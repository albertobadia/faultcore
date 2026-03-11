#!/usr/bin/env python3
import socket
import time

try:
    import requests
except ImportError:
    requests = None

from faultcore import connect_timeout, rate_limit


def tcp_echo(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(message.encode())
        response = sock.recv(1024)
        return response.decode().strip()
    finally:
        sock.close()


@rate_limit(rate=10)
def rate_limited_tcp(host: str, port: int, message: str):
    return tcp_echo(host, port, message)


@rate_limit(rate=5)
def rate_limited_http(url: str):
    if requests is None:
        raise ImportError("requests is not installed")
    response = requests.get(url, timeout=10)
    return response.status_code


@connect_timeout(timeout_ms=250)
def latency_injected_call(callable_func, *args, **kwargs):
    return callable_func(*args, **kwargs)


def combined_test_scenario(host: str, tcp_port: int):
    results: dict[str, str | int] = {}

    print("\n--- Scenario 1: Rate-limited TCP + HTTP ---")
    start = time.time()

    tcp_result = rate_limited_tcp(host, tcp_port, "TCP Test")
    results["tcp"] = tcp_result
    print(f"TCP: {tcp_result}")

    if requests is not None:
        http_result = rate_limited_http("https://httpbin.org/get")
        results["http"] = http_result
        print(f"HTTP: {http_result}")

    print(f"Total: {time.time() - start:.3f}s")
    return results


def latency_scenario(host: str, tcp_port: int):
    print("\n--- Scenario 2: Latency injection on multiple protocols ---")

    print("TCP with 250ms latency:")
    start = time.time()
    try:
        result = latency_injected_call(tcp_echo, host, tcp_port, "Latency test")
        print(f"  Result: {result}")
        print(f"  Time: {(time.time() - start) * 1000:.1f}ms")
    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")

    if requests is not None:
        print("HTTP with 250ms latency:")
        start = time.time()
        try:
            result = latency_injected_call(lambda: requests.get("https://httpbin.org/get", timeout=10))
            print(f"  Status: {result.status_code}")
            print(f"  Time: {(time.time() - start) * 1000:.1f}ms")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")


def burst_scenario(host: str, tcp_port: int):
    print("\n--- Scenario 3: Burst traffic simulation ---")

    print("Sending 10 rapid requests (should be rate limited):")
    start = time.time()
    for i in range(10):
        req_start = time.time()
        try:
            result = tcp_echo(host, tcp_port, f"Burst {i}")
            elapsed = (time.time() - req_start) * 1000
            print(f"  Request {i + 1}: {elapsed:.1f}ms - {result}")
        except Exception as e:
            elapsed = (time.time() - req_start) * 1000
            print(f"  Request {i + 1}: {elapsed:.1f}ms - ERROR: {type(e).__name__}")
    print(f"Total: {time.time() - start:.3f}s")


def mixed_policy_scenario(host: str, tcp_port: int):
    print("\n--- Scenario 4: Mixed policies (rate limit + latency) ---")

    @rate_limit(rate=3)
    @connect_timeout(timeout_ms=150)
    def throttled_and_slow_call(msg: str):
        return tcp_echo(host, tcp_port, msg)

    start = time.time()
    for i in range(3):
        req_start = time.time()
        try:
            result = throttled_and_slow_call(f"Mixed {i}")
            elapsed = (time.time() - req_start) * 1000
            print(f"  Request {i + 1}: {elapsed:.1f}ms - {result}")
        except Exception as e:
            elapsed = (time.time() - req_start) * 1000
            print(f"  Request {i + 1}: {elapsed:.1f}ms - ERROR: {type(e).__name__}")
    print(f"Total: {time.time() - start:.3f}s")


if __name__ == "__main__":
    print("=" * 60)
    print(" Multi-Protocol Examples with faultcore ".center(60, "="))
    print("=" * 60 + "\n")

    tcp_host = "127.0.0.1"
    tcp_port = 9000

    combined_test_scenario(tcp_host, tcp_port)
    latency_scenario(tcp_host, tcp_port)
    burst_scenario(tcp_host, tcp_port)
    mixed_policy_scenario(tcp_host, tcp_port)

    print("\nNote: Start the TCP echo server first:")
    print("  python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Load the interceptor: LD_PRELOAD=./target/release/libfaultcore_interceptor.so")
    print("\n" + "=" * 60)
    print(" All scenarios completed! ".center(60, "="))
    print("=" * 60)
