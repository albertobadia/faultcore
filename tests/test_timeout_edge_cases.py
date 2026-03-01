import time

import faultcore


def test_timeout_expired():
    @faultcore.timeout(50)
    def long_running():
        time.sleep(0.2)
        return "ok"

    try:
        long_running()
        raise AssertionError("Should have raised TimeoutError")
    except Exception as e:
        assert "timed out" in str(e).lower()


def test_timeout_zero_raises_error():
    try:
        faultcore.Timeout(0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "timeout" in str(e).lower()


def test_timeout_with_very_long_operation():
    @faultcore.timeout(10)
    def very_long():
        time.sleep(0.5)
        return "ok"

    try:
        very_long()
        raise AssertionError("Should have raised TimeoutError")
    except Exception as e:
        assert "timed out" in str(e).lower()


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
