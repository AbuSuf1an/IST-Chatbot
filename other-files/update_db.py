"""
Standalone script to update database with scraped content
Run independently from the main FastAPI application
"""

import os
import json
import psycopg2
from typing import List, Dict
import logging
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import re

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseUpdater:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'ist_data'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
        
        # Initialize embeddings model
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        self.embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=gemini_api_key
        )
    
    def load_scraped_content(self) -> List[Dict[str, str]]:
        """Load FAQ content from file with progress bar"""
        content_file = 'data/scraped-content-faqs.txt'  # Updated filename
        
        if not os.path.exists(content_file):
            logger.error(f"FAQ content file not found: {content_file}")
            logger.info("Please run gen_faq.py first to generate the FAQ file")
            return []
        
        logger.info(f"Loading FAQ content from: {content_file}")
        
        with open(content_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the FAQ file format
        # Split by the main separator lines
        sections = content.split("=" * 80)
        parsed_data = []
        
        current_q = ""
        current_a = ""
        faq_counter = 0
        
        # Progress bar for parsing FAQs
        lines = content.split('\n')
        parse_progress = tqdm(lines, desc="📖 Parsing FAQ content", unit="line")
        
        for line in parse_progress:
            line = line.strip()
            
            if not line:
                continue
            
            # Skip header lines
            if line.startswith("IST (Institute of Science and Technology)"):
                continue
            if line.startswith("=" * 10):  # Skip separator lines
                continue
            
            # Match Q1:, Q2:, etc.
            if re.match(r'^Q\d+:', line):
                # If we have a previous Q&A pair, save it
                if current_q and current_a:
                    faq_counter += 1
                    parsed_data.append({
                        'url': f'faq_item_{faq_counter}',
                        'title': f'FAQ {faq_counter}',
                        'content': f"Question: {current_q}\n\nAnswer: {current_a}",
                        'word_count': len(f"{current_q} {current_a}".split())
                    })
                    parse_progress.set_postfix({'FAQs': faq_counter})
                
                # Start new question
                current_q = line[line.find(':')+1:].strip()
                current_a = ""
            
            # Match A1:, A2:, etc.
            elif re.match(r'^A\d+:', line):
                current_a = line[line.find(':')+1:].strip()
            
            # Skip dashes separator
            elif line.startswith("-" * 10):
                continue
            
            # Continue building the answer if we're in answer mode
            elif current_q and current_a and not re.match(r'^[QA]\d+:', line):
                current_a += f" {line}"
        
        # Don't forget the last Q&A pair
        if current_q and current_a:
            faq_counter += 1
            parsed_data.append({
                'url': f'faq_item_{faq_counter}',
                'title': f'FAQ {faq_counter}',
                'content': f"Question: {current_q}\n\nAnswer: {current_a}",
                'word_count': len(f"{current_q} {current_a}".split())
            })
        
        parse_progress.close()
        logger.info(f"Loaded {len(parsed_data)} FAQ items from content")
        return parsed_data
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            # Try to end at a sentence boundary
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                boundary = max(last_period, last_newline)
                
                if boundary > start + chunk_size // 2:
                    chunk = text[start:start + boundary + 1]
                    end = start + boundary + 1
            
            chunks.append(chunk.strip())
            start = end - overlap if end < len(text) else end
        
        return chunks
    
    def process_scraped_content(self, scraped_data: List[Dict[str, str]]) -> List[Dict[str, any]]:
        """Process scraped content into database-ready format with progress bar"""
        processed_docs = []
        
        # Progress bar for overall pages
        page_progress = tqdm(scraped_data, desc="📄 Processing pages", unit="page")
        
        for item in page_progress:
            if not item['content']:
                continue
            
            # Update progress bar description with current URL
            page_progress.set_postfix({
                'Current': item['url'].split('/')[-1][:30] + '...' if len(item['url']) > 30 else item['url']
            })
            
            # Combine title and content for better context
            full_content = f"Title: {item['title']}\n\n{item['content']}" if item['title'] else item['content']
            
            # Split into chunks
            chunks = self.chunk_text(full_content)
            
            # Progress bar for chunks within each page
            chunk_progress = tqdm(enumerate(chunks), 
                                desc=f"  🔍 Processing chunks", 
                                total=len(chunks), 
                                leave=False,
                                unit="chunk")
            
            for i, chunk in chunk_progress:
                if len(chunk.strip()) < 50:  # Skip very short chunks
                    continue
                
                # Create filename for this chunk
                url_safe = item['url'].replace('https://', '').replace('http://', '').replace('/', '_').replace('?', '_').replace('&', '_')
                filename = f"web_{url_safe}_chunk_{i+1}.txt"
                
                # Generate embedding with progress update
                try:
                    chunk_progress.set_postfix({'Status': 'Generating embedding...'})
                    embedding = self.embeddings_model.embed_query(chunk)
                    
                    processed_docs.append({
                        'filename': filename,
                        'content': chunk,
                        'chunk_index': i + 1,  # ← FIX: Set chunk_index here in the main doc dict
                        'embedding': embedding,
                        'metadata': json.dumps({
                            'source_url': item['url'],
                            'page_title': item['title'],
                            'chunk_index': i + 1,
                            'total_chunks': len(chunks),
                            'content_type': 'web_scraped',
                            'word_count': len(chunk.split())
                        })
                    })
                    
                    chunk_progress.set_postfix({'Status': '✅ Done'})
                
                except Exception as e:
                    chunk_progress.set_postfix({'Status': f'❌ Error: {str(e)[:20]}...'})
                    logger.error(f"❌ Failed to generate embedding for chunk from {item['url']}: {str(e)}")
                    continue
        
            chunk_progress.close()
        
        page_progress.close()
        return processed_docs
    
    def insert_documents(self, documents: List[Dict[str, any]]) -> int:
        """Insert documents into the database with progress bar"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            inserted_count = 0
            
            # Progress bar for database insertions
            insert_progress = tqdm(documents, desc="💾 Inserting documents", unit="doc")
            
            for doc in insert_progress:
                # Update progress bar with current filename
                insert_progress.set_postfix({
                    'Current': doc['filename'][:40] + '...' if len(doc['filename']) > 40 else doc['filename']
                })
                
                # Get chunk_index - it should be in the main doc dict now
                chunk_index = doc.get('chunk_index')
                if chunk_index is None:
                    # Fallback: try to extract from metadata
                    try:
                        metadata = json.loads(doc['metadata'])
                        chunk_index = metadata.get('chunk_index', 1)
                    except:
                        chunk_index = 1  # Default fallback
                    
                    logger.warning(f"chunk_index was None for {doc['filename']}, using {chunk_index}")
                
                # Convert embedding to string format for PostgreSQL
                embedding_str = '[' + ','.join(map(str, doc['embedding'])) + ']'
                
                # Insert new document with proper chunk_index
                cur.execute("""
                    INSERT INTO documents (filename, content, chunk_index, embedding, metadata, created_at) 
                    VALUES (%s, %s, %s, %s::vector, %s, NOW())
                """, (
                    doc['filename'], 
                    doc['content'], 
                    chunk_index,  # Use the validated chunk_index
                    embedding_str, 
                    doc['metadata']
                ))
                
                inserted_count += 1
                insert_progress.set_postfix({'Inserted': inserted_count})
            
            insert_progress.close()
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"✅ Inserted {inserted_count} new documents")
            return inserted_count
        
        except Exception as e:
            logger.error(f"❌ Failed to insert documents: {str(e)}")
            raise
    
    def clear_web_scraped_data(self):
        """Remove all previously scraped web content"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            # Delete all web scraped documents
            cur.execute("DELETE FROM documents WHERE filename LIKE 'web_%'")
            deleted_count = cur.rowcount
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"🗑️  Deleted {deleted_count} old web scraped documents")
            return deleted_count
        except Exception as e:
            logger.error(f"❌ Failed to clear web scraped data: {str(e)}")
            raise

def main():
    """Enhanced main function with overall progress tracking"""
    try:
        print("🚀 Starting database update with scraped content...")
        
        updater = DatabaseUpdater()
        
        # Clear old web data with progress
        print("🧹 Clearing old web scraped data...")
        cleared_count = updater.clear_web_scraped_data()
        print(f"✅ Cleared {cleared_count} old documents")
        
        # Load scraped data
        scraped_data = updater.load_scraped_content()
        
        if not scraped_data:
            print("❌ No scraped data found to process")
            return
        
        print(f"📄 Loaded {len(scraped_data)} scraped pages")
        
        # Process and insert into database
        processed_docs = updater.process_scraped_content(scraped_data)
        
        if not processed_docs:
            print("❌ No documents were processed")
            return
        
        print(f"💾 Inserting {len(processed_docs)} processed documents...")
        
        inserted_count = updater.insert_documents(processed_docs)
        
        print(f"\n🎉 Database update completed!")
        print(f"📊 Summary:")
        print(f"   📥 Original pages: {len(scraped_data)}")
        print(f"   📝 Generated chunks: {len(processed_docs)}")
        print(f"   💾 Inserted documents: {inserted_count}")
        
    except Exception as e:
        print(f"❌ Database update failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()