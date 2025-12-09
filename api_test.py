#!/usr/bin/env python3
"""
Simple API Performance Test
This script tests the IST Chatbot API performance without complex imports
"""

import requests
import time
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8001"
TIMEOUT = 30  # seconds

def test_api_availability():
    """Check if the API server is running"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200, response.json() if response.status_code == 200 else None
    except requests.exceptions.RequestException as e:
        return False, str(e)

def test_single_query(message, session_id=None):
    """Test a single chat query and return timing info"""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_BASE_URL}/api/chat", 
            json=payload,
            timeout=TIMEOUT
        )
        end_time = time.time()
        
        response_time = end_time - start_time
        
        result = {
            "query": message,
            "response_time": response_time,
            "status_code": response.status_code,
            "success": response.status_code == 200
        }
        
        if response.status_code == 200:
            data = response.json()
            result.update({
                "response_length": len(data.get("response", "")),
                "session_id": data.get("session_id"),
                "sources_count": len(data.get("sources", [])),
                "has_sources": len(data.get("sources", [])) > 0
            })
        else:
            result["error"] = response.text
        
        return result
        
    except requests.exceptions.RequestException as e:
        return {
            "query": message,
            "response_time": TIMEOUT,
            "status_code": 0,
            "success": False,
            "error": str(e)
        }

def run_performance_tests():
    """Run comprehensive performance tests"""
    
    print("🚀 Starting IST Chatbot API Performance Tests")
    print("=" * 60)
    
    # Check API availability
    print("1. Checking API availability...")
    is_available, health_data = test_api_availability()
    
    if not is_available:
        print("❌ API server is not running!")
        print("   Please start the server with: python main.py")
        print(f"   Expected URL: {API_BASE_URL}")
        return None
    
    print("✅ API server is running")
    print(f"   Health check data: {health_data}")
    
    # Test queries
    test_queries = [
        "Hello",
        "What are the admission requirements?", 
        "Tell me about Computer Science Engineering",
        "What courses are offered in CSE?",
        "How do I apply for admission?",
        "What are the campus facilities?",
        "What are the fees for engineering programs?",
        "When is the admission deadline?",
        "Tell me about the faculty",
        "What is the placement record?"
    ]
    
    print(f"\n2. Running {len(test_queries)} test queries...")
    print("-" * 60)
    
    results = []
    for i, query in enumerate(test_queries, 1):
        print(f"   Query {i:2d}: {query[:40]}{'...' if len(query) > 40 else ''}")
        result = test_single_query(query, f"test_session_{i}")
        results.append(result)
        
        if result["success"]:
            print(f"            ✅ {result['response_time']:.3f}s - {result['response_length']} chars - {result['sources_count']} sources")
        else:
            print(f"            ❌ {result['response_time']:.3f}s - Error: {result.get('error', 'Unknown error')}")
    
    # Calculate statistics
    successful_results = [r for r in results if r["success"]]
    response_times = [r["response_time"] for r in successful_results]
    
    if response_times:
        stats = {
            "total_queries": len(test_queries),
            "successful_queries": len(successful_results),
            "success_rate": len(successful_results) / len(test_queries) * 100,
            "average_response_time": sum(response_times) / len(response_times),
            "min_response_time": min(response_times),
            "max_response_time": max(response_times),
            "queries_under_3s": sum(1 for t in response_times if t < 3.0),
            "queries_under_5s": sum(1 for t in response_times if t < 5.0),
            "total_response_length": sum(r["response_length"] for r in successful_results),
            "queries_with_sources": sum(1 for r in successful_results if r["has_sources"]),
        }
        
        # Calculate percentiles
        sorted_times = sorted(response_times)
        stats["95th_percentile"] = sorted_times[int(0.95 * len(sorted_times))] if sorted_times else 0
        stats["median_response_time"] = sorted_times[len(sorted_times) // 2] if sorted_times else 0
        
    else:
        stats = {
            "total_queries": len(test_queries),
            "successful_queries": 0,
            "success_rate": 0,
            "error": "No successful queries"
        }
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE TEST RESULTS")
    print("=" * 60)
    
    if response_times:
        print(f"Total Queries:           {stats['total_queries']}")
        print(f"Successful Queries:      {stats['successful_queries']}")
        print(f"Success Rate:            {stats['success_rate']:.1f}%")
        print(f"Average Response Time:   {stats['average_response_time']:.3f} seconds")
        print(f"Median Response Time:    {stats['median_response_time']:.3f} seconds")
        print(f"95th Percentile:         {stats['95th_percentile']:.3f} seconds")
        print(f"Min Response Time:       {stats['min_response_time']:.3f} seconds")
        print(f"Max Response Time:       {stats['max_response_time']:.3f} seconds")
        print(f"Queries under 3s:        {stats['queries_under_3s']}/{stats['total_queries']} ({stats['queries_under_3s']/stats['total_queries']*100:.1f}%)")
        print(f"Queries under 5s:        {stats['queries_under_5s']}/{stats['total_queries']} ({stats['queries_under_5s']/stats['total_queries']*100:.1f}%)")
        print(f"Queries with sources:    {stats['queries_with_sources']}/{stats['successful_queries']} ({stats['queries_with_sources']/max(1,stats['successful_queries'])*100:.1f}%)")
        print(f"Average response length: {stats['total_response_length']//max(1,stats['successful_queries'])} characters")
    else:
        print("❌ No successful queries - check server status and configuration")
    
    # Save detailed results
    timestamp = datetime.now().isoformat()
    detailed_results = {
        "timestamp": timestamp,
        "api_url": API_BASE_URL,
        "performance_stats": stats,
        "individual_results": results
    }
    
    filename = f"api_performance_test_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(detailed_results, f, indent=2)
    
    print(f"\n📁 Detailed results saved to: {filename}")
    print("   Use these numbers in your thesis Chapter 6 & 7!")
    
    return detailed_results

if __name__ == "__main__":
    run_performance_tests()