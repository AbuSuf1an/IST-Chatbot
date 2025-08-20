import google.generativeai as genai
import json
import re
import os
from typing import List, Dict
from dotenv import load_dotenv
from tqdm import tqdm

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
        
        # Light preprocessing - keep important content
        cleaned_content = self.light_preprocess_content(raw_content)
        
        # Enhanced prompt for better information extraction
        prompt = f"""
        You are an expert at extracting comprehensive information from educational institution content. 
        
        Analyze the following scraped content from Institute of Science and Technology (IST) Bangladesh and create detailed FAQ pairs.
        
        CRITICAL REQUIREMENTS:
        1. Extract ALL faculty/teacher information including names, positions, departments, qualifications, research areas, publications
        2. Extract ALL technical details like Wi-Fi passwords, network information, system details
        3. Extract ALL contact information, addresses, phone numbers, emails
        4. Extract ALL academic programs, courses, admission requirements, fees
        5. Extract ALL facility information, lab details, equipment, services
        6. Create specific, detailed questions and comprehensive answers
        7. DO NOT miss any factual information - include everything available
        
        FACULTY INFORMATION PRIORITY:
        - Full name and title (Professor, Assistant Professor, Lecturer, etc.)
        - Department and position
        - Educational background and degrees
        - Research interests and areas
        - Publications and achievements
        - Contact information
        
        TECHNICAL INFORMATION PRIORITY:
        - Wi-Fi passwords and network details
        - System specifications
        - Lab equipment and software
        - Technical requirements
        
        Content to analyze:
        {cleaned_content[:12000]}  # Increased limit
        
        Return ONLY valid JSON array with comprehensive FAQ pairs:
        [
            {{"question": "Who is [Faculty Name] and what is their background?", "answer": "Detailed information about the faculty member..."}},
            {{"question": "What is the Wi-Fi password for [network]?", "answer": "The password is..."}},
            {{"question": "What are the technical specifications of [lab/equipment]?", "answer": "Technical details..."}}
        ]
        """
        
        try:
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                print(f"Empty response from Gemini")
                return []
            
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
            if response and hasattr(response, 'text'):
                print(f"Raw response: {response.text[:300]}...")
            return []
    
    def light_preprocess_content(self, content: str) -> str:
        """Light preprocessing - only remove truly junk content, keep important info"""
        
        # Only remove the most obvious junk, keep everything else
        minimal_junk_patterns = [
            r'Skip to content\s*',
            r'Created with ♥ by ISTians\s*',
            r'All Rights Reserved.*?Copyright.*?\d{4}\s*',
        ]
        
        for pattern in minimal_junk_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        # Clean up excessive whitespace but preserve structure
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Max 2 consecutive newlines
        content = re.sub(r' +', ' ', content)  # Multiple spaces to single space
        
        return content.strip()
    
    def process_large_content(self, content: str, chunk_size: int = 10000) -> List[Dict[str, str]]:
        """Process large content by breaking it into overlapping chunks"""
        all_faqs = []
        
        # Create overlapping chunks to avoid losing context at boundaries
        overlap = 1000  # 1000 character overlap
        chunks = []
        
        for i in range(0, len(content), chunk_size - overlap):
            chunk = content[i:i + chunk_size]
            chunks.append(chunk)
            if i + chunk_size >= len(content):
                break
        
        print(f"Processing {len(chunks)} overlapping chunks...")
        
        # Use progress bar
        for i, chunk in enumerate(tqdm(chunks, desc="Processing chunks")):
            print(f"\nProcessing chunk {i+1}/{len(chunks)}...")
            chunk_faqs = self.clean_and_extract_faqs(chunk)
            if chunk_faqs:
                all_faqs.extend(chunk_faqs)
                print(f"  ✅ Generated {len(chunk_faqs)} FAQs from chunk {i+1}")
            else:
                print(f"  ❌ No FAQs generated from chunk {i+1}")
        
        print(f"\nTotal FAQs before deduplication: {len(all_faqs)}")
        
        # Remove duplicates but be more lenient to keep important variations
        unique_faqs = self.smart_deduplicate_faqs(all_faqs)
        print(f"Total FAQs after smart deduplication: {len(unique_faqs)}")
        
        return unique_faqs
    
    def smart_deduplicate_faqs(self, faqs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Smart deduplication that keeps important variations"""
        unique_faqs = []
        seen_questions = {}
        
        for faq in faqs:
            if 'question' not in faq or 'answer' not in faq:
                continue
                
            # Normalize question for comparison
            question_key = faq['question'].lower().strip()
            question_key = re.sub(r'[^\w\s]', '', question_key)  # Remove punctuation
            question_key = re.sub(r'\s+', ' ', question_key)     # Normalize spaces
            
            # Check if we've seen a very similar question
            is_duplicate = False
            for seen_key in seen_questions:
                # Calculate simple word overlap
                words1 = set(question_key.split())
                words2 = set(seen_key.split())
                overlap = len(words1 & words2) / len(words1 | words2) if words1 | words2 else 0
                
                if overlap > 0.8:  # 80% word overlap = likely duplicate
                    # Keep the one with longer/better answer
                    if len(faq['answer']) > len(seen_questions[seen_key]['answer']):
                        # Replace the existing one
                        for j, existing_faq in enumerate(unique_faqs):
                            if existing_faq == seen_questions[seen_key]:
                                unique_faqs[j] = faq
                                seen_questions[seen_key] = faq
                                break
                    is_duplicate = True
                    break
            
            if not is_duplicate and len(question_key) > 5:  # Minimum question length
                unique_faqs.append(faq)
                seen_questions[question_key] = faq
        
        return unique_faqs
    
    def extract_manual_faqs(self, content: str) -> List[Dict[str, str]]:
        """Manual extraction for critical information that Gemini might miss"""
        faqs = []
        
        # Split content by pages/sections
        pages = content.split("=" * 80)
        
        print("🔍 Manually extracting critical information...")
        
        for page in tqdm(pages, desc="Scanning pages"):
            if len(page.strip()) < 100:
                continue
            
            lines = page.split('\n')
            
            # Extract faculty information more aggressively
            for i, line in enumerate(lines):
                line = line.strip()
                
                # Faculty name extraction (usually at the beginning of faculty pages)
                if re.match(r'^[A-Z][a-zA-Z\s.]+$', line) and len(line.split()) <= 4:
                    faculty_name = line.strip()
                    
                    # Look for position in next few lines
                    position = ""
                    department = ""
                    email = ""
                    
                    for j in range(i+1, min(i+20, len(lines))):
                        next_line = lines[j].strip()
                        
                        if re.search(r'(professor|lecturer|instructor|head|director)', next_line, re.IGNORECASE):
                            position = next_line
                        
                        if re.search(r'department of', next_line, re.IGNORECASE):
                            department = next_line
                        
                        if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', next_line):
                            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', next_line)
                            if email_match:
                                email = email_match.group(1)
                    
                    if position or department or email:
                        faqs.append({
                            "question": f"Who is {faculty_name}?",
                            "answer": f"{faculty_name} is {position} in the {department}. Contact: {email}".strip()
                        })
                
                # Wi-Fi passwords and technical info
                if any(keyword in line.lower() for keyword in ['password', 'wifi', 'wi-fi', 'network', 'ssid']):
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            faqs.append({
                                "question": f"What is the {parts[0].strip()}?",
                                "answer": parts[1].strip()
                            })
                
                # Phone numbers
                phone_match = re.search(r'(\+880\s?\d{2}\s?\d{4}\s?\d{4}|\d{3,4}[-\s]?\d{7,8}|017\s?\d{4}\s?\d{4})', line)
                if phone_match:
                    faqs.append({
                        "question": "What is the contact phone number?",
                        "answer": phone_match.group(1)
                    })
                
                # Addresses
                if 'house' in line.lower() and 'road' in line.lower() and 'dhaka' in line.lower():
                    faqs.append({
                        "question": "What is the address of IST?",
                        "answer": line.strip()
                    })
        
        print(f"🔍 Manually extracted {len(faqs)} additional FAQs")
        return faqs
    
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
        
        # Process content with Gemini
        gemini_faqs = processor.process_large_content(raw_content)
        
        # Extract additional information manually
        manual_faqs = processor.extract_manual_faqs(raw_content)
        
        # Combine both approaches
        all_faqs = gemini_faqs + manual_faqs
        
        # Final deduplication
        final_faqs = processor.smart_deduplicate_faqs(all_faqs)
        
        if not final_faqs:
            print("❌ No FAQs were generated")
            return
        
        # Save results to text file
        output_file = processor.save_to_text_file(final_faqs, 'data/scraped-content-faqs.txt')
        
        # Show preview
        print(f"\n📋 Preview of generated FAQs:")
        print("-" * 50)
        for i, faq in enumerate(final_faqs[:5]):  # Show more examples
            print(f"\nQ{i+1}: {faq['question']}")
            print(f"A{i+1}: {faq['answer'][:150]}{'...' if len(faq['answer']) > 150 else ''}")
        
        print(f"\n🎉 Successfully generated {len(final_faqs)} FAQs!")
        print(f"📊 Breakdown:")
        print(f"   - Gemini extracted: {len(gemini_faqs)} FAQs")
        print(f"   - Manual extracted: {len(manual_faqs)} FAQs")
        print(f"   - Final unique: {len(final_faqs)} FAQs")
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