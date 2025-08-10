import google.generativeai as genai
import json
import re
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

class FAQProcessor:
    def __init__(self):
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
    
    def clean_and_extract_faqs(self, raw_content: str) -> List[Dict[str, str]]:
        """Process raw scraped content and extract meaningful FAQ pairs"""
        
        # First, clean the content
        cleaned_content = self.preprocess_content(raw_content)
        
        # Generate FAQ using Gemini
        prompt = f"""
        Please analyze the following scraped content from Institute of Science and Technology (IST) Bangladesh and convert it into a clean FAQ format.
        
        Instructions:
        1. Remove all duplicate, junk, or irrelevant data
        2. Extract meaningful information about the institute and convert it into question-answer pairs
        3. Create clear, concise questions that students or prospective students might actually ask
        4. Provide comprehensive but concise answers
        5. Ignore navigation elements, footers, headers, advertisements, and repetitive content
        6. Focus on substantive content about courses, admissions, faculty, facilities, etc.
        7. Return the result as a JSON array with objects containing 'question' and 'answer' fields
        
        Content to process:
        {cleaned_content[:8000]}  # Limit content to avoid token limits
        
        Return only valid JSON in this format:
        [
            {{"question": "What courses does IST offer?", "answer": "..."}},
            {{"question": "How do I apply for admission?", "answer": "..."}}
        ]
        """
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            json_text = response.text.strip()
            
            # Try to find JSON array in the response
            json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = json_text
            
            # Clean up common formatting issues
            json_str = json_str.replace('```json', '').replace('```', '').strip()
            
            faqs = json.loads(json_str)
            return faqs
                
        except Exception as e:
            print(f"Error processing with Gemini: {e}")
            print(f"Raw response: {response.text[:200]}...")
            return []
    
    def preprocess_content(self, content: str) -> str:
        """Basic preprocessing to clean up scraped content"""
        # Remove extra whitespace and newlines
        content = re.sub(r'\n+', ' ', content)
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common junk patterns specific to IST website
        junk_patterns = [
            r'Skip to content',
            r'Sitemap',
            r'FAQ',
            r'Hotline: 017 2693 7910',
            r'info@ist\.edu\.bd',
            r'Facebook',
            r'Youtube',
            r'Linkedin',
            r'Institute of Science and Technology',
            r'a center of excellence for education',
            r'Search',
            r'Menu',
            r'All Rights Reserved.*?ISTians',
            r'Created with ♥ by ISTians',
            r'Loading\.\.\.',
            r'Copyright.*?\d{4}',
        ]
        
        for pattern in junk_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def process_large_content(self, content: str, chunk_size: int = 6000) -> List[Dict[str, str]]:
        """Process large content by breaking it into chunks"""
        all_faqs = []
        
        # Split content into chunks
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        
        print(f"Processing {len(chunks)} chunks...")
        
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}...")
            chunk_faqs = self.clean_and_extract_faqs(chunk)
            if chunk_faqs:
                all_faqs.extend(chunk_faqs)
                print(f"  Generated {len(chunk_faqs)} FAQs from chunk {i+1}")
        
        # Remove duplicates
        unique_faqs = self.remove_duplicate_faqs(all_faqs)
        print(f"Total FAQs after removing duplicates: {len(unique_faqs)}")
        
        return unique_faqs
    
    def remove_duplicate_faqs(self, faqs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate FAQ entries based on similarity"""
        unique_faqs = []
        seen_questions = set()
        
        for faq in faqs:
            # Normalize question for comparison
            question_key = faq['question'].lower().strip().replace('?', '').replace('.', '')
            question_key = re.sub(r'\s+', ' ', question_key)
            
            if question_key not in seen_questions and len(question_key) > 10:
                seen_questions.add(question_key)
                unique_faqs.append(faq)
        
        return unique_faqs
    
    def save_to_text_file(self, faqs: List[Dict[str, str]], filename: str = 'cleaned_faqs.txt'):
        """Save FAQ data to a clean text file"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("IST (Institute of Science and Technology) - Frequently Asked Questions\n")
            f.write("=" * 80 + "\n\n")
            
            for i, faq in enumerate(faqs, 1):
                f.write(f"Q{i}: {faq['question']}\n")
                f.write("-" * 50 + "\n")
                f.write(f"A{i}: {faq['answer']}\n\n")
                f.write("=" * 80 + "\n\n")
        
        print(f"✅ Saved {len(faqs)} FAQs to {filename}")
        return filename
    
    def cleanup_scraper_files(self):
        """Delete scraped content and URL files after processing"""
        files_to_delete = [
            'data/scraped_content.txt',
            'data/scraped_urls.csv'
        ]
        
        deleted_files = []
        
        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_files.append(file_path)
                    print(f"🗑️  Deleted: {file_path}")
                else:
                    print(f"ℹ️  File not found (skipping): {file_path}")
            except Exception as e:
                print(f"❌ Failed to delete {file_path}: {e}")
        
        if deleted_files:
            print(f"✅ Successfully cleaned up {len(deleted_files)} scraper files")
        else:
            print("ℹ️  No scraper files found to clean up")
        
        return deleted_files

def generate_faqs_from_content(scraped_content):
    faqs = []
    
    # Contact Information
    contact_patterns = {
        'phone': r'(?:phone|tel|call|hotline)[:\s]*([+\d\s\-\(\)]+)',
        'email': r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        'address': r'(?:address|location)[:\s]*([^\n]+(?:\n[^\n]+)*?)(?=\n\n|\n[A-Z]|$)',
        'fax': r'(?:fax)[:\s]*([+\d\s\-\(\)]+)'
    }
    
    for content_type, items in scraped_content.items():
        for item in items:
            content = item.get('content', '').lower()
            original_content = item.get('content', '')
            title = item.get('title', '')
            
            # Extract contact information
            for contact_type, pattern in contact_patterns.items():
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if contact_type == 'phone' and len(match.strip()) > 6:
                        faqs.append({
                            "question": f"What is the {contact_type} number?",
                            "answer": match.strip(),
                            "category": "contact"
                        })
                    elif contact_type == 'email' and '@' in match:
                        faqs.append({
                            "question": f"What is the email address?",
                            "answer": match.strip(),
                            "category": "contact"
                        })
            
            # Faculty/Teacher Information
            if any(keyword in content for keyword in ['professor', 'lecturer', 'faculty', 'teacher', 'instructor']):
                # Extract faculty details
                name_match = re.search(r'^([A-Z][a-zA-Z\s.]+)(?:\n|$)', original_content, re.MULTILINE)
                if name_match:
                    faculty_name = name_match.group(1).strip()
                    
                    # Position/Title
                    position_match = re.search(r'((?:assistant |associate |)?professor|lecturer|instructor|head of|director)', content, re.IGNORECASE)
                    if position_match:
                        faqs.append({
                            "question": f"Who is {faculty_name}?",
                            "answer": f"{faculty_name} is {position_match.group(1)} at the institute.",
                            "category": "faculty"
                        })
                    
                    # Department
                    dept_match = re.search(r'department of ([^.\n]+)', content, re.IGNORECASE)
                    if dept_match:
                        faqs.append({
                            "question": f"Which department does {faculty_name} belong to?",
                            "answer": f"{faculty_name} is in the {dept_match.group(1).strip()}.",
                            "category": "faculty"
                        })
                    
                    # Email
                    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', original_content)
                    if email_match:
                        faqs.append({
                            "question": f"What is {faculty_name}'s email?",
                            "answer": email_match.group(1),
                            "category": "faculty"
                        })
                    
                    # Academic Background
                    if 'academic background' in content or 'education' in content:
                        degree_matches = re.findall(r'((?:ph\.?d|m\.?\s?sc|b\.?\s?sc|mba|ma|ba)[^.\n]*)', content, re.IGNORECASE)
                        for degree in degree_matches[:3]:  # Limit to top 3 degrees
                            faqs.append({
                                "question": f"What is {faculty_name}'s educational background?",
                                "answer": f"{faculty_name} has {degree.strip()}",
                                "category": "faculty"
                            })
                    
                    # Research Areas
                    research_match = re.search(r'research areas?[:\s]*([^.\n]+(?:[,;][^.\n]+)*)', content, re.IGNORECASE)
                    if research_match:
                        faqs.append({
                            "question": f"What are {faculty_name}'s research areas?",
                            "answer": f"{faculty_name}'s research areas include: {research_match.group(1).strip()}",
                            "category": "faculty"
                        })
                    
                    # Publications
                    if 'publications' in content:
                        pub_count = len(re.findall(r'published in', content, re.IGNORECASE))
                        if pub_count > 0:
                            faqs.append({
                                "question": f"How many publications does {faculty_name} have?",
                                "answer": f"{faculty_name} has {pub_count} publications listed.",
                                "category": "faculty"
                            })
            
            # Wi-Fi and Network Information
            wifi_patterns = [
                r'wi-?fi[:\s]*([^\n]+)',
                r'network[:\s]*([^\n]+)',
                r'password[:\s]*([^\n]+)',
                r'ssid[:\s]*([^\n]+)'
            ]
            
            for pattern in wifi_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if any(keyword in match.lower() for keyword in ['password', 'wifi', 'network', 'ssid']):
                        faqs.append({
                            "question": "What is the Wi-Fi password/network information?",
                            "answer": match.strip(),
                            "category": "facilities"
                        })
            
            # Academic Programs
            program_keywords = ['bachelor', 'master', 'phd', 'diploma', 'certificate', 'degree', 'program']
            if any(keyword in content for keyword in program_keywords):
                program_matches = re.findall(r'((?:bachelor|master|phd|diploma|certificate)[^.\n]*)', content, re.IGNORECASE)
                for program in program_matches[:5]:  # Limit to 5 programs
                    faqs.append({
                        "question": "What academic programs are offered?",
                        "answer": program.strip().title(),
                        "category": "academics"
                    })
            
            # Admission Information
            admission_keywords = ['admission', 'application', 'enrollment', 'apply', 'requirements']
            if any(keyword in content for keyword in admission_keywords):
                # Extract admission requirements
                req_matches = re.findall(r'(?:requirement|criteria|eligibility)[:\s]*([^.\n]+)', content, re.IGNORECASE)
                for req in req_matches:
                    faqs.append({
                        "question": "What are the admission requirements?",
                        "answer": req.strip(),
                        "category": "admission"
                    })
                
                # Extract deadlines
                deadline_matches = re.findall(r'(?:deadline|last date)[:\s]*([^.\n]+)', content, re.IGNORECASE)
                for deadline in deadline_matches:
                    faqs.append({
                        "question": "What is the admission deadline?",
                        "answer": deadline.strip(),
                        "category": "admission"
                    })
            
            # Fees and Costs
            fee_patterns = [
                r'(?:fee|tuition|cost|charge)[:\s]*([^\n]+)',
                r'(\$\d+|\d+\s*(?:taka|tk|usd|dollars?))',
            ]
            
            for pattern in fee_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if any(char.isdigit() for char in match):
                        faqs.append({
                            "question": "What are the fees?",
                            "answer": match.strip(),
                            "category": "fees"
                        })
            
            # Facilities
            facility_keywords = ['library', 'lab', 'laboratory', 'cafeteria', 'hostel', 'dormitory', 'gym', 'sports']
            for facility in facility_keywords:
                if facility in content:
                    facility_info = re.search(rf'{facility}[:\s]*([^.\n]+)', content, re.IGNORECASE)
                    if facility_info:
                        faqs.append({
                            "question": f"What {facility} facilities are available?",
                            "answer": facility_info.group(1).strip(),
                            "category": "facilities"
                        })
            
            # Events and News
            if any(keyword in content for keyword in ['event', 'seminar', 'workshop', 'conference', 'news']):
                event_matches = re.findall(r'(?:event|seminar|workshop|conference)[:\s]*([^.\n]+)', content, re.IGNORECASE)
                for event in event_matches[:3]:  # Limit to 3 events
                    faqs.append({
                        "question": "What events are happening?",
                        "answer": event.strip(),
                        "category": "events"
                    })
            
            # Departments
            dept_patterns = [
                r'department of ([^.\n]+)',
                r'school of ([^.\n]+)',
                r'faculty of ([^.\n]+)'
            ]
            
            for pattern in dept_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    faqs.append({
                        "question": "What departments are available?",
                        "answer": f"Department of {match.strip().title()}",
                        "category": "academics"
                    })
            
            # Location and Transportation
            location_keywords = ['location', 'address', 'campus', 'building', 'transport', 'bus', 'parking']
            for keyword in location_keywords:
                if keyword in content:
                    location_info = re.search(rf'{keyword}[:\s]*([^.\n]+)', content, re.IGNORECASE)
                    if location_info:
                        faqs.append({
                            "question": f"What is the {keyword} information?",
                            "answer": location_info.group(1).strip(),
                            "category": "location"
                        })
            
            # Office Hours
            hours_match = re.search(r'(?:office hours?|hours?|timing)[:\s]*([^.\n]+)', content, re.IGNORECASE)
            if hours_match:
                faqs.append({
                    "question": "What are the office hours?",
                    "answer": hours_match.group(1).strip(),
                    "category": "general"
                })
    
    # Remove duplicates while preserving order
    seen = set()
    unique_faqs = []
    for faq in faqs:
        # Create a key based on question and answer similarity
        key = (faq['question'].lower().strip(), faq['answer'].lower().strip()[:50])
        if key not in seen:
            seen.add(key)
            unique_faqs.append(faq)
    
    return unique_faqs

# Enhanced function to save FAQs with better organization
def save_enhanced_faqs(faqs, filename="enhanced_faqs.json"):
    # Group FAQs by category
    categorized_faqs = {}
    for faq in faqs:
        category = faq.get('category', 'general')
        if category not in categorized_faqs:
            categorized_faqs[category] = []
        categorized_faqs[category].append(faq)
    
    # Sort each category by relevance (question length as a simple heuristic)
    for category in categorized_faqs:
        categorized_faqs[category].sort(key=lambda x: len(x['question']))
    
    output = {
        "total_faqs": len(faqs),
        "categories": list(categorized_faqs.keys()),
        "faqs_by_category": categorized_faqs,
        "all_faqs": faqs
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"Enhanced FAQs saved to {filename}")
    print(f"Total FAQs: {len(faqs)}")
    print(f"Categories: {', '.join(categorized_faqs.keys())}")
    for category, items in categorized_faqs.items():
        print(f"  - {category}: {len(items)} FAQs")

def main():
    try:
        # Initialize processor
        processor = FAQProcessor()
        
        # Check if scraped content exists
        content_file = 'data/scraped_content.txt'
        if not os.path.exists(content_file):
            print(f"❌ File not found: {content_file}")
            print("ℹ️  Please run scraper.py first to generate scraped content")
            return
        
        # Read scraped content
        with open(content_file, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        print(f"📖 Processing {len(raw_content):,} characters of scraped content...")
        
        # Process content
        faqs = processor.process_large_content(raw_content)
        
        if not faqs:
            print("❌ No FAQs were generated")
            return
        
        # Save results to text file
        output_file = processor.save_to_text_file(faqs, 'data/scraped-content-faqs.txt')
        
        # Show preview
        print(f"\n📋 Preview of generated FAQs:")
        print("-" * 50)
        for i, faq in enumerate(faqs[:3]):
            print(f"\nQ{i+1}: {faq['question']}")
            print(f"A{i+1}: {faq['answer'][:100]}{'...' if len(faq['answer']) > 100 else ''}")
        
        print(f"\n🎉 Successfully generated {len(faqs)} FAQs!")
        print(f"💾 Output saved to: {output_file}")
        
        # Clean up scraper files after successful processing
        print(f"\n🧹 Cleaning up scraper files...")
        processor.cleanup_scraper_files()
        
        print(f"\n✨ FAQ generation and cleanup completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()