import time

import faultcore


def test_timeout_with_one_ms():
    _policy = faultcore.Timeout(1)

    @faultcore.timeout(1)
    def quick_func():
        return "ok"

    result = quick_func()
    assert result == "ok"


def test_timeout_with_very_large_value():
    _policy = faultcore.Timeout(1000000)

    @faultcore.timeout(1000000)
    def long_func():
        return "ok"

    result = long_func()
    assert result == "ok"


def test_timeout_policy_repr():
    policy = faultcore.Timeout(500)
    repr_str = repr(policy)
    assert "TimeoutPolicy" in repr_str
    assert "500" in repr_str


def test_timeout_passes_args_kwargs():
    @faultcore.timeout(5000)
    def func_with_args(a, b, c=0):
        return a + b + c

    result = func_with_args(1, 2, c=3)
    assert result == 6


def test_timeout_zero_raises():
    try:
        faultcore.Timeout(0)
        raise AssertionError("Should have raised")
    except Exception as e:
        assert "value" in str(e).lower() or "timeout" in str(e).lower()


def test_timeout_decorator_preserves_name():
    @faultcore.timeout(1000)
    def my_function():
        return "ok"

    assert my_function.__name__ == "my_function"


def test_timeout_decorator_preserves_docstring():
    @faultcore.timeout(1000)
    def my_function():
        """This is a docstring."""
        return "ok"

    assert my_function.__doc__ == "This is a docstring."


def test_timeout_with_async_function():
    import asyncio

    @faultcore.timeout(5000)
    async def async_func():
        await asyncio.sleep(0.001)
        return "ok"

    result = asyncio.run(async_func())
    assert result == "ok"


def test_timeout_returns_value_immediately():
    start = time.time()

    @faultcore.timeout(1000)
    def quick_func():
        return "ok"

    result = quick_func()
    elapsed = time.time() - start

    assert result == "ok"
    assert elapsed < 0.1


def test_timeout_policy_class():
    policy = faultcore.Timeout(1000)
    assert hasattr(policy, "timeout_ms")
