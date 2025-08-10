"""
Standalone web scraper for IST website pages
Run independently from the main FastAPI application
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import urljoin, urlparse
from typing import List, Dict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ISTWebScraper:
    def __init__(self, base_url: str = "https://ist.edu.bd"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
    
    def find_sitemap_urls(self) -> List[str]:
        """Find sitemap URLs from robots.txt or common locations"""
        sitemap_urls = []
        
        # Check robots.txt
        try:
            robots_response = self.session.get(f"{self.base_url}/robots.txt")
            if robots_response.status_code == 200:
                for line in robots_response.text.split('\n'):
                    if 'sitemap:' in line.lower():
                        sitemap_url = line.split(': ', 1)[1].strip()
                        sitemap_urls.append(sitemap_url)
        except:
            pass
        
        # Check common sitemap locations
        common_locations = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap_index.xml",
            f"{self.base_url}/wp-sitemap.xml"
        ]
        
        for url in common_locations:
            try:
                response = self.session.get(url)
                if response.status_code == 200:
                    sitemap_urls.append(url)
            except:
                continue
        
        return list(set(sitemap_urls)) if sitemap_urls else [f"{self.base_url}/sitemap.xml"]
    
    def parse_sitemap(self, sitemap_url: str) -> List[Dict[str, str]]:
        """Parse sitemap and extract URLs"""
        try:
            logger.info(f"Parsing sitemap: {sitemap_url}")
            response = self.session.get(sitemap_url)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch sitemap: {sitemap_url}")
                return []
            
            soup = BeautifulSoup(response.content, 'xml')
            urls = []
            
            # Handle nested sitemaps
            for sitemap in soup.find_all("sitemap"):
                loc = sitemap.find("loc")
                if loc:
                    nested_urls = self.parse_sitemap(loc.text)
                    urls.extend(nested_urls)
            
            # Extract URLs from current sitemap
            for url_tag in soup.find_all("url"):
                loc = url_tag.find("loc")
                if loc:
                    url_data = {
                        'url': loc.text,
                        'lastmod': url_tag.find("lastmod").text if url_tag.find("lastmod") else '',
                        'priority': url_tag.find("priority").text if url_tag.find("priority") else ''
                    }
                    urls.append(url_data)
            
            return urls
        
        except Exception as e:
            logger.error(f"Error parsing sitemap {sitemap_url}: {str(e)}")
            return []
    
    def discover_urls_from_homepage(self) -> List[Dict[str, str]]:
        """Fallback: discover URLs by crawling from homepage"""
        try:
            logger.info("Discovering URLs from homepage")
            response = self.session.get(self.base_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            urls = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(self.base_url, href)
                
                # Only include URLs from the same domain
                if urlparse(full_url).netloc == urlparse(self.base_url).netloc:
                    urls.append({
                        'url': full_url,
                        'lastmod': '',
                        'priority': ''
                    })
            
            # Remove duplicates
            seen = set()
            unique_urls = []
            for url_data in urls:
                if url_data['url'] not in seen:
                    seen.add(url_data['url'])
                    unique_urls.append(url_data)
            
            return unique_urls[:50]  # Limit to 50 URLs for safety
        
        except Exception as e:
            logger.error(f"Error discovering URLs from homepage: {str(e)}")
            return []
    
    def get_all_urls(self) -> List[str]:
        """Get all URLs to scrape"""
        all_urls = []
        
        # Try sitemap first
        sitemap_urls = self.find_sitemap_urls()
        for sitemap_url in sitemap_urls:
            urls = self.parse_sitemap(sitemap_url)
            all_urls.extend([url_data['url'] for url_data in urls])
        
        # If no URLs found, try homepage discovery
        if not all_urls:
            logger.info("No sitemap URLs found, trying homepage discovery")
            url_data_list = self.discover_urls_from_homepage()
            all_urls = [url_data['url'] for url_data in url_data_list]
        
        # Save URLs to CSV
        if all_urls:
            df = pd.DataFrame({'url': all_urls})
            df.to_csv('data/scraped_urls.csv', index=False)
            logger.info(f"Found {len(all_urls)} URLs")
        
        return list(set(all_urls))  # Remove duplicates
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def fetch_page_content(self, url: str) -> str:
        """Fetch content from a single page with retry logic"""
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    
    def extract_text_from_url(self, url: str) -> Dict[str, str]:
        """Extract clean text from a URL"""
        try:
            logger.info(f"Processing: {url}")
            content = self.fetch_page_content(url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "aside"]):
                element.decompose()
            
            # Extract title
            title = soup.find('title')
            page_title = title.get_text().strip() if title else ''
            
            # Extract main content
            text = soup.get_text(separator='\n', strip=True)
            
            # Clean up text
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            clean_text = '\n'.join(lines)
            
            return {
                'url': url,
                'title': page_title,
                'content': clean_text,
                'word_count': len(clean_text.split())
            }
        
        except Exception as e:
            logger.error(f"Error extracting text from {url}: {str(e)}")
            return {
                'url': url,
                'title': '',
                'content': '',
                'word_count': 0
            }
    
    def scrape_all_pages(self, max_workers: int = 3) -> List[Dict[str, str]]:
        """Scrape all pages using multithreading"""
        urls = self.get_all_urls()
        
        if not urls:
            logger.error("No URLs found to scrape")
            return []
        
        logger.info(f"Starting to scrape {len(urls)} pages with {max_workers} workers")
        
        all_content = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.extract_text_from_url, url): url for url in urls}
            
            for future in as_completed(futures):
                result = future.result()
                if result['content']:  # Only add if content was extracted
                    all_content.append(result)
        
        # Save all content to file
        if all_content:
            with open('data/scraped_content.txt', 'w', encoding='utf-8') as f:
                for item in all_content:
                    f.write(f"URL: {item['url']}\n")
                    f.write(f"TITLE: {item['title']}\n")
                    f.write(f"CONTENT:\n{item['content']}\n")
                    f.write("=" * 80 + "\n\n")
            
            logger.info(f"Scraped {len(all_content)} pages successfully")
        
        return all_content

def main():
    """Main function to run the scraper"""
    print("🚀 Starting IST Website Scraper...")
    
    scraper = ISTWebScraper("https://ist.edu.bd")
    content = scraper.scrape_all_pages(max_workers=3)
    
    if content:
        total_words = sum(item['word_count'] for item in content)
        print(f"✅ Scraping completed!")
        print(f"📄 Total pages scraped: {len(content)}")
        print(f"📝 Total words: {total_words:,}")
        print(f"💾 Data saved to: data/scraped_content.txt")
        print(f"🔗 URLs saved to: data/scraped_urls.csv")
        return content
    else:
        print("❌ No content was scraped")
        return []

if __name__ == "__main__":
    main()