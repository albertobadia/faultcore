import asyncio

import faultcore


def test_sync_function():
    @faultcore.timeout(1000)
    def sync_func():
        return "sync result"

    assert sync_func() == "sync result"


async def test_async_function():
    @faultcore.timeout(1000)
    async def async_func():
        return "async result"

    result = await async_func()
    assert result == "async result"


def test_sync_retry():
    call_count = 0

    @faultcore.retry(max_retries=2, backoff_ms=10)
    def sync_fail():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "success"

    assert sync_fail() == "success"
    assert call_count == 3


async def test_async_retry():
    call_count = 0

    @faultcore.retry(max_retries=2, backoff_ms=10)
    async def async_fail():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "success"

    result = await async_fail()
    assert result == "success"
    assert call_count == 3


if __name__ == "__main__":
    test_sync_function()
    asyncio.run(test_async_function())
    test_sync_retry()
    asyncio.run(test_async_retry())
