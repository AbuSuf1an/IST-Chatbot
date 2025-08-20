import re
import os

def is_valid_faq(question, answer):
    """
    Determine if a FAQ entry is valid and meaningful.
    """
    
    # Skip if question or answer is too short
    if len(question.strip()) < 10 or len(answer.strip()) < 20:
        return False
    
    # Invalid question patterns (navigation elements, webpage elements, etc.)
    invalid_question_patterns = [
        r'^Who is (Skip to content|Sitemap|FAQ|Menu|Search|Loading|Download|View|Submit|Home|About|Contact)[\?\s]*$',
        r'^Who is (Facebook|Youtube|LinkedIn|Twitter)[\?\s]*$',
        r'^Who is (Apr|Jun|Jul|Oct|Dec|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[\?\s]*$',
        r'^Who is (Read|Open|Access|Click|Call|Email|Message)[\?\s]*$',
        r'^Who is (Previous|Next|See More|View Profile|View Courses)[\?\s]*$',
        r'^Who is (Student Clubs|Quick Links|About Us|Archives|Events)[\?\s]*$',
        r'^Who is (Others|Staff|Faculty Members|Alumni|Achievements)[\?\s]*$',
        r'^Who is (Reload document|Open in new tab|Submit|Download)[\?\s]*$',
        r'^Who is (Course Name|Course Teacher|Course|Semester|Year)[\?\s]*$',
        r'^Who is (Degree|University|Subject|Result|Academic Background)[\?\s]*$',
        r'^Who is (Research Areas|Publications|Biography|Academic Awards)[\?\s]*$',
        r'^Who is (B\.Sc\.?|M\.Sc\.?|Ph\.D\.?|MBA|BBA|CSE|ECE|ICT)[\?\s]*$',
        r'^Who is (Statistics|Mathematics|Physics|Chemistry|Computer)[\?\s]*$',
        r'^Who is (Machine Learning|Data Science|AI|Software Engineering)[\?\s]*$',
        r'^Who is (Network Security|Deep Learning|Big data|Web Technology)[\?\s]*$',
        r'^Who is (Marketing|Finance|Accounting|Management|Business Studies)[\?\s]*$',
        r'^Who is (Principal|Director|Professor|Assistant Professor|Lecturer)[\?\s]*$',
        r'^Who is (Department of|Faculty of|Institute of)[\?\s]*$',
        r'^Who is (Administration Staff|Library Staff|Lab Staff|Accounts Staff)[\?\s]*$',
        r'^Who is (Admission|Fee Structure|Tuition Fees|Scholarship)[\?\s]*$',
        r'^Who is (Notice|Result|Routine|Schedule|Exam|Class)[\?\s]*$',
        r'^Who is (Lab|Library|Computer Lab|Electronics Lab|Networking Lab)[\?\s]*$',
        r'^Who is (Windows OS|LAN Connection|Wireless Connection|Access Point)[\?\s]*$',
        r'^Who is (CONCLUSION|Alumni|Welcome|Admission|Courses)[\?\s]*$',
        r'^Who is (Name|Email|Message|Address|Phone|Contact)[\?\s]*$',
        r'^Who is (Total|Position|Batch|Year|Class|Division)[\?\s]*$',
        r'^Who is (First Class|National University|University of Dhaka)[\?\s]*$',
        r'^Who is (Passing Year|Academic Background|Conference Papers)[\?\s]*$',
        r'^What is the (URL|TITLE|Password|Network SSID)[\?\s]*$',
        r'^What is the.*\?$' # Many "What is the" questions are also invalid
    ]
    
    # Check if question matches invalid patterns
    for pattern in invalid_question_patterns:
        if re.match(pattern, question.strip(), re.IGNORECASE):
            return False
    
    # Invalid answer patterns (empty, template-like, or meaningless)
    invalid_answer_patterns = [
        r'^\s*$',  # Empty
        r'^.{1,20}\s+is\s+in\s+the\s+\.\s+Contact:\s*[\w@\.]*$',  # Template: "X is  in the . Contact: email"
        r'^.{1,50}\s+in\s+the\s+Department\s+of.*Contact:\s*[\w@\.]*$',  # Another template
        r'^.{1,50}\s+in\s+the\s+\.\s+Contact:\s+info@ist\.edu\.bd$',  # IST template
        r'^Loading\.\.\.$',
        r'^Download$',
        r'^View$',
        r'^Submit$',
        r'^\w+\s+is\s+\w+.*in\s+the\s+\.\s+Contact:.*$'  # Generic template pattern
    ]
    
    # Check if answer matches invalid patterns
    for pattern in invalid_answer_patterns:
        if re.match(pattern, answer.strip(), re.IGNORECASE | re.DOTALL):
            return False
    
    # Additional checks for meaningful content
    if 'Contact: info@ist.edu.bd' in answer and len(answer.replace('Contact: info@ist.edu.bd', '').strip()) < 50:
        return False
    
    # Check if answer is just a template with minimal content
    if answer.count(' in the ') > 0 and answer.count(' Contact:') > 0 and len(answer) < 100:
        return False
    
    return True

def clean_faq_file(input_file, output_file):
    """
    Clean the FAQ file by removing invalid entries.
    """
    
    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        return
    
    print(f"🧹 Cleaning FAQ file: {input_file}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by FAQ sections
    sections = content.split("=" * 80)
    
    valid_faqs = []
    invalid_count = 0
    total_count = 0
    
    for section in sections:
        section = section.strip()
        if not section or len(section) < 50:
            continue
        
        # Extract Q and A
        lines = section.split('\n')
        question = ""
        answer = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith('Q') and ':' in line:
                question = line.split(':', 1)[1].strip()
            elif line.startswith('A') and ':' in line:
                answer = line.split(':', 1)[1].strip()
                break
        
        total_count += 1
        
        # Check if this FAQ is valid
        if question and answer and is_valid_faq(question, answer):
            valid_faqs.append({
                'question': question,
                'answer': answer
            })
        else:
            invalid_count += 1
            if len(question) > 0:  # Only print if we actually found a question
                print(f"🗑️  Removed: Q: {question[:60]}...")
    
    # Write cleaned FAQs
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("IST (Institute of Science and Technology) - Frequently Asked Questions\n")
        f.write("=" * 80 + "\n\n")
        
        for i, faq in enumerate(valid_faqs, 1):
            f.write(f"Q{i}: {faq['question']}\n")
            f.write("-" * 50 + "\n")
            f.write(f"A{i}: {faq['answer']}\n\n")
            f.write("=" * 80 + "\n\n")
    
    print(f"\n📊 Cleaning Summary:")
    print(f"   - Total FAQs processed: {total_count}")
    print(f"   - Valid FAQs kept: {len(valid_faqs)}")
    print(f"   - Invalid FAQs removed: {invalid_count}")
    print(f"   - Removal rate: {invalid_count/total_count*100:.1f}%")
    print(f"✅ Cleaned file saved to: {output_file}")

def main():
    input_file = 'data/scraped-content-faqs.txt'
    output_file = 'data/scraped-content-faqs-cleaned.txt'
    
    clean_faq_file(input_file, output_file)
    
    # Replace the original file with the cleaned one
    if os.path.exists(output_file):
        os.replace(output_file, input_file)
        print(f"✅ Original file updated with cleaned version")

if __name__ == "__main__":
    main()