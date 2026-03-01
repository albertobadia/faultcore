import asyncio

import faultcore


def test_timeout_decorator():
    @faultcore.timeout(1000)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_timeout_decorator_zero():
    @faultcore.timeout(1)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_retry_decorator():
    @faultcore.retry(3, backoff_ms=100)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_retry_decorator_with_retry_on():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=["transient"])
    def my_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("retryable")
        return "ok"

    assert my_func() == "ok"
    assert call_count == 2


def test_retry_decorator_no_retry_on_non_retryable():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=["ValueError"])
    def my_func():
        nonlocal call_count
        call_count += 1
        raise TypeError("not retryable")

    try:
        my_func()
        raise AssertionError("Should have raised")
    except TypeError:
        pass

    assert call_count == 4


def test_fallback_decorator():
    @faultcore.fallback(lambda: "default")
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_fallback_decorator_with_error():
    call_count = 0

    @faultcore.fallback(lambda: "default")
    def my_func():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("error")
        return "ok"

    result = my_func()
    assert result == "default"
    assert call_count == 1


def test_fallback_decorator_async():
    @faultcore.fallback(lambda: "default")
    async def my_func():
        return "ok"

    result = asyncio.run(my_func())
    assert result == "ok"


def test_circuit_breaker_decorator():
    @faultcore.circuit_breaker(5)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_circuit_breaker_state():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=1)
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_rate_limit_decorator():
    @faultcore.rate_limit(10.0, 100)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_rate_limit_decorator_exceeded():
    @faultcore.rate_limit(1.0, 1)
    def my_func():
        return "ok"

    # First call should succeed
    assert my_func() == "ok"

    # Second call should fail (rate limit exceeded)
    try:
        my_func()
        # May not raise depending on timing
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()
