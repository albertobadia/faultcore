#!/usr/bin/env python3
import argparse
import socket
import sys
import time
from datetime import datetime


def test_latency(host: str, port: int, message: str, count: int = 10):
    print(f"[{datetime.now().isoformat()}] Testing latency to {host}:{port}")
    print(f"Message: '{message}', Count: {count}")
    print("-" * 60)

    latencies = []

    for i in range(count):
        try:
            start = time.perf_counter()

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host, port))

            sock.sendall(f"{message}\n".encode())

            response = sock.recv(4096)
            sock.close()

            end = time.perf_counter()
            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

            print(f"[{i + 1}/{count}] Latency: {latency_ms:.2f}ms - Response: {response.decode('utf-8').strip()}")

        except TimeoutError:
            print(f"[{i + 1}/{count}] TIMEOUT")
        except Exception as e:
            print(f"[{i + 1}/{count}] ERROR: {e}")

        time.sleep(0.1)

    if latencies:
        avg = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        print("-" * 60)
        print(f"Average latency: {avg:.2f}ms")
        print(f"Min latency: {min_lat:.2f}ms")
        print(f"Max latency: {max_lat:.2f}ms")
        return avg
    return None


def test_connect_timeout(host: str, port: int, timeout_sec: float = 5.0):
    print(f"[{datetime.now().isoformat()}] Testing connect timeout to {host}:{port}")
    print(f"Expected timeout: {timeout_sec} seconds")
    print("-" * 60)

    start = time.perf_counter()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        sock.connect((host, port))

        end = time.perf_counter()
        elapsed = end - start

        print(f"Connected in {elapsed:.2f} seconds")
        sock.close()
        return elapsed

    except TimeoutError:
        end = time.perf_counter()
        elapsed = end - start
        print(f"Connection timed out after {elapsed:.2f} seconds (expected: {timeout_sec}s)")
        return elapsed
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_recv_timeout(host: str, port: int, timeout_sec: float = 3.0):
    print(f"[{datetime.now().isoformat()}] Testing recv timeout to {host}:{port}")
    print(f"Expected timeout: {timeout_sec} seconds")
    print("-" * 60)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((host, port))

        sock.sendall(b"WAIT\n")

        start = time.perf_counter()
        try:
            response = sock.recv(4096)
            end = time.perf_counter()
            elapsed = end - start
            print(f"Received response in {elapsed:.2f} seconds: {response}")
            sock.close()
            return elapsed
        except TimeoutError:
            end = time.perf_counter()
            elapsed = end - start
            print(f"Receive timed out after {elapsed:.2f} seconds")
            sock.close()
            return elapsed

    except Exception as e:
        print(f"ERROR: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Latency Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--message", default="Hello FaultCore", help="Message to send")
    parser.add_argument("--count", type=int, default=10, help="Number of messages")
    parser.add_argument(
        "--mode", choices=["latency", "connect-timeout", "recv-timeout"], default="latency", help="Test mode"
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout in seconds")
    args = parser.parse_args()

    result = None
    if args.mode == "latency":
        result = test_latency(args.host, args.port, args.message, args.count)
    elif args.mode == "connect-timeout":
        result = test_connect_timeout(args.host, args.port, args.timeout)
    elif args.mode == "recv-timeout":
        result = test_recv_timeout(args.host, args.port, args.timeout)

    if result is None:
        sys.exit(1)
