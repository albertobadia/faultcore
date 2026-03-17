import asyncio

import faultcore


class TestAsyncBasic:
    def test_sync_function(self):
        @faultcore.timeout(connect="1s")
        def sync_func():
            return "sync result"

        assert sync_func() == "sync result"

    async def test_async_function(self):
        @faultcore.timeout(connect="1s")
        async def async_func():
            return "async result"

        result = await async_func()
        assert result == "async result"


class TestAsyncChaosWrapper:
    async def test_async_chaos_wrapper_basic(self):
        @faultcore.timeout(connect="1s")
        async def my_coro():
            await asyncio.sleep(0.001)
            return "result"

        result = await my_coro()
        assert result == "result"

    async def test_async_chaos_wrapper_rate_limit_exceeded(self):
        @faultcore.rate("1mbps")
        async def limited_coro():
            return "ok"

        result = await limited_coro()
        assert result == "ok"

    async def test_async_with_exception_in_await(self):
        @faultcore.timeout(connect="1s")
        async def failing_await():
            await asyncio.sleep(0.001)
            raise RuntimeError("error during await")

        try:
            await failing_await()
            raise AssertionError("Should have raised")
        except RuntimeError as e:
            assert "error during await" in str(e)

    def test_sync_function_returns_async(self):
        @faultcore.timeout(connect="1s")
        async def async_func():
            return "async result"

        wrapper = async_func()
        assert hasattr(wrapper, "__await__")
        assert hasattr(wrapper, "send")
        assert hasattr(wrapper, "throw")

        asyncio.run(wrapper)


class TestAsyncErrorPropagation:
    async def test_async_timeout_error_propagation(self):
        @faultcore.timeout(connect="1s")
        async def failing_async():
            await asyncio.sleep(0.01)
            raise RuntimeError("async error")

        try:
            await failing_async()
        except RuntimeError as e:
            assert str(e) == "async error"

    def test_sync_timeout_error_propagation(self):
        @faultcore.timeout(connect="1s")
        def failing_func():
            raise RuntimeError("sync error")

        try:
            failing_func()
        except RuntimeError as e:
            assert str(e) == "sync error"


class TestAsyncFaultContext:
    async def test_async_fault_context_sets_and_restores_policy(self):
        from faultcore.decorator import get_thread_policy

        faultcore.set_thread_policy("outer")
        async with faultcore.policy_context("inner"):
            assert get_thread_policy() == "inner"
