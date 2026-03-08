import asyncio
import time

import pytest

import faultcore


class TestTimeoutDecorator:
    def test_timeout_decorator_basic(self):
        @faultcore.timeout(1000)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_decorator_zero(self):
        @faultcore.timeout(1)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_passes_args(self):
        @faultcore.timeout(1000)
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_timeout_passes_kwargs(self):
        @faultcore.timeout(1000)
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15

    def test_timeout_passes_mixed_args(self):
        @faultcore.timeout(1000)
        def func_mixed(a, b=10, c=20):
            return a + b + c

        result = func_mixed(5, c=100)
        assert result == 115

    def test_timeout_decorator_with_varargs(self):
        @faultcore.timeout(1000)
        def func_with_varargs(*args):
            return sum(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    def test_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(1000)
        def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 6

    def test_timeout_decorator_with_args_and_kwargs(self):
        @faultcore.timeout(1000)
        def func_mixed(*args, **kwargs):
            return sum(args) + sum(kwargs.values())

        result = func_mixed(1, 2, x=3, y=4)
        assert result == 10


class TestLatencyDecorator:
    def test_latency_decorator_writes_latency_to_shm(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.latency(500)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_latency.assert_called_once_with(12345, 500)
                mock_shm.write_timeouts.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_latency_decorator_preserves_function_name(self):
        @faultcore.latency(100)
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"


class TestTimeoutDecoratorWritesCorrectFields:
    def test_timeout_writes_network_timeout_fields(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.timeout(2000)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 2000, 2000)
                mock_shm.write_latency.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)


class TestRateLimitDecorator:
    def test_rate_limit_decorator_basic(self):
        @faultcore.rate_limit(10.0)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_rate_limit_decorator_exceeded(self):
        @faultcore.rate_limit(1.0)
        def my_func():
            return "ok"

        assert my_func() == "ok"

        try:
            my_func()
        except Exception as e:
            assert "rate limit" in str(e).lower() or "resource" in str(e).lower()

    def test_rate_limit_passes_args(self):
        @faultcore.rate_limit(100.0)
        def func_with_args(a, b):
            return a**b

        result = func_with_args(2, 3)
        assert result == 8

    def test_rate_limit_passes_kwargs(self):
        @faultcore.rate_limit(100.0)
        def func_with_kwargs(base=1, exp=1):
            return base**exp

        result = func_with_kwargs(base=3, exp=4)
        assert result == 81

    def test_rate_limit_decorator_with_args(self):
        @faultcore.rate_limit(100.0)
        def func_with_varargs(*args):
            return len(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 5

    def test_rate_limit_decorator_with_kwargs(self):
        @faultcore.rate_limit(100.0)
        def func_with_kwargs(**kwargs):
            return len(kwargs)

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 3


class TestDecoratorMetadata:
    def test_decorator_preserves_function_name(self):
        @faultcore.timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_decorator_preserves_function_docstring(self):
        @faultcore.timeout(1000)
        def my_function():
            """This is my docstring."""
            return "ok"

        assert my_function.__doc__ == "This is my docstring."

    def test_decorator_preserves_function_module(self):
        @faultcore.timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__module__ is not None


class TestAsyncTimeoutDecorator:
    async def test_async_timeout_passes_args(self):
        @faultcore.timeout(1000)
        async def async_func(a, b):
            return a + b

        result = await async_func(10, 20)
        assert result == 30

    async def test_async_timeout_passes_kwargs(self):
        @faultcore.timeout(1000)
        async def async_func(a=0, b=0):
            return a + b

        result = await async_func(a=100, b=200)
        assert result == 300

    async def test_async_timeout_decorator_with_args(self):
        @faultcore.timeout(1000)
        async def func_with_varargs(*args):
            return sum(args)

        result = await func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    async def test_async_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(1000)
        async def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = await func_with_kwargs(a=1, b=2, c=3)
        assert result == 6


class TestTimeoutContract:
    def test_timeout_enforces_function_execution_deadline(self):
        @faultcore.timeout(5)
        def slow_operation():
            time.sleep(0.02)
            return "done"

        with pytest.raises(TimeoutError):
            slow_operation()


class TestTimeoutShmLifecycle:
    def test_sync_timeout_clears_shm_on_timeout_error(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=777):

                @faultcore.timeout(5)
                def slow_operation():
                    time.sleep(0.02)

                with pytest.raises(TimeoutError):
                    slow_operation()

                mock_shm.write_timeouts.assert_called_once_with(777, 5, 5)
                mock_shm.clear.assert_called_once_with(777)

    def test_sync_timeout_clears_shm_on_function_exception(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=778):

                @faultcore.timeout(100)
                def failing_operation():
                    raise RuntimeError("boom")

                with pytest.raises(RuntimeError, match="boom"):
                    failing_operation()

                mock_shm.write_timeouts.assert_called_once_with(778, 100, 100)
                mock_shm.clear.assert_called_once_with(778)

    async def test_async_timeout_clears_shm_on_timeout_error(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=779):

                @faultcore.timeout(10)
                async def slow_async():
                    await asyncio.sleep(0.05)

                with pytest.raises((TimeoutError, asyncio.TimeoutError)):
                    await slow_async()

                mock_shm.write_timeouts.assert_called_once_with(779, 10, 10)
                mock_shm.clear.assert_called_once_with(779)


class TestAsyncShmLifecycle:
    async def test_async_decorator_keeps_policy_until_coroutine_finishes(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=321):

                @faultcore.timeout(100)
                async def async_op():
                    return "ok"

                pending = async_op()
                try:
                    assert mock_shm.clear.call_count == 0
                finally:
                    result = await pending
                    assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(321, 100, 100)
                mock_shm.clear.assert_called_once_with(321)
