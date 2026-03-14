#!/usr/bin/env python3
import socket
import time

from faultcore import connect_timeout, rate_limit


def send_udp_message(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(message.encode(), (host, port))
        sock.settimeout(1)
        try:
            response, _ = sock.recvfrom(1024)
            return response.decode().strip()
        except TimeoutError:
            return "No response (timeout)"
    finally:
        sock.close()


@rate_limit(rate=10)
def rate_limited_udp(host: str, port: int, message: str):
    return send_udp_message(host, port, message)


@connect_timeout(timeout_ms=100)
def slow_udp(host: str, port: int, message: str):
    return send_udp_message(host, port, message)


if __name__ == "__main__":
    print("=" * 60)
    print(" UDP Client Examples with faultcore ".center(60, "="))
    print("=" * 60 + "\n")

    host = "127.0.0.1"
    port = 9001
    message = "UDP Hello!"

    print(f"--- Plain UDP (server: {host}:{port}) ---")
    start = time.time()
    try:
        response = send_udp_message(host, port, message)
        elapsed = time.time() - start
        print(f"Sent: {message}")
        print(f"Received: {response}")
        print(f"Time: {elapsed * 1000:.1f}ms")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print()

    print("--- UDP with Rate Setting (10 Mbps equivalent) ---")
    start = time.time()
    for i in range(1, 6):
        req_start = time.time()
        try:
            response = rate_limited_udp(host, port, f"UDP {i}")
            elapsed = time.time() - req_start
            print(f"Message {i}: {elapsed * 1000:.1f}ms - {response}")
        except Exception as exc:
            print(f"Message {i}: Error - {type(exc).__name__}")
    print(f"Total time: {time.time() - start:.3f}s")
    print()

    print("--- UDP with Latency Injection (100ms) ---")
    start = time.time()
    try:
        response = slow_udp(host, port, "Slow UDP")
        elapsed = time.time() - start
        print("Sent: Slow UDP")
        print(f"Received: {response}")
        print(f"Time: {elapsed * 1000:.1f}ms")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print()

    print("UDP is connectionless, so interception is applied at socket level.")
    print("For actual UDP server testing, start a UDP echo server on the specified port.")
    print("Load the interceptor: LD_PRELOAD=./target/release/libfaultcore_interceptor.so")
    print("\nDone.")
