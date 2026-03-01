import faultcore


def test_retry_with_retry_on_none():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=None)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("test error")

    try:
        failing_func()
    except ValueError:
        pass

    assert call_count == 3


def test_retry_with_empty_retry_on():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=[])
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("test error")

    try:
        failing_func()
    except ValueError:
        pass

    assert call_count == 1


def test_retry_with_timeout_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("operation timed out")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_network_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("network failure")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


async def test_async_retry_with_timeout_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    async def failing_async():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("async timeout")
        return "success"

    result = await failing_async()
    assert result == "success"
    assert call_count == 3


async def test_async_retry_with_connection_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    async def failing_async():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("network failure")
        return "success"

    result = await failing_async()
    assert result == "success"
    assert call_count == 3


async def test_async_retry_with_value_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    async def failing_async():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("value error")
        return "success"

    result = await failing_async()
    assert result == "success"
    assert call_count == 3


async def test_async_retry_string_type_not_matching():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10, retry_on=["timeout"])
    async def failing_async():
        nonlocal call_count
        call_count += 1
        raise ValueError("not a timeout")

    try:
        await failing_async()
    except ValueError:
        pass

    assert call_count == 1


def test_retry_policy_classification():
    policy = faultcore.Retry(3, 100, ["timeout", "network"])
    assert policy.max_retries == 3
    assert policy.backoff_ms == 100


def test_retry_repr():
    policy = faultcore.Retry(3, 100, None)
    repr_str = repr(policy)
    assert "RetryPolicy" in repr_str
    assert "3" in repr_str
    assert "100" in repr_str
