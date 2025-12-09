import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import time
import json
from fastapi.testclient import TestClient

# Import your main app
try:
    from main import app
    client = TestClient(app)
    APP_AVAILABLE = True
except ImportError as e:
    print(f"Could not import app: {e}")
    APP_AVAILABLE = False

@pytest.mark.skipif(not APP_AVAILABLE, reason="FastAPI app not available")
def test_health_endpoint():
    """Test if the health endpoint is working"""
    start_time = time.time()
    response = client.get("/health")
    response_time = time.time() - start_time
    
    print(f"\n🔍 Health Endpoint Test:")
    print(f"   Response Time: {response_time:.3f} seconds")
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   Response Data: {data}")
    
    assert response.status_code == 200

@pytest.mark.skipif(not APP_AVAILABLE, reason="FastAPI app not available")  
def test_chat_endpoint_simple():
    """Test a simple chat query and measure response time"""
    test_message = "Hello"
    
    start_time = time.time()
    response = client.post("/api/chat", json={
        "message": test_message
    })
    response_time = time.time() - start_time
    
    print(f"\n🔍 Simple Chat Test:")
    print(f"   Query: '{test_message}'")
    print(f"   Response Time: {response_time:.3f} seconds")
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   Response Length: {len(data.get('response', '0'))} characters")
        print(f"   Has Session ID: {'session_id' in data}")
        print(f"   Sources Count: {len(data.get('sources', []))}")
    else:
        print(f"   Error: {response.text}")

@pytest.mark.skipif(not APP_AVAILABLE, reason="FastAPI app not available")
def test_chat_endpoint_complex():
    """Test a complex institutional query"""
    test_message = "What are the admission requirements for Computer Science Engineering?"
    
    start_time = time.time()
    response = client.post("/api/chat", json={
        "message": test_message,
        "session_id": "test_session_001"
    })
    response_time = time.time() - start_time
    
    print(f"\n🔍 Complex Chat Test:")
    print(f"   Query: '{test_message}'")
    print(f"   Response Time: {response_time:.3f} seconds")
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   Response Length: {len(data.get('response', '0'))} characters")
        print(f"   Session ID: {data.get('session_id', 'None')}")
        print(f"   Sources Count: {len(data.get('sources', []))}")
        if data.get('sources'):
            print(f"   Sources: {data['sources']}")
    else:
        print(f"   Error: {response.text}")

@pytest.mark.skipif(not APP_AVAILABLE, reason="FastAPI app not available")
def test_multiple_queries_performance():
    """Test multiple queries to get average performance"""
    test_queries = [
        "Hello",
        "What courses are offered?", 
        "How do I apply for admission?",
        "Tell me about campus facilities",
        "What are the fees?"
    ]
    
    response_times = []
    successful_requests = 0
    
    print(f"\n🔍 Multiple Queries Performance Test:")
    print(f"   Testing {len(test_queries)} queries...")
    
    for i, query in enumerate(test_queries):
        start_time = time.time()
        response = client.post("/api/chat", json={
            "message": query,
            "session_id": f"test_session_{i}"
        })
        response_time = time.time() - start_time
        response_times.append(response_time)
        
        if response.status_code == 200:
            successful_requests += 1
            data = response.json()
            print(f"   Query {i+1}: {response_time:.3f}s - {len(data.get('response', ''))} chars")
        else:
            print(f"   Query {i+1}: {response_time:.3f}s - FAILED ({response.status_code})")
    
    if response_times:
        avg_response_time = sum(response_times) / len(response_times)
        min_response_time = min(response_times)
        max_response_time = max(response_times)
        success_rate = successful_requests / len(test_queries) * 100
        
        print(f"\n📊 Performance Summary:")
        print(f"   Average Response Time: {avg_response_time:.3f} seconds")
        print(f"   Min Response Time: {min_response_time:.3f} seconds")
        print(f"   Max Response Time: {max_response_time:.3f} seconds")
        print(f"   Success Rate: {success_rate:.1f}%")
        print(f"   Total Requests: {len(test_queries)}")
        print(f"   Successful Requests: {successful_requests}")
        
        # Save results to a file for thesis use
        results = {
            "timestamp": time.time(),
            "performance_metrics": {
                "average_response_time": avg_response_time,
                "min_response_time": min_response_time,
                "max_response_time": max_response_time,
                "success_rate": success_rate,
                "total_requests": len(test_queries),
                "successful_requests": successful_requests,
                "individual_response_times": response_times
            }
        }
        
        with open("performance_test_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print(f"   📁 Results saved to: performance_test_results.json")

def test_fallback_without_server():
    """Test what happens if server is not running - for demonstration"""
    print(f"\n🔍 Server Availability Check:")
    if APP_AVAILABLE:
        print("   ✅ FastAPI server connection available")
    else:
        print("   ❌ FastAPI server not available - start with: python main.py")