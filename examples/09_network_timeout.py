#!/usr/bin/env python3
"""
Network Timeout Examples using faultcore.
Requires running with LD_PRELOAD on Linux.
"""

import socket
import time

import faultcore


@faultcore.timeout(timeout_ms=2000)
def test_connect_timeout():
    print(" Test 1: Connect Timeout (unreachable IP) ".center(60, "="))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    start = 0

    try:
        start = time.time()
        s.connect(("10.255.255.1", 9999))
        elapsed = time.time() - start
        print(f"Connected after {elapsed:.3f}s (unexpected)")
    except TimeoutError:
        elapsed = time.time() - start
        print(f"TimeoutError after {elapsed:.3f}s (expected)")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Error: {type(e).__name__}: {e} after {elapsed:.3f}s")
    finally:
        s.close()


def test_no_timeout():
    print("\n Test 2: No Interceptor Timeout (Python timeout) ".center(60, "="))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    start = 0

    try:
        start = time.time()
        s.connect(("10.255.255.1", 9999))
        elapsed = time.time() - start
        print(f"Connected after {elapsed:.3f}s")
    except TimeoutError:
        elapsed = time.time() - start
        print(f"TimeoutError after {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Error: {type(e).__name__}: {e} after {elapsed:.3f}s")
    finally:
        s.close()


@faultcore.timeout(timeout_ms=1000)
def test_fast_timeout():
    print("\n Test 3: Fast Timeout (1 second) ".center(60, "="))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    start = 0

    try:
        start = time.time()
        s.connect(("10.255.255.1", 9999))
        elapsed = time.time() - start
        print(f"Connected after {elapsed:.3f}s")
    except TimeoutError:
        elapsed = time.time() - start
        print(f"TimeoutError after {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Error: {type(e).__name__}: {e} after {elapsed:.3f}s")
    finally:
        s.close()


@faultcore.timeout(timeout_ms=5000)
def test_connection_refused():
    print("\n Test 4: Connection Refused (no server) ".center(60, "="))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    start = 0

    try:
        start = time.time()
        s.connect(("127.0.0.1", 9999))
        elapsed = time.time() - start
        print(f"Connected after {elapsed:.3f}s")
    except ConnectionRefusedError:
        elapsed = time.time() - start
        print(f"ConnectionRefusedError after {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Error: {type(e).__name__}: {e} after {elapsed:.3f}s")
    finally:
        s.close()


def test_recv_timeout():
    print("\n Test 5: Recv Timeout ".center(60, "="))
    print("Note: This test requires a server that accepts but doesn't send data")
    print("Skipping for demonstration purposes\n")


if __name__ == "__main__":
    print("\nNetwork Timeout Examples using faultcore")
    print("Uses @faultcore.timeout decorator with SHM communication")
    print("Make sure to run with LD_PRELOAD (Linux)")
    print()

    test_connect_timeout()
    test_no_timeout()
    test_fast_timeout()
    test_connection_refused()
    test_recv_timeout()

    print("\n" + "=" * 60)
    print(" All tests completed! ".center(60, "="))
    print("=" * 60)
