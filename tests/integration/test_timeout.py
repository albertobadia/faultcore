#!/usr/bin/env python3
import argparse
import socket
import sys
import time
from datetime import datetime


def test_connect_timeout(host: str, port: int, timeout_ms: int):
    print(f"[{datetime.now().isoformat()}] Testing connect timeout to {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    start = time.perf_counter()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_ms / 1000.0)

        result = sock.connect_ex((host, port))

        if result == 0:
            print("Connected successfully")
            sock.close()
            return 0
        else:
            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000
            print(f"Connection failed with code: {result}, elapsed: {elapsed_ms:.2f}ms")
            sock.close()
            return elapsed_ms

    except TimeoutError:
        end = time.perf_counter()
        elapsed_ms = (end - start) * 1000
        print(f"Connection TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
        return elapsed_ms
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_recv_timeout(host: str, port: int, timeout_ms: int):
    print(f"[{datetime.now().isoformat()}] Testing recv timeout on {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((host, port))

        sock.sendall(b"NO RESPONSE\n")

        start = time.perf_counter()

        try:
            data = sock.recv(4096)
            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000
            print(f"Received data: {data}, elapsed: {elapsed_ms:.2f}ms")
            sock.close()
            return elapsed_ms
        except TimeoutError:
            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000
            print(f"Receive TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
            sock.close()
            return elapsed_ms

    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_send_timeout(host: str, port: int, timeout_ms: int):
    print(f"[{datetime.now().isoformat()}] Testing send timeout on {host}:{port}")
    print(f"Timeout: {timeout_ms}ms")
    print("-" * 60)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((host, port))

        sock.sendall(b"PARTIAL\n")

        sock.shutdown(socket.SHUT_WR)

        start = time.perf_counter()

        try:
            data = sock.recv(4096)
            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000
            print(f"Received response: {data}, elapsed: {elapsed_ms:.2f}ms")
            sock.close()
            return elapsed_ms
        except TimeoutError:
            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000
            print(f"Send TIMED OUT after {elapsed_ms:.2f}ms (expected: {timeout_ms}ms)")
            sock.close()
            return elapsed_ms

    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_graceful_disconnect(host: str, port: int):
    print(f"[{datetime.now().isoformat()}] Testing graceful disconnect from {host}:{port}")
    print("-" * 60)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))

        sock.sendall(b"CLOSE ME\n")

        time.sleep(0.5)

        sock.shutdown(socket.SHUT_WR)

        data = sock.recv(4096)
        print(f"Received before close: {data}")

        sock.close()
        print("Socket closed gracefully")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Timeout Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument(
        "--mode", choices=["connect", "recv", "send", "disconnect"], default="connect", help="Test mode"
    )
    parser.add_argument("--timeout", type=int, default=3000, help="Timeout in milliseconds")
    args = parser.parse_args()

    result = None
    if args.mode == "connect":
        result = test_connect_timeout(args.host, args.port, args.timeout)
    elif args.mode == "recv":
        result = test_recv_timeout(args.host, args.port, args.timeout)
    elif args.mode == "send":
        result = test_send_timeout(args.host, args.port, args.timeout)
    elif args.mode == "disconnect":
        result = test_graceful_disconnect(args.host, args.port)

    if result is None or result is False:
        sys.exit(1)
