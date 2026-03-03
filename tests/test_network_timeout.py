import socket
import time

import pytest

import faultcore


class TestNetworkTimeout:
    """Tests for network timeout via SHM"""

    def test_interceptor_is_loaded(self):
        if not faultcore.is_interceptor_loaded():
            pytest.skip(
                "Interceptor not loaded. Run tests with:\n"
                "  Linux: LD_PRELOAD=target/release/libfaultcore_interceptor.so pytest tests/"
            )

    @faultcore.timeout(timeout_ms=2000)
    def test_connect_timeout_with_unreachable_ip(self):
        if not faultcore.is_interceptor_loaded():
            pytest.skip("Interceptor not loaded")

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        start = time.time()
        try:
            s.connect(("10.255.255.1", 9999))
            elapsed = time.time() - start
            pytest.fail(f"Should have raised TimeoutError, got connection after {elapsed:.2f}s")
        except (TimeoutError, BlockingIOError):
            elapsed = time.time() - start
            assert 1.5 <= elapsed <= 3.0, f"Expected ~2s, got {elapsed:.2f}s"
        except ConnectionRefusedError:
            elapsed = time.time() - start
            assert elapsed < 1.0, f"Connection refused too slow: {elapsed:.2f}s"
        finally:
            s.close()

    def test_no_timeout_uses_python_timeout(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)

        start = time.time()
        try:
            s.connect(("10.255.255.1", 9999))
            pytest.fail("Should have raised TimeoutError")
        except TimeoutError:
            elapsed = time.time() - start
            assert 1.5 <= elapsed <= 3.0, f"Expected ~2s, got {elapsed:.2f}s"
        finally:
            s.close()

    @faultcore.timeout(timeout_ms=1000)
    def test_short_timeout(self):
        if not faultcore.is_interceptor_loaded():
            pytest.skip("Interceptor not loaded")

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        start = time.time()
        try:
            s.connect(("10.255.255.1", 9999))
            pytest.fail("Should have raised TimeoutError")
        except (TimeoutError, BlockingIOError):
            elapsed = time.time() - start
            assert 0.5 <= elapsed <= 2.0, f"Expected ~1s, got {elapsed:.2f}s"
        finally:
            s.close()

    @faultcore.timeout(timeout_ms=5000)
    def test_connection_refused_fast(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)

        start = time.time()
        try:
            s.connect(("127.0.0.1", 9999))
        except ConnectionRefusedError:
            elapsed = time.time() - start
            assert elapsed < 1.0, f"Connection refused took too long: {elapsed:.2f}s"
        except TimeoutError:
            elapsed = time.time() - start
            assert elapsed >= 4.5, f"Timeout too early: {elapsed:.2f}s"
        finally:
            s.close()


if __name__ == "__main__":
    if not faultcore.is_interceptor_loaded():
        import sys

        print("WARNING: Interceptor not loaded!")
        print("Run tests with:")
        print("  LD_PRELOAD=target/release/libfaultcore_interceptor.so pytest tests/test_network_timeout.py")
        sys.exit(1)

    pytest.main([__file__, "-v"])
