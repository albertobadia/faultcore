#!/usr/bin/env python3
import time

try:
    import requests
except ImportError:
    print("requests not installed. Install with: pip install requests")
    raise

from faultcore import connect_timeout, rate_limit


@rate_limit(rate=10)
def fetch_github_api():
    response = requests.get("https://api.github.com/repos/python/cpython", timeout=10)
    return response.json()


@rate_limit(rate=5)
def fetch_health():
    response = requests.get("https://httpbin.org/get", timeout=10)
    return response.status_code


@connect_timeout(timeout_ms=500)
def fetch_with_latency():
    response = requests.get("https://httpbin.org/delay/1", timeout=10)
    return response.status_code


def fetch_plain():
    response = requests.get("https://httpbin.org/get", timeout=10)
    return response.status_code


if __name__ == "__main__":
    print("=" * 60)
    print(" HTTP Examples with faultcore ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Plain HTTP Request (no fault injection) ---")
    start = time.time()
    try:
        status = fetch_plain()
        print(f"Status: {status}")
    except Exception as e:
        print(f"Error: {e}")
    print(f"Time: {time.time() - start:.3f}s\n")

    print("--- Rate Setting (10 Mbps equivalent) ---")
    start = time.time()
    for i in range(5):
        try:
            result = fetch_github_api()
            print(f"Request {i + 1}: OK - {result.get('full_name', 'N/A')}")
        except Exception as e:
            print(f"Request {i + 1}: Error - {type(e).__name__}")
    print(f"Total time: {time.time() - start:.3f}s\n")

    print("--- Rate Setting (5 Mbps equivalent) with httpbin ---")
    start = time.time()
    for i in range(5):
        try:
            status = fetch_health()
            print(f"Request {i + 1}: Status {status}")
        except Exception as e:
            print(f"Request {i + 1}: Error - {type(e).__name__}")
    print(f"Total time: {time.time() - start:.3f}s\n")

    print("--- With Latency Injection (500ms) ---")
    start = time.time()
    try:
        status = fetch_with_latency()
        print(f"Status: {status}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
    print(f"Time: {time.time() - start:.3f}s\n")

    print("These examples require the interceptor loaded via LD_PRELOAD.")
    print("Build the interceptor first: ./build.sh")
    print("\nDone.")
