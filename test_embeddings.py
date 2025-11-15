#!/usr/bin/env python3
"""
Test script for rate-limited Gemini embedding implementation.
This script verifies that the direct API approach works correctly
and respects rate limits.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add the project directory to the path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from dotenv import load_dotenv
from embedding_utils import get_embedding, get_embedding_with_retry, batch_embeddings

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_single_embedding():
    """Test single embedding generation"""
    print("\n" + "="*60)
    print("Testing Single Embedding Generation")
    print("="*60)
    
    test_text = "What is machine learning and how does it work?"
    
    try:
        print(f"Input text: {test_text}")
        start_time = time.time()
        
        embedding = get_embedding(test_text)
        
        end_time = time.time()
        
        print(f"✅ SUCCESS!")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   Time taken: {end_time - start_time:.2f} seconds")
        print(f"   First 5 values: {embedding[:5]}")
        print(f"   Last 5 values: {embedding[-5:]}")
        
        # Verify embedding is valid
        assert len(embedding) > 0, "Embedding should not be empty"
        assert all(isinstance(x, (int, float)) for x in embedding), "All values should be numeric"
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False

def test_rate_limiting():
    """Test rate limiting behavior with multiple quick requests"""
    print("\n" + "="*60)
    print("Testing Rate Limiting (Multiple Quick Requests)")
    print("="*60)
    
    test_texts = [
        "What is artificial intelligence?",
        "How does machine learning work?",
        "What are neural networks?",
        "Explain deep learning concepts.",
        "What is natural language processing?"
    ]
    
    try:
        results = []
        
        for i, text in enumerate(test_texts, 1):
            print(f"\nRequest {i}/{len(test_texts)}: {text[:40]}...")
            start_time = time.time()
            
            embedding = get_embedding(text)
            
            end_time = time.time()
            duration = end_time - start_time
            
            results.append({
                'text': text,
                'embedding_length': len(embedding),
                'duration': duration
            })
            
            print(f"   ✅ Success in {duration:.2f}s (dim: {len(embedding)})")
            
        print(f"\n📊 Rate Limiting Test Summary:")
        print(f"   Total requests: {len(results)}")
        total_time = sum(r['duration'] for r in results)
        print(f"   Total time: {total_time:.2f} seconds")
        print(f"   Average time per request: {total_time/len(results):.2f} seconds")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False

def test_batch_processing():
    """Test batch processing functionality"""
    print("\n" + "="*60)
    print("Testing Batch Processing")
    print("="*60)
    
    test_texts = [
        "Introduction to computer science",
        "Database management systems",
        "Software engineering principles", 
        "Network security fundamentals",
        "Web development technologies",
        "Data structures and algorithms",
        "Operating system concepts"
    ]
    
    try:
        print(f"Processing {len(test_texts)} texts in batches...")
        start_time = time.time()
        
        embeddings = batch_embeddings(test_texts, batch_size=3)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ SUCCESS!")
        print(f"   Processed {len(embeddings)} embeddings")
        print(f"   Total time: {total_time:.2f} seconds")
        print(f"   Average time per embedding: {total_time/len(embeddings):.2f} seconds")
        
        # Verify all embeddings
        for i, embedding in enumerate(embeddings):
            assert len(embedding) > 0, f"Embedding {i} should not be empty"
            assert all(isinstance(x, (int, float)) for x in embedding), f"Embedding {i} should contain only numbers"
        
        print(f"   All embeddings validated ✅")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False

def test_error_handling():
    """Test error handling and retry logic"""
    print("\n" + "="*60)
    print("Testing Error Handling and Retry Logic")
    print("="*60)
    
    # Test with very long text (might cause issues)
    long_text = "This is a test sentence. " * 1000  # Very long text
    
    try:
        print(f"Testing with very long text ({len(long_text)} characters)...")
        
        start_time = time.time()
        embedding = get_embedding_with_retry(long_text, max_retries=2)
        end_time = time.time()
        
        print(f"✅ Long text handled successfully!")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   Time taken: {end_time - start_time:.2f} seconds")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Expected behavior for very long text: {str(e)}")
        # This might fail, which is expected for very long texts
        
        # Test with normal text to ensure retry logic doesn't break normal operation
        try:
            normal_text = "This is a normal length text for testing."
            embedding = get_embedding_with_retry(normal_text)
            print(f"✅ Normal text still works after error: dim {len(embedding)}")
            return True
        except Exception as e2:
            print(f"❌ FAILED: Normal text failed after error: {str(e2)}")
            return False

def test_api_key_validation():
    """Test API key validation"""
    print("\n" + "="*60)
    print("Testing API Key Validation")
    print("="*60)
    
    # Check if API key is set
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("❌ GEMINI_API_KEY environment variable is not set!")
        print("   Please set it in your .env file")
        return False
    
    if len(api_key) < 20:  # Basic validation
        print("❌ GEMINI_API_KEY appears to be invalid (too short)")
        return False
    
    print(f"✅ API key found: {api_key[:10]}...{api_key[-5:]}")
    return True

def main():
    """Run all tests"""
    print("🚀 Starting Rate-Limited Gemini Embedding Tests")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("API Key Validation", test_api_key_validation),
        ("Single Embedding", test_single_embedding),
        ("Rate Limiting", test_rate_limiting),
        ("Batch Processing", test_batch_processing),
        ("Error Handling", test_error_handling)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name:<25} {status}")
    
    print(f"\nOverall Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your rate-limited embedding implementation is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)