import time

import faultcore


def test_retry_zero_max_retries():
    call_count = 0

    @faultcore.retry(0, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    try:
        failing_func()
        raise AssertionError("Should have raised")
    except ValueError:
        pass

    assert call_count == 1


def test_retry_all_retries_exhausted():
    call_count = 0

    @faultcore.retry(2, backoff_ms=5)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    try:
        failing_func()
        raise AssertionError("Should have raised")
    except ValueError:
        pass

    assert call_count == 3


def test_retry_exponential_backoff():
    call_times = []

    @faultcore.retry(2, backoff_ms=50)
    def failing_func():
        call_times.append(time.time())
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    assert len(call_times) == 3
    if len(call_times) >= 3:
        gap1 = call_times[1] - call_times[0]
        gap2 = call_times[2] - call_times[1]
        assert gap1 >= 0.04
        assert gap2 >= 0.08


def test_retry_with_timeout_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise TimeoutError("timed out")

    try:
        failing_func()
    except TimeoutError:
        pass

    assert call_count == 3


def test_retry_with_network_error():
    call_count = 0

    class NetworkError(Exception):
        pass

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise NetworkError("network failure")

    try:
        failing_func()
    except NetworkError:
        pass

    assert call_count == 3


def test_retry_backoff_duration():
    policy = faultcore.Retry(3, 100, None)

    assert policy.max_retries == 3
    assert policy.backoff_ms == 100


def test_retry_getters():
    policy = faultcore.Retry(5, 200, None)
    assert policy.max_retries == 5
    assert policy.backoff_ms == 200


def test_retry_repr():
    policy = faultcore.Retry(3, 100, None)
    repr_str = repr(policy)
    assert "3" in repr_str
    assert "100" in repr_str
