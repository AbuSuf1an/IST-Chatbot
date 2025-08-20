import google.generativeai as genai
import json
import re
import os
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

class AIFAQCleaner:
    def __init__(self):
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
    
    def evaluate_faq_batch(self, faqs_batch: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Evaluate a batch of FAQs using AI to determine which ones are meaningful.
        """
        
        # Prepare the batch for evaluation
        faq_text = ""
        for i, faq in enumerate(faqs_batch):
            faq_text += f"FAQ {i+1}:\n"
            faq_text += f"Q: {faq['question']}\n"
            faq_text += f"A: {faq['answer']}\n\n"
        
        prompt = f"""
You are an expert content curator for educational institution FAQs. Your task is to evaluate the following FAQ entries and identify which ones are meaningful and useful.

EVALUATION CRITERIA - Mark as KEEP if:
1. The question makes logical sense and asks about real information
2. The answer provides actual, useful information
3. The question is about real people, places, programs, or services
4. The content would be helpful to students, faculty, or visitors

EVALUATION CRITERIA - Mark as REMOVE if:
1. The question asks "Who is [navigation element]?" like "Who is Menu?", "Who is Search?", "Who is Facebook?"
2. The question asks about generic terms as if they were people: "Who is Machine Learning?", "Who is Research Areas?"
3. The answer is empty, template-like, or contains only contact info with no real content
4. The question asks about obviously non-human entities as if they were people
5. The answer is clearly garbled, duplicated, or nonsensical
6. The question is about webpage elements, technical terms, or abstract concepts treated as people

INSTRUCTIONS:
- Respond with ONLY a JSON array
- For each FAQ, provide: {{"index": number, "decision": "KEEP" or "REMOVE", "reason": "brief explanation"}}
- Be strict but fair - when in doubt, lean toward REMOVE for clearly nonsensical content

FAQs to evaluate:

{faq_text}

Return your evaluation as a JSON array:
"""
        
        try:
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                print(f"Empty response from AI evaluator")
                return []
            
            # Extract JSON from response
            json_text = response.text.strip()
            json_text = json_text.replace('```json', '').replace('```', '').strip()
            
            # Find JSON array
            json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = json_text
            
            evaluations = json.loads(json_str)
            
            # Filter FAQs based on AI evaluation
            kept_faqs = []
            for eval_item in evaluations:
                if eval_item.get('decision') == 'KEEP':
                    idx = eval_item.get('index', 1) - 1  # Convert to 0-based index
                    if 0 <= idx < len(faqs_batch):
                        kept_faqs.append(faqs_batch[idx])
                        print(f"✅ KEPT: {faqs_batch[idx]['question'][:60]}...")
                else:
                    idx = eval_item.get('index', 1) - 1
                    if 0 <= idx < len(faqs_batch):
                        reason = eval_item.get('reason', 'No reason provided')
                        print(f"❌ REMOVED: {faqs_batch[idx]['question'][:60]}... (Reason: {reason})")
            
            return kept_faqs
            
        except Exception as e:
            print(f"Error evaluating FAQ batch: {e}")
            # Fallback to basic filtering if AI fails
            return self.basic_filter_fallback(faqs_batch)
    
    def basic_filter_fallback(self, faqs_batch: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Fallback filtering using rule-based approach if AI evaluation fails.
        """
        print("Using fallback rule-based filtering...")
        
        kept_faqs = []
        for faq in faqs_batch:
            if self.is_meaningful_basic(faq['question'], faq['answer']):
                kept_faqs.append(faq)
        
        return kept_faqs
    
    def is_meaningful_basic(self, question: str, answer: str) -> bool:
        """
        Basic rule-based filtering as fallback.
        """
        # Skip questions about navigation elements or webpage components
        nav_elements = [
            'menu', 'search', 'sitemap', 'faq', 'facebook', 'youtube', 'linkedin',
            'skip to content', 'view', 'download', 'submit', 'loading', 'home',
            'about us', 'contact', 'quick links', 'student clubs'
        ]
        
        for element in nav_elements:
            if f"who is {element}" in question.lower():
                return False
        
        # Skip questions about abstract concepts as people
        abstract_concepts = [
            'machine learning', 'research areas', 'publications', 'biography',
            'academic background', 'degree', 'university', 'subject', 'result',
            'artificial intelligence', 'deep learning', 'network security',
            'software engineering', 'computer science', 'electronics'
        ]
        
        for concept in abstract_concepts:
            if f"who is {concept}" in question.lower():
                return False
        
        # Skip template answers
        if " is  in the . Contact:" in answer:
            return False
        
        # Keep if answer has substantial content
        return len(answer.strip()) > 50 and not answer.strip().endswith("Contact: info@ist.edu.bd")
    
    def clean_faq_file(self, input_file: str, output_file: str, batch_size: int = 10):
        """
        Clean the FAQ file using AI evaluation in batches.
        """
        
        if not os.path.exists(input_file):
            print(f"❌ Input file not found: {input_file}")
            return
        
        print(f"🤖 AI-powered FAQ cleaning started: {input_file}")
        
        # Read and parse FAQs
        faqs = self.parse_faq_file(input_file)
        total_original = len(faqs)
        print(f"📋 Found {total_original} FAQs to evaluate")
        
        if total_original == 0:
            print("No FAQs found to process")
            return
        
        # Process FAQs in batches
        cleaned_faqs = []
        
        for i in tqdm(range(0, len(faqs), batch_size), desc="Processing batches"):
            batch = faqs[i:i + batch_size]
            print(f"\n🔍 Evaluating batch {i//batch_size + 1}/{(len(faqs) + batch_size - 1)//batch_size}")
            
            kept_batch = self.evaluate_faq_batch(batch)
            cleaned_faqs.extend(kept_batch)
        
        # Save cleaned FAQs
        self.save_cleaned_faqs(cleaned_faqs, output_file)
        
        # Print summary
        total_kept = len(cleaned_faqs)
        total_removed = total_original - total_kept
        removal_rate = (total_removed / total_original) * 100 if total_original > 0 else 0
        
        print(f"\n📊 AI Cleaning Summary:")
        print(f"   - Original FAQs: {total_original}")
        print(f"   - Kept (meaningful): {total_kept}")
        print(f"   - Removed (nonsensical): {total_removed}")
        print(f"   - Removal rate: {removal_rate:.1f}%")
        print(f"✅ Cleaned FAQs saved to: {output_file}")
    
    def parse_faq_file(self, filename: str) -> List[Dict[str, str]]:
        """
        Parse FAQ file and extract questions and answers.
        """
        faqs = []
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by FAQ sections
        sections = content.split("=" * 80)
        
        for section in sections:
            section = section.strip()
            if len(section) < 50:
                continue
            
            lines = section.split('\n')
            question = ""
            answer = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith('Q') and ':' in line:
                    question = line.split(':', 1)[1].strip()
                elif line.startswith('A') and ':' in line:
                    # Get the full answer (might span multiple lines)
                    answer_start = section.find(line)
                    remaining = section[answer_start:]
                    answer = remaining.split(':', 1)[1].strip()
                    break
            
            if question and answer:
                faqs.append({
                    'question': question,
                    'answer': answer
                })
        
        return faqs
    
    def save_cleaned_faqs(self, faqs: List[Dict[str, str]], filename: str):
        """
        Save cleaned FAQs to file.
        """
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("IST (Institute of Science and Technology) - AI Cleaned FAQs\n")
            f.write("=" * 80 + "\n\n")
            
            for i, faq in enumerate(faqs, 1):
                f.write(f"Q{i}: {faq['question']}\n")
                f.write("-" * 50 + "\n")
                f.write(f"A{i}: {faq['answer']}\n\n")
                f.write("=" * 80 + "\n\n")

def main():
    try:
        # Initialize AI cleaner
        cleaner = AIFAQCleaner()
        
        input_file = 'data/scraped-content-faqs.txt'
        output_file = 'data/scraped-content-faqs-ai-cleaned.txt'
        
        # Clean FAQs using AI
        cleaner.clean_faq_file(input_file, output_file, batch_size=8)  # Smaller batches for better accuracy
        
        # Replace original file with cleaned version
        if os.path.exists(output_file):
            os.replace(output_file, input_file)
            print(f"✅ Original file updated with AI-cleaned version")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()