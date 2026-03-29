#!/usr/bin/env python3
import argparse
import select
import socket
import sys
import time
from datetime import datetime

import pytest

pytestmark = [pytest.mark.usefixtures("reachable_endpoint"), pytest.mark.integration_network]


def _run_bandwidth_send(host: str, port: int, data_size: int, duration_sec: float) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing bandwidth (send) to {host}:{port}")
    print(f"Data size: {data_size} bytes, Duration: {duration_sec} seconds")
    print("-" * 60)

    data = b"x" * data_size
    total_sent = 0
    start_time = time.perf_counter()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(duration_sec + 5)
            sock.connect((host, port))
            print(f"Connected. Starting to send {data_size}-byte chunks...")

            while time.perf_counter() - start_time < duration_sec:
                try:
                    sock.sendall(data)
                    total_sent += data_size
                    ready, _, _ = select.select([sock], [], [], 0)
                    if ready:
                        _ = sock.recv(4096)
                except Exception as exc:
                    print(f"Send error: {exc}")
                    return None
    except Exception as exc:
        print(f"Connection error: {exc}")
        return None

    elapsed = time.perf_counter() - start_time
    bytes_per_sec = total_sent / elapsed if elapsed > 0 else 0
    mbits_per_sec = (bytes_per_sec * 8) / (1024 * 1024)
    print(f"Total sent: {total_sent} bytes in {elapsed:.2f} seconds")
    print(f"Bandwidth: {bytes_per_sec:.2f} bytes/s ({mbits_per_sec:.4f} Mbps)")
    return None if total_sent == 0 else bytes_per_sec


def _run_bandwidth_recv(host: str, port: int, duration_sec: float) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing bandwidth (receive) from {host}:{port}")
    print(f"Duration: {duration_sec} seconds")
    print("-" * 60)

    total_received = 0
    start_time = time.perf_counter()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(duration_sec + 5)
            sock.connect((host, port))
            sock.sendall(b"STREAM\\n")
            print("Receiving data...")

            while time.perf_counter() - start_time < duration_sec:
                try:
                    data = sock.recv(8192)
                    if not data:
                        break
                    total_received += len(data)
                except TimeoutError:
                    break
                except Exception as exc:
                    print(f"Receive error: {exc}")
                    break
    except Exception as exc:
        print(f"Connection error: {exc}")
        return None

    elapsed = time.perf_counter() - start_time
    bytes_per_sec = total_received / elapsed if elapsed > 0 else 0
    mbits_per_sec = (bytes_per_sec * 8) / (1024 * 1024)
    print(f"Total received: {total_received} bytes in {elapsed:.2f} seconds")
    print(f"Bandwidth: {bytes_per_sec:.2f} bytes/s ({mbits_per_sec:.4f} Mbps)")
    return None if total_received == 0 else bytes_per_sec


def _run_throughput(host: str, port: int, num_messages: int) -> float | None:
    print(f"[{datetime.now().isoformat()}] Testing throughput to {host}:{port}")
    print(f"Number of messages: {num_messages}")
    print("-" * 60)

    start_time = time.perf_counter()
    successful = 0

    for i in range(num_messages):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)
                sock.connect((host, port))
                message = f"MESSAGE_{i:04d}_" + "x" * 100 + "\\n"
                sock.sendall(message.encode("utf-8"))
                response = sock.recv(4096)
                if response:
                    successful += 1
        except Exception as exc:
            print(f"Error on message {i}: {exc}")

    elapsed = time.perf_counter() - start_time
    msgs_per_sec = successful / elapsed if elapsed > 0 else 0
    print(f"Successful: {successful}/{num_messages}")
    print(f"Time: {elapsed:.2f} seconds")
    print(f"Throughput: {msgs_per_sec:.2f} msgs/s")
    return None if successful == 0 else msgs_per_sec


def test_bandwidth_send(host: str, port: int, probe_data_size: int, probe_duration_sec: float):
    bytes_per_sec = _run_bandwidth_send(host, port, probe_data_size, probe_duration_sec)
    assert bytes_per_sec is not None
    assert bytes_per_sec > 0


def test_bandwidth_recv(host: str, port: int, probe_duration_sec: float):
    bytes_per_sec = _run_bandwidth_recv(host, port, probe_duration_sec)
    assert bytes_per_sec is not None
    assert bytes_per_sec > 0


def test_throughput(host: str, port: int, probe_num_messages: int):
    msgs_per_sec = _run_throughput(host, port, probe_num_messages)
    assert msgs_per_sec is not None
    assert msgs_per_sec > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Bandwidth Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--mode", choices=["send", "recv", "throughput", "all"], default="all", help="Test mode")
    parser.add_argument("--size", type=int, default=1024, help="Data size for send test")
    parser.add_argument("--duration", type=float, default=2.0, help="Test duration in seconds")
    parser.add_argument("--messages", type=int, default=20, help="Number of messages for throughput")
    args = parser.parse_args()

    results: list[float | None] = []
    if args.mode == "send":
        results.append(_run_bandwidth_send(args.host, args.port, args.size, args.duration))
    elif args.mode == "recv":
        results.append(_run_bandwidth_recv(args.host, args.port, args.duration))
    elif args.mode == "throughput":
        results.append(_run_throughput(args.host, args.port, args.messages))
    else:
        results.append(_run_bandwidth_send(args.host, args.port, args.size, args.duration))
        results.append(_run_bandwidth_recv(args.host, args.port, args.duration))
        results.append(_run_throughput(args.host, args.port, args.messages))

    if any(result is None for result in results):
        sys.exit(1)
