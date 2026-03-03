import faultcore


def test_retry_is_custom_retry_with_custom_classes():
    call_count = 0

    @faultcore.retry(3, 10, ["ValueError"])
    def func():
        nonlocal call_count
        call_count += 1
        raise ValueError("test")

    try:
        func()
    except ValueError:
        pass
    assert call_count > 1


def test_retry_default_retry_on_includes_standard():
    call_count = 0

    @faultcore.retry(3, 10, None)
    def func():
        nonlocal call_count
        call_count += 1
        raise TimeoutError("timeout")

    try:
        func()
    except TimeoutError:
        pass
    assert call_count > 1


def test_retry_explicit_retry_on_replaces_defaults():
    call_count = 0

    @faultcore.retry(3, 10, ["ValueError"])
    def func():
        nonlocal call_count
        call_count += 1
        raise TimeoutError("timeout")

    try:
        func()
    except TimeoutError:
        pass
    assert call_count == 1


def test_retry_backoff_increases_exponentially():
    import time

    call_times = []

    @faultcore.retry(3, 50)
    def func():
        call_times.append(time.time())
        if len(call_times) < 4:
            raise ValueError("fail")

    try:
        func()
    except ValueError:
        pass

    if len(call_times) >= 3:
        first_gap = call_times[1] - call_times[0]
        second_gap = call_times[2] - call_times[1]
        assert second_gap > first_gap


def test_retry_with_network_error():
    call_count = 0

    @faultcore.retry(2, 10)
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("connection failed")
        return "ok"

    result = func()
    assert result == "ok"
    assert call_count == 3


def test_retry_with_key_error_classified():
    call_count = 0

    @faultcore.retry(2, 10)
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise KeyError("missing")
        return "ok"

    result = func()
    assert result == "ok"
    assert call_count == 3


def test_retry_multiple_error_types():
    call_count = 0

    @faultcore.retry(5, 10, ["ValueError", "TypeError", "KeyError"])
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            error_types = [ValueError("v"), TypeError("t"), KeyError("k")]
            raise error_types[call_count - 1]
        return "ok"

    result = func()
    assert result == "ok"
    assert call_count == 4


def test_retry_getters():
    policy = faultcore.Retry(5, 200)
    assert policy.max_retries == 5
    assert policy.backoff_ms == 200


def test_retry_repr():
    policy = faultcore.Retry(3, 100, ["ValueError"])
    repr_str = repr(policy)
    assert "RetryPolicy" in repr_str
    assert "max_retries=3" in repr_str


def test_retry_zero_retries():
    call_count = 0

    @faultcore.retry(0, 10)
    def func():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    try:
        func()
    except ValueError:
        pass
    assert call_count == 1
