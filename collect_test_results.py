import subprocess
import json
import time
from datetime import datetime

def run_all_tests():
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }
    
    print("🚀 Starting comprehensive testing...")
    
    # 1. Backend Unit Tests
    print("\n1. Running backend unit tests...")
    try:
        result = subprocess.run(
            ["pytest", "tests/", "-v", "--tb=short"], 
            capture_output=True, text=True, timeout=300
        )
        results["tests"]["backend_unit"] = {
            "success": result.returncode == 0,
            "output": result.stdout,
            "duration": "captured in output"
        }
        print("✅ Backend tests completed")
    except Exception as e:
        print(f"❌ Backend tests failed: {e}")
    
    # 2. Frontend Unit Tests
    print("\n2. Running frontend unit tests...")
    try:
        result = subprocess.run(
            ["npx", "jest", "frontend/tests/", "--verbose"], 
            capture_output=True, text=True, timeout=120
        )
        results["tests"]["frontend_unit"] = {
            "success": result.returncode == 0,
            "output": result.stdout
        }
        print("✅ Frontend tests completed")
    except Exception as e:
        print(f"❌ Frontend tests failed: {e}")
    
    # 3. Performance Tests
    print("\n3. Running performance tests...")
    try:
        # Run database performance test
        result = subprocess.run(
            ["python", "database_performance_test.py"], 
            capture_output=True, text=True, timeout=180
        )
        results["tests"]["database_performance"] = {
            "success": result.returncode == 0,
            "output": result.stdout
        }
        print("✅ Performance tests completed")
    except Exception as e:
        print(f"❌ Performance tests failed: {e}")
    
    # Save results to file
    with open(f"test_results_{int(time.time())}.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📊 All test results saved to test_results_{int(time.time())}.json")
    return results

if __name__ == "__main__":
    run_all_tests()