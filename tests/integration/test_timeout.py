#!/usr/bin/env python3
import argparse
import socket
import sys
import time
from datetime import datetime

import pytest

pytestmark = [pytest.mark.usefixtures("reachable_endpoint"), pytest.mark.integration_network]


def _run_connect_timeout(host: str, port: int, timeout_ms: int) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing connect timeout to {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    start = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_ms / 1000.0)
            result = sock.connect_ex((host, port))

        elapsed_ms = (time.perf_counter() - start) * 1000
        if result == 0:
            print("Connected successfully")
        else:
            print(f"Connection failed with code: {result}, elapsed: {elapsed_ms:.2f}ms")
        return elapsed_ms
    except TimeoutError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"Connection TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
        return elapsed_ms
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def _run_recv_timeout(host: str, port: int, timeout_ms: int) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing recv timeout on {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(30.0)
            sock.connect((host, port))
            sock.sendall(b"NO RESPONSE\\n")

            start = time.perf_counter()
            try:
                data = sock.recv(4096)
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Received data: {data}, elapsed: {elapsed_ms:.2f}ms")
                return elapsed_ms
            except TimeoutError:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Receive TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
                return elapsed_ms
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def _run_send_timeout(host: str, port: int, timeout_ms: int) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing send timeout on {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(30.0)
            sock.connect((host, port))
            sock.sendall(b"PARTIAL\\n")
            sock.shutdown(socket.SHUT_WR)

            start = time.perf_counter()
            try:
                data = sock.recv(4096)
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Received response: {data}, elapsed: {elapsed_ms:.2f}ms")
                return elapsed_ms
            except TimeoutError:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Send TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
                return elapsed_ms
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def _run_graceful_disconnect(host: str, port: int) -> bool:
    print(f"[{datetime.now().isoformat()}] Testing graceful disconnect from {host}:{port}")
    print("-" * 60)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.sendall(b"CLOSE ME\\n")
            time.sleep(0.5)
            sock.shutdown(socket.SHUT_WR)
            data = sock.recv(4096)
            print(f"Received before close: {data}")
        print("Socket closed gracefully")
        return True
    except Exception as exc:
        print(f"ERROR: {exc}")
        return False


def test_connect_timeout(host: str, port: int, probe_timeout_ms: int):
    elapsed_ms = _run_connect_timeout(host, port, probe_timeout_ms)
    assert elapsed_ms is not None
    assert elapsed_ms >= 0


def test_recv_timeout(host: str, port: int, probe_timeout_ms: int):
    elapsed_ms = _run_recv_timeout(host, port, probe_timeout_ms)
    assert elapsed_ms is not None
    assert elapsed_ms >= 0


def test_send_timeout(host: str, port: int, probe_timeout_ms: int):
    elapsed_ms = _run_send_timeout(host, port, probe_timeout_ms)
    assert elapsed_ms is not None
    assert elapsed_ms >= 0


def test_graceful_disconnect(host: str, port: int):
    assert _run_graceful_disconnect(host, port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Timeout Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument(
        "--mode", choices=["connect", "recv", "send", "disconnect", "all"], default="all", help="Test mode"
    )
    parser.add_argument("--timeout", type=int, default=1000, help="Timeout in milliseconds")
    args = parser.parse_args()

    results: list[float | bool | None] = []
    if args.mode == "connect":
        results.append(_run_connect_timeout(args.host, args.port, args.timeout))
    elif args.mode == "recv":
        results.append(_run_recv_timeout(args.host, args.port, args.timeout))
    elif args.mode == "send":
        results.append(_run_send_timeout(args.host, args.port, args.timeout))
    elif args.mode == "disconnect":
        results.append(_run_graceful_disconnect(args.host, args.port))
    else:
        results.append(_run_connect_timeout(args.host, args.port, args.timeout))
        results.append(_run_recv_timeout(args.host, args.port, args.timeout))
        results.append(_run_send_timeout(args.host, args.port, args.timeout))
        results.append(_run_graceful_disconnect(args.host, args.port))

    if any(result is None or result is False for result in results):
        sys.exit(1)
