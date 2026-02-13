import requests
import sys

BASE_URL = "http://127.0.0.1:5000"

def check_route(method, endpoint, data=None, expected_status=200):
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == 'GET':
            response = requests.get(url)
        elif method == 'POST':
            response = requests.post(url, json=data)
        
        if response.status_code == expected_status:
            print(f"[PASS] {method} {endpoint}")
            return True
        else:
            print(f"[FAIL] {method} {endpoint} - Failed (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"[FAIL] {method} {endpoint} - Error: {e}")
        return False

def main():
    print("--- Checking Current Site Stability ---")
    
    # 1. Home Page
    if not check_route('GET', '/'):
        print("CRITICAL: Home page not accessible!")
        sys.exit(1)
        
    # 2. Options (CORS check)
    check_route('OPTIONS', '/api/auth/login', expected_status=204)
    
    # 3. API Health (Menu)
    # Using /api/menu/all as we fixed it recently
    check_route('GET', '/api/menu/all')
    
    print("\n--- Basic Health Checks Complete ---\n")

if __name__ == "__main__":
    main()
