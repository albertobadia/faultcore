#!/usr/bin/env python3
import argparse
import socket
import time
from datetime import datetime


def test_bandwidth_send(host: str, port: int, data_size: int, duration_sec: float = 5.0):
    print(f"[{datetime.now().isoformat()}] Testing bandwidth (send) to {host}:{port}")
    print(f"Data size: {data_size} bytes, Duration: {duration_sec} seconds")
    print("-" * 60)

    data = b"x" * data_size
    total_sent = 0
    start_time = time.perf_counter()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(duration_sec + 5)
        sock.connect((host, port))

        print(f"Connected. Starting to send {data_size}-byte chunks...")

        while time.perf_counter() - start_time < duration_sec:
            try:
                sock.sendall(data)
                total_sent += data_size
            except Exception as e:
                print(f"Send error: {e}")
                break

        sock.close()

    except Exception as e:
        print(f"Connection error: {e}")
        return None

    end_time = time.perf_counter()
    elapsed = end_time - start_time
    bytes_per_sec = total_sent / elapsed if elapsed > 0 else 0
    mbits_per_sec = (bytes_per_sec * 8) / (1024 * 1024)

    print(f"Total sent: {total_sent} bytes in {elapsed:.2f} seconds")
    print(f"Bandwidth: {bytes_per_sec:.2f} bytes/s ({mbits_per_sec:.4f} Mbps)")

    return bytes_per_sec


def test_bandwidth_recv(host: str, port: int, duration_sec: float = 5.0):
    print(f"[{datetime.now().isoformat()}] Testing bandwidth (receive) from {host}:{port}")
    print(f"Duration: {duration_sec} seconds")
    print("-" * 60)

    total_received = 0
    start_time = time.perf_counter()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(duration_sec + 5)
        sock.connect((host, port))

        sock.sendall(b"STREAM\n")

        print("Receiving data...")

        while time.perf_counter() - start_time < duration_sec:
            try:
                data = sock.recv(8192)
                if not data:
                    break
                total_received += len(data)
            except TimeoutError:
                break
            except Exception as e:
                print(f"Receive error: {e}")
                break

        sock.close()

    except Exception as e:
        print(f"Connection error: {e}")
        return None

    end_time = time.perf_counter()
    elapsed = end_time - start_time
    bytes_per_sec = total_received / elapsed if elapsed > 0 else 0
    mbits_per_sec = (bytes_per_sec * 8) / (1024 * 1024)

    print(f"Total received: {total_received} bytes in {elapsed:.2f} seconds")
    print(f"Bandwidth: {bytes_per_sec:.2f} bytes/s ({mbits_per_sec:.4f} Mbps)")

    return bytes_per_sec


def test_throughput(host: str, port: int, num_messages: int = 100):
    print(f"[{datetime.now().isoformat()}] Testing throughput to {host}:{port}")
    print(f"Number of messages: {num_messages}")
    print("-" * 60)

    start_time = time.perf_counter()
    successful = 0

    for i in range(num_messages):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))

            message = f"MESSAGE_{i:04d}_" + "x" * 100 + "\n"
            sock.sendall(message.encode("utf-8"))

            response = sock.recv(4096)
            sock.close()

            if response:
                successful += 1

        except Exception as e:
            print(f"Error on message {i}: {e}")

    end_time = time.perf_counter()
    elapsed = end_time - start_time
    msgs_per_sec = successful / elapsed if elapsed > 0 else 0

    print(f"Successful: {successful}/{num_messages}")
    print(f"Time: {elapsed:.2f} seconds")
    print(f"Throughput: {msgs_per_sec:.2f} msgs/s")

    return msgs_per_sec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore Bandwidth Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--mode", choices=["send", "recv", "throughput"], default="send", help="Test mode")
    parser.add_argument("--size", type=int, default=1024, help="Data size for send test")
    parser.add_argument("--duration", type=float, default=5.0, help="Test duration in seconds")
    parser.add_argument("--messages", type=int, default=100, help="Number of messages for throughput")
    args = parser.parse_args()

    if args.mode == "send":
        test_bandwidth_send(args.host, args.port, args.size, args.duration)
    elif args.mode == "recv":
        test_bandwidth_recv(args.host, args.port, args.duration)
    elif args.mode == "throughput":
        test_throughput(args.host, args.port, args.messages)
