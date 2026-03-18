#!/usr/bin/env python3
import socket
import time

from faultcore import rate, timeout


def start_echo_client(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(message.encode())
        response = sock.recv(1024)
        return response.decode().strip()
    finally:
        sock.close()


@rate("5mbps")
def rate_limited_echo(host: str, port: int, message: str):
    return start_echo_client(host, port, message)


@timeout(connect="200ms")
def slow_echo(host: str, port: int, message: str):
    return start_echo_client(host, port, message)


if __name__ == "__main__":
    print("=" * 60)
    print(" TCP Client Examples with faultcore ".center(60, "="))
    print("=" * 60 + "\n")

    host = "127.0.0.1"
    port = 9000
    message = "Hello, TCP!"

    print(f"--- Plain TCP Echo (server: {host}:{port}) ---")
    try:
        start = time.time()
        response = start_echo_client(host, port, message)
        elapsed = time.time() - start
        print(f"Sent: {message}")
        print(f"Received: {response}")
        print(f"Time: {elapsed:.3f}s")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the echo server running on port {port}?")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print()

    print("--- TCP Echo with Rate Setting (5 Mbps equivalent) ---")
    try:
        start = time.time()
        for i in range(1, 6):
            req_start = time.time()
            response = rate_limited_echo(host, port, f"Message {i}")
            elapsed = time.time() - req_start
            print(f"Request {i}: {elapsed * 1000:.1f}ms - {response}")
        print(f"Total time: {time.time() - start:.3f}s")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the echo server running on port {port}?")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print()

    print("--- TCP with Latency Injection (200ms) ---")
    try:
        start = time.time()
        response = slow_echo(host, port, "Slow message")
        elapsed = time.time() - start
        print("Sent: Slow message")
        print(f"Received: {response}")
        print(f"Time: {elapsed:.3f}s")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the echo server running on port {port}?")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    print()

    print("Start the echo server first:")
    print("  uv run python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Load the interceptor: LD_PRELOAD=./src/faultcore/_native/<platform>/libfaultcore_interceptor.so")
    print("Or use: examples/run_with_preload.sh 3_tcp_client.py")
    print("\nDone.")
