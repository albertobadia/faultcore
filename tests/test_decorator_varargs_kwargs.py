import faultcore


def test_timeout_decorator_with_args():
    @faultcore.timeout(1000)
    def func_with_varargs(*args):
        return sum(args)

    result = func_with_varargs(1, 2, 3, 4, 5)
    assert result == 15


def test_timeout_decorator_with_kwargs():
    @faultcore.timeout(1000)
    def func_with_kwargs(**kwargs):
        return sum(kwargs.values())

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 6


def test_timeout_decorator_with_args_and_kwargs():
    @faultcore.timeout(1000)
    def func_mixed(*args, **kwargs):
        return sum(args) + sum(kwargs.values())

    result = func_mixed(1, 2, x=3, y=4)
    assert result == 10


def test_rate_limit_decorator_with_args():
    @faultcore.rate_limit(100.0, 50)
    def func_with_varargs(*args):
        return len(args)

    result = func_with_varargs(1, 2, 3, 4, 5)
    assert result == 5


def test_rate_limit_decorator_with_kwargs():
    @faultcore.rate_limit(100.0, 50)
    def func_with_kwargs(**kwargs):
        return len(kwargs)

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 3


async def test_async_timeout_decorator_with_args():
    @faultcore.timeout(1000)
    async def func_with_varargs(*args):
        return sum(args)

    result = await func_with_varargs(1, 2, 3, 4, 5)
    assert result == 15


async def test_async_timeout_decorator_with_kwargs():
    @faultcore.timeout(1000)
    async def func_with_kwargs(**kwargs):
        return sum(kwargs.values())

    result = await func_with_kwargs(a=1, b=2, c=3)
    assert result == 6
