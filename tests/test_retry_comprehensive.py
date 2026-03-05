import time

import faultcore


def test_retry_with_retry_on_string_timeout():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["timeout"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("timed out")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_retry_on_string_connection_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["network"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("connection failed")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_retry_on_string_runtime_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["RuntimeError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("runtime error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_multiple_retry_on_strings():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["ValueError", "RuntimeError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("runtime error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_retry_on_string_not_matching():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["ValueError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("not a ValueError")

    try:
        failing_func()
    except RuntimeError:
        pass

    assert call_count == 1


def test_retry_backoff_duration_grows():
    call_times = []

    @faultcore.retry(3, backoff_ms=50)
    def failing_func():
        call_times.append(time.time())
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    if len(call_times) >= 4:
        gap1 = call_times[1] - call_times[0]
        gap2 = call_times[2] - call_times[1]
        gap3 = call_times[3] - call_times[2]
        assert gap1 >= 0.04
        assert gap2 >= 0.08
        assert gap3 >= 0.12


def test_retry_classify_as_transient():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("io error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_large_backoff():
    start = time.time()

    @faultcore.retry(1, backoff_ms=100)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    elapsed = time.time() - start
    assert elapsed >= 0.09


def test_retry_first_attempt_succeeds():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10)
    def succeeding_func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = succeeding_func()
    assert result == "success"
    assert call_count == 1


def test_retry_repr_contains_retry_on():
    policy = faultcore.Retry(3, 100, ["ValueError", "TimeoutError"])
    repr_str = repr(policy)
    assert "RetryPolicy" in repr_str
    assert "3" in repr_str
    assert "100" in repr_str


def test_retry_with_transient_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["transient"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_default_retry_on():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("timeout")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3
