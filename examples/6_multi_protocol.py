#!/usr/bin/env python3
import socket
import time
from collections.abc import Callable
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from faultcore import rate, timeout


def tcp_echo(host: str, port: int, message: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect((host, port))
        sock.sendall(message.encode())
        response = sock.recv(1024)
        return response.decode().strip()


@rate("10mbps")
def rate_limited_tcp(host: str, port: int, message: str) -> str:
    return tcp_echo(host, port, message)


@rate("5mbps")
def rate_limited_http(url: str) -> int:
    if requests is None:
        raise ImportError("requests is not installed")
    response = requests.get(url, timeout=10)
    return response.status_code


@timeout(connect="250ms")
def latency_injected_call(callable_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return callable_func(*args, **kwargs)


def combined_test_scenario(host: str, tcp_port: int) -> dict[str, str | int]:
    results: dict[str, str | int] = {}

    print("\n--- Scenario 1: Rate-limited TCP + HTTP ---")
    start = time.perf_counter()

    tcp_result = rate_limited_tcp(host, tcp_port, "TCP Test")
    results["tcp"] = tcp_result
    print(f"TCP: {tcp_result}")

    if requests is not None:
        http_result = rate_limited_http("https://httpbin.org/get")
        results["http"] = http_result
        print(f"HTTP: {http_result}")

    print(f"Total: {time.perf_counter() - start:.3f}s")
    return results


def latency_scenario(host: str, tcp_port: int) -> None:
    print("\n--- Scenario 2: Latency injection on multiple protocols ---")

    print("TCP with 250ms latency:")
    start = time.perf_counter()
    try:
        result = latency_injected_call(tcp_echo, host, tcp_port, "Latency test")
        print(f"  Result: {result}")
        print(f"  Time: {(time.perf_counter() - start) * 1000:.1f}ms")
    except Exception as exc:
        print(f"  Error: {type(exc).__name__}: {exc}")

    if requests is not None:
        print("HTTP with 250ms latency:")
        start = time.perf_counter()
        try:
            result = latency_injected_call(lambda: requests.get("https://httpbin.org/get", timeout=10))
            print(f"  Status: {result.status_code}")
            print(f"  Time: {(time.perf_counter() - start) * 1000:.1f}ms")
        except Exception as exc:
            print(f"  Error: {type(exc).__name__}: {exc}")


def burst_scenario(host: str, tcp_port: int) -> None:
    print("\n--- Scenario 3: Burst traffic simulation ---")

    print("Sending 10 rapid requests (should be rate limited):")
    start = time.perf_counter()
    for attempt in range(10):
        req_start = time.perf_counter()
        try:
            result = tcp_echo(host, tcp_port, f"Burst {attempt}")
            elapsed = (time.perf_counter() - req_start) * 1000
            print(f"  Request {attempt + 1}: {elapsed:.1f}ms - {result}")
        except Exception as exc:
            elapsed = (time.perf_counter() - req_start) * 1000
            print(f"  Request {attempt + 1}: {elapsed:.1f}ms - ERROR: {type(exc).__name__}")
    print(f"Total: {time.perf_counter() - start:.3f}s")


def mixed_policy_scenario(host: str, tcp_port: int) -> None:
    print("\n--- Scenario 4: Mixed policies (rate limit + latency) ---")

    @rate("3mbps")
    @timeout(connect="150ms")
    def throttled_and_slow_call(msg: str) -> str:
        return tcp_echo(host, tcp_port, msg)

    start = time.perf_counter()
    for attempt in range(3):
        req_start = time.perf_counter()
        try:
            result = throttled_and_slow_call(f"Mixed {attempt}")
            elapsed = (time.perf_counter() - req_start) * 1000
            print(f"  Request {attempt + 1}: {elapsed:.1f}ms - {result}")
        except Exception as exc:
            elapsed = (time.perf_counter() - req_start) * 1000
            print(f"  Request {attempt + 1}: {elapsed:.1f}ms - ERROR: {type(exc).__name__}")
    print(f"Total: {time.perf_counter() - start:.3f}s")


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
    print("  uv run python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Load the interceptor: LD_PRELOAD=./src/faultcore/_native/<platform>/libfaultcore_interceptor.so")
    print("Or use: examples/run_with_preload.sh 6_multi_protocol.py")
    print("\n" + "=" * 60)
    print(" All scenarios completed! ".center(60, "="))
    print("=" * 60)
