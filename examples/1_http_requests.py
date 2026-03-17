#!/usr/bin/env python3
import time

try:
    import requests
except ImportError:
    print("requests not installed. Install with: pip install requests")
    raise

from faultcore import rate, timeout


@rate(rate="10mbps")
def fetch_github_api():
    response = requests.get("https://api.github.com/repos/python/cpython", timeout=10)
    return response.json()


@rate(rate="5mbps")
def fetch_health():
    response = requests.get("https://httpbin.org/get", timeout=10)
    return response.status_code


@timeout(connect="500ms")
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
    start = time.perf_counter()
    try:
        status = fetch_plain()
        print(f"Status: {status}")
    except Exception as exc:
        print(f"Error: {exc}")
    print(f"Time: {time.perf_counter() - start:.3f}s\n")

    print("--- Rate Setting (10 Mbps equivalent) ---")
    start = time.perf_counter()
    for attempt in range(1, 6):
        try:
            result = fetch_github_api()
            print(f"Request {attempt}: OK - {result.get('full_name', 'N/A')}")
        except Exception as exc:
            print(f"Request {attempt}: Error - {type(exc).__name__}")
    print(f"Total time: {time.perf_counter() - start:.3f}s\n")

    print("--- Rate Setting (5 Mbps equivalent) with httpbin ---")
    start = time.perf_counter()
    for attempt in range(1, 6):
        try:
            status = fetch_health()
            print(f"Request {attempt}: Status {status}")
        except Exception as exc:
            print(f"Request {attempt}: Error - {type(exc).__name__}")
    print(f"Total time: {time.perf_counter() - start:.3f}s\n")

    print("--- With Latency Injection (500ms) ---")
    start = time.perf_counter()
    try:
        status = fetch_with_latency()
        print(f"Status: {status}")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print(f"Time: {time.perf_counter() - start:.3f}s\n")

    print("These examples require the interceptor loaded via LD_PRELOAD.")
    print("Build the interceptor first: ./build.sh")
    print("Run with: faultcore run -- python examples/1_http_requests.py")
    print("Or use: examples/run_with_preload.sh 1_http_requests.py")
    print("\nDone.")
