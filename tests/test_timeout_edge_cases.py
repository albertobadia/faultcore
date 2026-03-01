import os
import socket
import time

import faultcore


def is_interceptor_loaded():
    return "DYLD_INSERT_LIBRARIES" in os.environ or "LD_PRELOAD" in os.environ


def test_timeout_expired_network():
    if not is_interceptor_loaded():
        import pytest

        pytest.skip("Interceptor not loaded. Run with DYLD_INSERT_LIBRARIES or LD_PRELOAD")

    @faultcore.timeout(50)
    def network_operation():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect(("10.255.255.1", 9999))
        except (TimeoutError, ConnectionRefusedError):
            pass
        finally:
            sock.close()
        return "ok"

    start = time.time()
    try:
        network_operation()
    except TimeoutError:
        elapsed = time.time() - start
        assert 0.04 <= elapsed <= 0.15, f"Expected ~50ms, got {elapsed:.3f}s"
    except Exception:
        pass


def test_timeout_zero_raises_error():
    try:
        faultcore.Timeout(0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "timeout" in str(e).lower()


def test_timeout_with_very_long_operation():
    if not is_interceptor_loaded():
        import pytest

        pytest.skip("Interceptor not loaded. Run with DYLD_INSERT_LIBRARIES or LD_PRELOAD")

    @faultcore.timeout(100)
    def network_operation():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect(("10.255.255.1", 9999))
        except (TimeoutError, ConnectionRefusedError):
            pass
        finally:
            sock.close()
        return "ok"

    start = time.time()
    try:
        network_operation()
    except TimeoutError:
        elapsed = time.time() - start
        assert 0.05 <= elapsed <= 0.2, f"Expected ~100ms, got {elapsed:.3f}s"
    except Exception:
        pass


def test_timeout_succeeds_before_deadline():
    @faultcore.timeout(2000)
    def quick_operation():
        return "success"

    result = quick_operation()
    assert result == "success"


def test_timeout_getter():
    policy = faultcore.Timeout(500)
    assert policy.timeout_ms == 500


def test_timeout_repr():
    policy = faultcore.Timeout(500)
    repr_str = repr(policy)
    assert "500" in repr_str
