import asyncio

import faultcore


async def test_async_chaos_wrapper_basic():
    @faultcore.timeout(1000)
    async def my_coro():
        await asyncio.sleep(0.001)
        return "result"

    result = await my_coro()
    assert result == "result"


async def test_async_chaos_wrapper_with_retry():
    call_count = 0

    @faultcore.retry(2, 10)
    async def my_coro():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "ok"

    result = await my_coro()
    assert result == "ok"
    assert call_count == 3


async def test_async_chaos_wrapper_with_network_queue():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=10)
    async def my_coro():
        await asyncio.sleep(0.001)
        return "result"

    result = await my_coro()
    assert result == "result"


async def test_async_chaos_wrapper_exception_propagation():
    @faultcore.retry(1, 10)
    async def my_coro():
        raise ValueError("test error")

    try:
        await my_coro()
        raise AssertionError("Should have raised")
    except ValueError as e:
        assert str(e) == "test error"


async def test_async_chaos_wrapper_with_fallback_success():
    @faultcore.fallback(lambda: "fallback")
    async def success_coro():
        await asyncio.sleep(0.001)
        return "success"

    result = await success_coro()
    assert result == "success"


async def test_async_chaos_wrapper_rate_limit_exceeded():
    @faultcore.rate_limit(1.0, 1)
    async def limited_coro():
        return "ok"

    result = await limited_coro()
    assert result == "ok"

    try:
        await limited_coro()
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()


async def test_async_chaos_wrapper_context_manager():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=50)
    async def test_coro():
        return "ok"

    result = await test_coro()
    assert result == "ok"


async def test_async_multiple_decorators_order():
    call_order = []

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(2, 10)
    @faultcore.timeout(1000)
    async def decorated_coro():
        call_order.append("coro")
        return "ok"

    result = await decorated_coro()
    assert result == "ok"
    assert call_order == ["coro"]


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
    import asyncio

    asyncio.get_event_loop().run_until_complete(wrapper)
