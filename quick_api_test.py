#!/usr/bin/env python3
"""
Quick Test for IST Chatbot - Test basic functionality and get real timing data
"""

import requests
import time
import json

API_BASE_URL = "http://localhost:8001"

def test_basic_functionality():
    """Test basic API functionality with simple queries"""
    
    print("🔍 Testing Basic API Functionality")
    print("=" * 50)
    
    # Test health endpoint
    try:
        start = time.time()
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)
        health_time = time.time() - start
        
        print(f"Health Check: {health_time:.3f}s - Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"Health Check Failed: {e}")
        return
    
    # Test simple queries that should work quickly
    simple_queries = [
        "Hi",
        "Hello", 
        "Test",
        "What is IST?"
    ]
    
    print(f"\n🔍 Testing {len(simple_queries)} Simple Queries")
    print("-" * 50)
    
    results = []
    for i, query in enumerate(simple_queries, 1):
        try:
            start = time.time()
            response = requests.post(
                f"{API_BASE_URL}/api/chat",
                json={"message": query},
                timeout=15
            )
            response_time = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    "query": query,
                    "response_time": response_time,
                    "status": "success",
                    "response_length": len(data.get("response", "")),
                    "sources": len(data.get("sources", [])),
                    "session_id": data.get("session_id", "")
                }
                print(f"Query {i}: {query:<15} -> {response_time:.3f}s, {result['response_length']} chars, {result['sources']} sources")
                results.append(result)
            else:
                print(f"Query {i}: {query:<15} -> ERROR {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"Query {i}: {query:<15} -> TIMEOUT (>15s)")
        except Exception as e:
            print(f"Query {i}: {query:<15} -> ERROR: {e}")
    
    # Test one complex query with longer timeout
    print(f"\n🔍 Testing 1 Complex Query (longer timeout)")
    print("-" * 50)
    
    try:
        complex_query = "What is computer science?"
        start = time.time()
        response = requests.post(
            f"{API_BASE_URL}/api/chat",
            json={"message": complex_query},
            timeout=60
        )
        response_time = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            result = {
                "query": complex_query,
                "response_time": response_time,
                "status": "success",
                "response_length": len(data.get("response", "")),
                "sources": len(data.get("sources", [])),
                "session_id": data.get("session_id", "")
            }
            print(f"Complex Query: {response_time:.3f}s, {result['response_length']} chars, {result['sources']} sources")
            print(f"Sample Response: {data.get('response', '')[:100]}...")
            results.append(result)
        else:
            print(f"Complex Query: ERROR {response.status_code}")
            print(f"Error Details: {response.text}")
            
    except requests.exceptions.Timeout:
        print("Complex Query: TIMEOUT (>60s)")
    except Exception as e:
        print(f"Complex Query: ERROR: {e}")
    
    # Summary
    if results:
        response_times = [r["response_time"] for r in results]
        successful_queries = len(results)
        avg_time = sum(response_times) / len(response_times)
        
        print(f"\n📊 Summary for Thesis:")
        print("-" * 30)
        print(f"Successful queries: {successful_queries}")
        print(f"Average response time: {avg_time:.3f} seconds")
        print(f"Fastest response: {min(response_times):.3f} seconds")
        print(f"Slowest response: {max(response_times):.3f} seconds")
        
        # Save results for thesis
        test_results = {
            "timestamp": time.time(),
            "test_type": "basic_functionality",
            "summary_stats": {
                "successful_queries": successful_queries,
                "average_response_time": avg_time,
                "min_response_time": min(response_times),
                "max_response_time": max(response_times),
                "response_times": response_times
            },
            "detailed_results": results
        }
        
        with open("basic_test_results.json", "w") as f:
            json.dump(test_results, f, indent=2)
        
        print(f"📁 Results saved to: basic_test_results.json")
        
        # Recommendations for thesis
        print(f"\n📝 For Your Thesis:")
        print(f"   - Use average response time: {avg_time:.3f}s")
        print(f"   - Mention range: {min(response_times):.3f}s to {max(response_times):.3f}s")
        print(f"   - Success rate: {successful_queries}/5 queries tested")
        
    else:
        print("\n No successful queries - check server configuration")

if __name__ == "__main__":
    test_basic_functionality()