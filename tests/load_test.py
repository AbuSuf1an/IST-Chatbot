#!/usr/bin/env python3
"""
Simple Load Test for IST Chatbot
Tests concurrent users to measure system performance under load
"""

import requests
import time
import threading
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
API_BASE_URL = "http://localhost:8001"
TIMEOUT = 30

class LoadTestUser:
    def __init__(self, user_id):
        self.user_id = user_id
        self.session_id = f"load_test_user_{user_id}"
        self.results = []
    
    def send_query(self, message):
        """Send a single query and record the result"""
        try:
            start_time = time.time()
            response = requests.post(
                f"{API_BASE_URL}/api/chat",
                json={
                    "message": message,
                    "session_id": self.session_id
                },
                timeout=TIMEOUT
            )
            response_time = time.time() - start_time
            
            result = {
                "user_id": self.user_id,
                "query": message,
                "response_time": response_time,
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "timestamp": time.time()
            }
            
            if response.status_code == 200:
                data = response.json()
                result["response_length"] = len(data.get("response", ""))
                result["sources_count"] = len(data.get("sources", []))
            
            return result
            
        except Exception as e:
            return {
                "user_id": self.user_id,
                "query": message,
                "response_time": TIMEOUT,
                "status_code": 0,
                "success": False,
                "error": str(e),
                "timestamp": time.time()
            }
    
    def simulate_user_session(self):
        """Simulate a typical user session"""
        queries = [
            "Hello",
            "What are the admission requirements?",
            "Tell me more about CSE program",
            "What are the fees?",
            "Thank you"
        ]
        
        for query in queries:
            result = self.send_query(query)
            self.results.append(result)
            # Small delay between queries (realistic user behavior)
            time.sleep(0.5)
        
        return self.results

