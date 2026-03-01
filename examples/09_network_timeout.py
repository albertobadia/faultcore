#!/usr/bin/env python3
"""
Network Timeout Example using the interceptor.

This example demonstrates timeout at the NETWORK LEVEL using LD_PRELOAD/DYLD_INSERT_LIBRARIES.
The timeout is applied to socket connect() and recv() syscalls, not to Python functions.

Usage:
    # macOS:
    DYLD_INSERT_LIBRARIES=target/release/libfaultcore_interceptor.dylib uv run python examples/09_network_timeout.py
    # Linux:
    LD_PRELOAD=target/release/libfaultcore_interceptor.so uv run python examples/09_network_timeout.py
"""

import ctypes
import socket
import time

MAGIC_TIMEOUT = 0xFC

libc = None


def setup_timeout(connect_timeout: int, recv_timeout: int):
    """Set network timeout via interceptor."""
    global libc
    if libc is None:
        libc = ctypes.CDLL(None)
    libc.setpriority(MAGIC_TIMEOUT, connect_timeout, recv_timeout)


def clear_timeout():
    """Clear network timeout."""
    global libc
    if libc:
        libc.setpriority(MAGIC_TIMEOUT, 0, 0)


def test_connect_timeout():
    """Test connect timeout with unreachable IP."""
    print("=" * 60)
    print(" Test 1: Connect Timeout (unreachable IP) ".center(60, "="))
    print("=" * 60)

    setup_timeout(2, 2)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)  # Python-level backup timeout

    try:
        start = time.time()
        s.connect(("10.255.255.1", 9999))  # Unreachable IP
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
        clear_timeout()


def test_no_timeout():
    """Test without interceptor timeout (uses Python timeout)."""
    print("\n" + "=" * 60)
    print(" Test 2: No Interceptor Timeout (Python timeout) ".center(60, "="))
    print("=" * 60)

    clear_timeout()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)  # Python-level timeout

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


def test_fast_timeout():
    """Test with very short timeout."""
    print("\n" + "=" * 60)
    print(" Test 3: Fast Timeout (1 second) ".center(60, "="))
    print("=" * 60)

    setup_timeout(1, 1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)

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
        clear_timeout()


def test_connection_refused():
    """Test with immediate connection refused."""
    print("\n" + "=" * 60)
    print(" Test 4: Connection Refused (no server) ".center(60, "="))
    print("=" * 60)

    setup_timeout(5, 5)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)

    try:
        start = time.time()
        s.connect(("127.0.0.1", 9999))  # Nothing listening
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
        clear_timeout()


def test_recv_timeout():
    """Test recv timeout (requires server that sends slowly)."""
    print("\n" + "=" * 60)
    print(" Test 5: Recv Timeout ".center(60, "="))
    print("=" * 60)
    print("Note: This test requires a server that accepts but doesn't send data")
    print("Skipping for demonstration purposes\n")


if __name__ == "__main__":
    print("\nNetwork Timeout Examples using Interceptor")
    print("Make sure to run with DYLD_INSERT_LIBRARIES (macOS) or LD_PRELOAD (Linux)")
    print()

    test_connect_timeout()
    test_no_timeout()
    test_fast_timeout()
    test_connection_refused()
    test_recv_timeout()

    print("\n" + "=" * 60)
    print(" All tests completed! ".center(60, "="))
    print("=" * 60)
