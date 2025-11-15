"""
Direct Gemini API embedding utility with rate limiting to bypass langchain quota issues.
This module provides a rate-limited implementation of Gemini embeddings that works 
around the free tier batch embedding API limitations.
"""

import requests
import os
import time
import logging
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Rate limiting globals
_last_request_time = 0
_request_count = 0
_minute_start = time.time()

# Configuration
MAX_REQUESTS_PER_MINUTE = 15  # Conservative limit for free tier
MIN_REQUEST_INTERVAL = 2.0    # Minimum seconds between requests
REQUEST_TIMEOUT = 30          # Timeout for API requests

def get_embedding_gemini_rate_limited(text: str, model: str = "models/text-embedding-004") -> List[float]:
    """
    Direct Gemini API call with comprehensive rate limiting.
    
    This function bypasses the langchain wrapper that uses batch embedding APIs
    and instead makes direct REST API calls to avoid free tier quota issues.
    
    Args:
        text (str): Text to embed
        model (str): Embedding model to use
        
    Returns:
        List[float]: Embedding vector
        
    Raises:
        ValueError: If API key is missing or response is invalid
        requests.RequestException: If API request fails
    """
    global _last_request_time, _request_count, _minute_start
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    current_time = time.time()
    
    # Reset counter every minute
    if current_time - _minute_start >= 60:
        _request_count = 0
        _minute_start = current_time
        logger.debug(f"Rate limit counter reset. New minute started.")
    
    # Check if we've hit the per-minute limit
    if _request_count >= MAX_REQUESTS_PER_MINUTE:
        sleep_time = 60 - (current_time - _minute_start)
        if sleep_time > 0:
            logger.warning(f"Rate limit reached ({_request_count}/{MAX_REQUESTS_PER_MINUTE}). "
                          f"Sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
            _request_count = 0
            _minute_start = time.time()
    
    # Ensure minimum interval between requests
    time_since_last = current_time - _last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - time_since_last
        logger.debug(f"Enforcing minimum interval. Sleeping for {sleep_time:.2f} seconds")
        time.sleep(sleep_time)
    
    # Prepare API request
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:embedContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "content": {
            "parts": [{"text": text}]
        }
    }
    
    try:
        logger.debug(f"Making embedding request for text length: {len(text)}")
        response = requests.post(url, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
        
        # Update tracking variables
        _last_request_time = time.time()
        _request_count += 1
        
        # Check response status
        response.raise_for_status()
        
        # Parse response
        result = response.json()
        embedding = result.get("embedding", {}).get("values", [])
        
        if not embedding:
            raise ValueError("No embedding returned from API response")
        
        logger.debug(f"Successfully generated embedding with {len(embedding)} dimensions")
        return embedding
        
    except requests.exceptions.Timeout:
        logger.error("Request timed out")
        raise
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            logger.error("Rate limit exceeded despite local throttling. "
                        "Consider reducing MAX_REQUESTS_PER_MINUTE")
        logger.error(f"HTTP error {response.status_code}: {response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Invalid response format: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during embedding generation: {str(e)}")
        raise

def get_embedding_with_retry(text: str, model: str = "models/text-embedding-004", 
                           max_retries: int = 3) -> List[float]:
    """
    Get embedding with exponential backoff retry logic.
    
    Args:
        text (str): Text to embed
        model (str): Embedding model to use
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        List[float]: Embedding vector
    """
    for attempt in range(max_retries + 1):
        try:
            return get_embedding_gemini_rate_limited(text, model)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries:
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5, 10, 20 seconds
                logger.warning(f"Rate limit hit, attempt {attempt + 1}/{max_retries + 1}. "
                              f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            raise
        except Exception as e:
            if attempt < max_retries:
                wait_time = (attempt + 1) * 2  # Linear backoff for other errors
                logger.warning(f"Embedding failed, attempt {attempt + 1}/{max_retries + 1}. "
                              f"Retrying in {wait_time} seconds... Error: {str(e)}")
                time.sleep(wait_time)
                continue
            raise
    
    raise Exception("All retry attempts failed")

# Alias for easier migration from langchain
def get_embedding(text: str) -> List[float]:
    """
    Main embedding function that replaces langchain GoogleGenerativeAIEmbeddings.embed_query()
    
    Args:
        text (str): Text to embed
        
    Returns:
        List[float]: Embedding vector
    """
    return get_embedding_with_retry(text)

def batch_embeddings(texts: List[str], batch_size: int = 5) -> List[List[float]]:
    """
    Process multiple texts with rate limiting between batches.
    
    Args:
        texts (List[str]): List of texts to embed
        batch_size (int): Number of texts to process before adding delay
        
    Returns:
        List[List[float]]: List of embedding vectors
    """
    embeddings = []
    
    for i, text in enumerate(texts):
        try:
            embedding = get_embedding(text)
            embeddings.append(embedding)
            
            # Add extra delay between batches
            if (i + 1) % batch_size == 0 and i + 1 < len(texts):
                logger.info(f"Processed batch {(i + 1) // batch_size}. "
                           f"Adding 5 second delay before next batch...")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Failed to embed text {i + 1}/{len(texts)}: {str(e)}")
            raise
    
    return embeddings

if __name__ == "__main__":
    # Test the embedding function
    logging.basicConfig(level=logging.INFO)
    
    test_texts = [
        "What is machine learning?",
        "How does artificial intelligence work?",
        "What are the benefits of deep learning?"
    ]
    
    print("Testing rate-limited Gemini embeddings...")
    
    for i, text in enumerate(test_texts):
        try:
            print(f"\nTest {i + 1}: Embedding text: '{text[:50]}...'")
            start_time = time.time()
            
            embedding = get_embedding(text)
            
            end_time = time.time()
            print(f"✅ Success! Embedding length: {len(embedding)}")
            print(f"   Time taken: {end_time - start_time:.2f} seconds")
            print(f"   First 5 values: {embedding[:5]}")
            
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            break
    
    print("\nTesting completed!")