def run_load_test(num_users=5, duration_seconds=30):
    """Run load test with specified number of concurrent users"""
    
    print(f"🔄 Starting Load Test: {num_users} concurrent users for {duration_seconds} seconds")
    print("=" * 70)
    
    # Check if server is available
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server not available!")
            return None
    except:
        print("❌ Server not available!")
        return None
    
    print("✅ Server is available, starting load test...")
    
    all_results = []
    start_time = time.time()
    end_time = start_time + duration_seconds
    
    # Function to run continuous queries for one user
    def user_load_worker(user_id):
        user = LoadTestUser(user_id)
        user_results = []
        
        queries = [
            "What are admission requirements?",
            "Tell me about courses",
            "What are the facilities?",
            "How to apply?",
            "What are the fees?"
        ]
        
        query_index = 0
        while time.time() < end_time:
            query = queries[query_index % len(queries)]
            result = user.send_query(query)
            user_results.append(result)
            query_index += 1
            
            # Small delay between requests
            time.sleep(1)
        
        return user_results
    
    # Start concurrent users
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [executor.submit(user_load_worker, i) for i in range(num_users)]
        
        for future in as_completed(futures):
            try:
                user_results = future.result()
                all_results.extend(user_results)
            except Exception as e:
                print(f"User thread error: {e}")
    
    actual_duration = time.time() - start_time
    
    # Analyze results
    successful_results = [r for r in all_results if r["success"]]
    failed_results = [r for r in all_results if not r["success"]]
    
    if successful_results:
        response_times = [r["response_time"] for r in successful_results]
        
        stats = {
            "test_duration": actual_duration,
            "concurrent_users": num_users,
            "total_requests": len(all_results),
            "successful_requests": len(successful_results),
            "failed_requests": len(failed_results),
            "success_rate": len(successful_results) / len(all_results) * 100 if all_results else 0,
            "requests_per_second": len(all_results) / actual_duration,
            "successful_requests_per_second": len(successful_results) / actual_duration,
            "average_response_time": sum(response_times) / len(response_times),
            "min_response_time": min(response_times),
            "max_response_time": max(response_times),
            "median_response_time": sorted(response_times)[len(response_times) // 2],
        }
        
        # Calculate percentiles
        sorted_times = sorted(response_times)
        stats["95th_percentile"] = sorted_times[int(0.95 * len(sorted_times))]
        stats["99th_percentile"] = sorted_times[int(0.99 * len(sorted_times))]
        
    else:
        stats = {
            "test_duration": actual_duration,
            "concurrent_users": num_users,
            "total_requests": len(all_results),
            "successful_requests": 0,
            "failed_requests": len(failed_results),
            "success_rate": 0,
            "error": "No successful requests"
        }
    
    # Print results
    print("\n" + "=" * 70)
    print("📊 LOAD TEST RESULTS")
    print("=" * 70)
    print(f"Test Duration:           {actual_duration:.1f} seconds")
    print(f"Concurrent Users:        {num_users}")
    print(f"Total Requests:          {stats['total_requests']}")
    print(f"Successful Requests:     {stats['successful_requests']}")
    print(f"Failed Requests:         {stats['failed_requests']}")
    print(f"Success Rate:            {stats['success_rate']:.1f}%")
    
    if successful_results:
        print(f"Requests/Second:         {stats['requests_per_second']:.2f}")
        print(f"Successful Req/Sec:      {stats['successful_requests_per_second']:.2f}")
        print(f"Average Response Time:   {stats['average_response_time']:.3f} seconds")
        print(f"Median Response Time:    {stats['median_response_time']:.3f} seconds")
        print(f"95th Percentile:         {stats['95th_percentile']:.3f} seconds")
        print(f"99th Percentile:         {stats['99th_percentile']:.3f} seconds")
        print(f"Min Response Time:       {stats['min_response_time']:.3f} seconds")
        print(f"Max Response Time:       {stats['max_response_time']:.3f} seconds")
    
    # Save results
    timestamp = datetime.now().isoformat()
    detailed_results = {
        "timestamp": timestamp,
        "test_type": "load_test",
        "api_url": API_BASE_URL,
        "load_test_stats": stats,
        "individual_results": all_results
    }
    
    filename = f"load_test_results_{num_users}users_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(detailed_results, f, indent=2)
    
    print(f"\n📁 Detailed results saved to: {filename}")
    
    return detailed_results

def run_scalability_test():
    """Test with increasing number of users to find limits"""
    print("🔄 Running Scalability Test")
    print("=" * 50)
    
    user_counts = [1, 5, 10, 15, 20, 25]
    test_duration = 20  # seconds per test
    
    scalability_results = []
    
    for num_users in user_counts:
        print(f"\nTesting with {num_users} concurrent users...")
        result = run_load_test(num_users, test_duration)
        if result:
            scalability_results.append({
                "users": num_users,
                "stats": result["load_test_stats"]
            })
        
        # Brief pause between tests
        time.sleep(5)
    
    # Print scalability summary
    print("\n" + "=" * 70)
    print("📈 SCALABILITY TEST SUMMARY")
    print("=" * 70)
    print(f"{'Users':<6} {'Success%':<8} {'Avg Time':<10} {'95th %ile':<10} {'Req/Sec':<8}")
    print("-" * 50)
    
    for result in scalability_results:
        stats = result["stats"]
        if "average_response_time" in stats:
            print(f"{result['users']:<6} {stats['success_rate']:<7.1f}% {stats['average_response_time']:<9.3f}s {stats['95th_percentile']:<9.3f}s {stats['successful_requests_per_second']:<7.1f}")
    
    # Save scalability results
    timestamp = datetime.now().isoformat()
    scalability_data = {
        "timestamp": timestamp,
        "test_type": "scalability_test",
        "results": scalability_results
    }
    
    filename = f"scalability_test_results_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(scalability_data, f, indent=2)
    
    print(f"\n📁 Scalability results saved to: {filename}")
    
    return scalability_data

if __name__ == "__main__":
    # Run single load test
    print("Choose test type:")
    print("1. Single Load Test (10 users, 30 seconds)")
    print("2. Scalability Test (1-25 users)")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "2":
        run_scalability_test()
    else:
        run_load_test(10, 30)