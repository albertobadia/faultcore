#!/usr/bin/env python3
import argparse
import socket
import sys
import time
from datetime import datetime

import pytest

pytestmark = [pytest.mark.usefixtures("reachable_endpoint"), pytest.mark.integration_network]


def _run_latency(host: str, port: int, message: str, count: int) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing latency to {host}:{port}")
    print(f"Message: '{message}', Count: {count}")
    print("-" * 60)

    latencies: list[float] = []
    for i in range(count):
        try:
            start = time.perf_counter()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10.0)
                sock.connect((host, port))
                sock.sendall(f"{message}\\n".encode())
                response = sock.recv(4096)

            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)
            print(f"[{i + 1}/{count}] Latency: {latency_ms:.2f}ms - Response: {response.decode('utf-8').strip()}")
        except TimeoutError:
            print(f"[{i + 1}/{count}] TIMEOUT")
        except Exception as exc:
            print(f"[{i + 1}/{count}] ERROR: {exc}")
        time.sleep(0.1)

    if not latencies:
        return None

    avg = sum(latencies) / len(latencies)
    print("-" * 60)
    print(f"Average latency: {avg:.2f}ms")
    print(f"Min latency: {min(latencies):.2f}ms")
    print(f"Max latency: {max(latencies):.2f}ms")
    return avg


def _run_connect_timeout(host: str, port: int, timeout_sec: float) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing connect timeout to {host}:{port}")
    print(f"Expected timeout: {timeout_sec} seconds")
    print("-" * 60)

    start = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_sec)
            sock.connect((host, port))
        elapsed = time.perf_counter() - start
        print(f"Connected in {elapsed:.2f} seconds")
        return elapsed
    except TimeoutError:
        elapsed = time.perf_counter() - start
        print(f"Connection timed out after {elapsed:.2f} seconds (expected: {timeout_sec}s)")
        return elapsed
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def _run_recv_timeout(host: str, port: int, timeout_sec: float) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing recv timeout to {host}:{port}")
    print(f"Expected timeout: {timeout_sec} seconds")
    print("-" * 60)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10.0)
            sock.connect((host, port))
            sock.sendall(b"WAIT\\n")

            start = time.perf_counter()
            try:
                response = sock.recv(4096)
                elapsed = time.perf_counter() - start
                print(f"Received response in {elapsed:.2f} seconds: {response}")
                return elapsed
            except TimeoutError:
                elapsed = time.perf_counter() - start
                print(f"Receive timed out after {elapsed:.2f} seconds")
                return elapsed
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def test_latency(host: str, port: int, message: str, probe_count: int) -> None:
    avg_ms = _run_latency(host, port, message, probe_count)
    assert avg_ms is not None
    assert avg_ms >= 0


def test_connect_timeout(host: str, port: int, probe_timeout_sec: float) -> None:
    elapsed = _run_connect_timeout(host, port, probe_timeout_sec)
    assert elapsed is not None
    assert elapsed >= 0


def test_recv_timeout(host: str, port: int, probe_timeout_sec: float) -> None:
    elapsed = _run_recv_timeout(host, port, probe_timeout_sec)
    assert elapsed is not None
    assert elapsed >= 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Latency Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--message", default="Hello FaultCore", help="Message to send")
    parser.add_argument("--count", type=int, default=5, help="Number of messages")
    parser.add_argument(
        "--mode", choices=["latency", "connect-timeout", "recv-timeout", "all"], default="all", help="Test mode"
    )
    parser.add_argument("--timeout", type=float, default=2.0, help="Timeout in seconds")
    args = parser.parse_args()

    results: list[float | None] = []
    if args.mode == "latency":
        results.append(_run_latency(args.host, args.port, args.message, args.count))
    elif args.mode == "connect-timeout":
        results.append(_run_connect_timeout(args.host, args.port, args.timeout))
    elif args.mode == "recv-timeout":
        results.append(_run_recv_timeout(args.host, args.port, args.timeout))
    else:
        results.append(_run_latency(args.host, args.port, args.message, args.count))
        results.append(_run_connect_timeout(args.host, args.port, args.timeout))
        results.append(_run_recv_timeout(args.host, args.port, args.timeout))

    if any(result is None for result in results):
        sys.exit(1)
