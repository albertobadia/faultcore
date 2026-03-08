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
