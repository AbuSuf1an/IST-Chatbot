import pytest
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    print(f"Health check response: {data}")

def test_chat_endpoint_performance():
    start_time = time.time()
    response = client.post("/api/chat", json={
        "message": "What are the admission requirements for CSE?",
        "session_id": "test_session_123"
    })
    end_time = time.time()
    
    response_time = end_time - start_time
    assert response.status_code == 200
    assert response_time < 10.0  # Should respond within 10 seconds
    
    data = response.json()
    assert "response" in data
    assert "session_id" in data
    
    print(f"Chat response time: {response_time:.2f} seconds")
    print(f"Response length: {len(data['response'])} characters")

def test_multiple_queries():
    """Test multiple different queries to measure accuracy"""
    test_queries = [
        "What are CSE admission requirements?",
        "Tell me about campus facilities",
        "What courses are offered in computer science?",
        "How do I apply for admission?",
        "What are the fees for engineering programs?"
    ]
    
    results = []
    for query in test_queries:
        start_time = time.time()
        response = client.post("/api/chat", json={"message": query})
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            results.append({
                "query": query,
                "response_time": response_time,
                "response_length": len(data.get("response", "")),
                "has_sources": len(data.get("sources", [])) > 0
            })
    
    # Calculate metrics
    avg_response_time = sum(r["response_time"] for r in results) / len(results)
    success_rate = len(results) / len(test_queries) * 100
    
    print(f"Average response time: {avg_response_time:.2f}s")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Queries with sources: {sum(1 for r in results if r['has_sources'])}/{len(results)}")