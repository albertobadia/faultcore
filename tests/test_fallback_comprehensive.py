import asyncio

import faultcore


def test_fallback_with_callable_object():
    class FallbackCallable:
        def __call__(self):
            return "fallback_result"

    @faultcore.fallback(FallbackCallable())
    def failing_func():
        raise ValueError("error")

    result = failing_func()
    assert result == "fallback_result"


def test_fallback_with_partial_function():
    from functools import partial

    def fallback_func(x, y=0):
        return x + y

    fallback = partial(fallback_func, 10, y=5)

    @faultcore.fallback(fallback)
    def failing_func():
        raise ValueError("error")

    result = failing_func()
    assert result == 15


def test_fallback_chain_multiple_fallbacks():
    @faultcore.fallback(lambda: "first")
    @faultcore.fallback(lambda: "second")
    def failing_func():
        raise ValueError("error")

    result = failing_func()
    assert result == "second"


def test_fallback_with_exception_subclass():
    class CustomError(Exception):
        pass

    @faultcore.fallback(lambda: "fallback")
    def raising_custom():
        raise CustomError("custom")

    result = raising_custom()
    assert result == "fallback"


def test_fallback_function_passes_original_args():
    received_args = []

    def fallback(*args, **kwargs):
        received_args.append((args, kwargs))
        return "fallback"

    @faultcore.fallback(fallback)
    def func(a, b, c=0):
        raise ValueError("error")

    result = func(1, 2, c=3)
    assert result == "fallback"
    assert received_args[0] == ((1, 2), {"c": 3})


async def test_async_fallback_with_success():
    @faultcore.fallback(lambda: "fallback")
    async def success_async():
        await asyncio.sleep(0.001)
        return "success"

    result = await success_async()
    assert result == "success"


def test_fallback_with_async_callable():
    def fallback_func():
        return "fallback_result"

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("error")

    result = failing_func()
    assert result == "fallback_result"


def test_fallback_repr_shows_class():
    policy = faultcore.Fallback(lambda: "fallback")
    repr_str = repr(policy)
    assert "FallbackPolicy" in repr_str
