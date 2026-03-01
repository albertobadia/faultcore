import ctypes
import os
import socket
import sys
import time

import pytest

MAGIC_TIMEOUT = 0xFC


def setup_timeout(connect_timeout: int, recv_timeout: int):
    libc = ctypes.CDLL(None)
    libc.setpriority(MAGIC_TIMEOUT, connect_timeout, recv_timeout)


def clear_timeout():
    libc = ctypes.CDLL(None)
    libc.setpriority(MAGIC_TIMEOUT, 0, 0)


def is_interceptor_loaded():
    return "DYLD_INSERT_LIBRARIES" in os.environ or "LD_PRELOAD" in os.environ


@pytest.fixture(autouse=True)
def cleanup_timeout():
    yield
    try:
        clear_timeout()
    except Exception:
        pass


def test_interceptor_is_loaded():
    if not is_interceptor_loaded():
        pytest.skip(
            "Interceptor not loaded. Run tests with:\n"
            "  macOS: DYLD_INSERT_LIBRARIES=target/release/libfaultcore_interceptor.dylib pytest tests/\n"
            "  Linux: LD_PRELOAD=target/release/libfaultcore_interceptor.so pytest tests/"
        )


def test_connect_timeout_with_unreachable_ip():
    if not is_interceptor_loaded():
        pytest.skip("Interceptor not loaded")

    setup_timeout(2, 2)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)  # Python backup timeout

    start = time.time()
    try:
        s.connect(("10.255.255.1", 9999))
        elapsed = time.time() - start
        pytest.fail(f"Should have raised TimeoutError or ConnectionRefusedError, got connection after {elapsed:.2f}s")
    except TimeoutError:
        elapsed = time.time() - start
        # Should be around 2 seconds (interceptor timeout)
        assert 1.5 <= elapsed <= 3.0, f"Expected ~2s, got {elapsed:.2f}s"
    except ConnectionRefusedError:
        # Some networks route 10.x.x.x to local services
        elapsed = time.time() - start
        # Connection refused should be fast
        assert elapsed < 1.0, f"Connection refused too slow: {elapsed:.2f}s"
    finally:
        s.close()


def test_no_timeout_uses_python_timeout():
    clear_timeout()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)  # Python timeout

    start = time.time()
    try:
        s.connect(("10.255.255.1", 9999))
        pytest.fail("Should have raised TimeoutError")
    except TimeoutError:
        elapsed = time.time() - start
        # Should be around 2 seconds (Python timeout)
        assert 1.5 <= elapsed <= 3.0, f"Expected ~2s, got {elapsed:.2f}s"
    finally:
        s.close()


def test_short_timeout():
    if not is_interceptor_loaded():
        pytest.skip("Interceptor not loaded")

    setup_timeout(1, 1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)

    start = time.time()
    try:
        s.connect(("10.255.255.1", 9999))
        pytest.fail("Should have raised TimeoutError")
    except TimeoutError:
        elapsed = time.time() - start
        # Should be around 1 second
        assert 0.5 <= elapsed <= 2.0, f"Expected ~1s, got {elapsed:.2f}s"
    finally:
        s.close()


def test_clear_timeout():
    # Set timeout
    setup_timeout(5, 5)

    # Clear timeout
    clear_timeout()

    # Now should use Python timeout
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)

    start = time.time()
    try:
        s.connect(("10.255.255.1", 9999))
        pytest.fail("Should have raised TimeoutError")
    except TimeoutError:
        elapsed = time.time() - start
        # Should be around 1 second (Python timeout)
        assert 0.5 <= elapsed <= 2.0, f"Expected ~1s, got {elapsed:.2f}s"
    finally:
        s.close()


def test_connection_refused_fast():
    setup_timeout(5, 5)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)

    start = time.time()
    try:
        s.connect(("127.0.0.1", 9999))  # Nothing listening on this port
    except ConnectionRefusedError:
        elapsed = time.time() - start
        # Should be very fast (< 1 second)
        assert elapsed < 1.0, f"Connection refused took too long: {elapsed:.2f}s"
    except TimeoutError:
        elapsed = time.time() - start
        # If timeout kicks in first, still valid
        assert elapsed >= 4.5, f"Timeout too early: {elapsed:.2f}s"
    finally:
        s.close()


def test_zero_timeout_clears():
    if not is_interceptor_loaded():
        pytest.skip("Interceptor not loaded")

    setup_timeout(3, 3)
    setup_timeout(0, 0)  # Clear

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)

    start = time.time()
    try:
        s.connect(("10.255.255.1", 9999))
        pytest.fail("Should have raised TimeoutError")
    except TimeoutError:
        elapsed = time.time() - start
        # Should use Python timeout (1s)
        assert 0.5 <= elapsed <= 2.0, f"Expected ~1s (Python), got {elapsed:.2f}s"
    finally:
        s.close()


if __name__ == "__main__":
    if not is_interceptor_loaded():
        print("WARNING: Interceptor not loaded!")
        print("Run tests with:")
        if sys.platform == "darwin":
            lib = "DYLD_INSERT_LIBRARIES"
            ext = "dylib"
        else:
            lib = "LD_PRELOAD"
            ext = "so"
        print(f"  {lib}=target/release/libfaultcore_interceptor.{ext} pytest tests/test_network_timeout.py")
        sys.exit(1)

    pytest.main([__file__, "-v"])
