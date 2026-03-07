import asyncio

import faultcore


async def test_async_chaos_wrapper_basic():
    @faultcore.timeout(1000)
    async def my_coro():
        await asyncio.sleep(0.001)
        return "result"

    result = await my_coro()
    assert result == "result"


async def test_async_chaos_wrapper_rate_limit_exceeded():
    @faultcore.rate_limit(1.0)
    async def limited_coro():
        return "ok"

    result = await limited_coro()
    assert result == "ok"

    try:
        await limited_coro()
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()


async def test_async_with_exception_in_await():
    @faultcore.timeout(1000)
    async def failing_await():
        await asyncio.sleep(0.001)
        raise RuntimeError("error during await")

    try:
        await failing_await()
        raise AssertionError("Should have raised")
    except RuntimeError as e:
        assert "error during await" in str(e)


def test_sync_function_returns_async():
    @faultcore.timeout(1000)
    async def async_func():
        return "async result"

    wrapper = async_func()
    assert hasattr(wrapper, "__await__")
    assert hasattr(wrapper, "send")
    assert hasattr(wrapper, "throw")

    asyncio.run(wrapper)
