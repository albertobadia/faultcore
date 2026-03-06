import faultcore


def test_timeout_passes_args():
    @faultcore.timeout(1000)
    def func_with_args(a, b):
        return a + b

    result = func_with_args(1, 2)
    assert result == 3


def test_timeout_passes_kwargs():
    @faultcore.timeout(1000)
    def func_with_kwargs(a=1, b=2):
        return a + b

    result = func_with_kwargs(a=5, b=10)
    assert result == 15


def test_timeout_passes_mixed_args():
    @faultcore.timeout(1000)
    def func_mixed(a, b=10, c=20):
        return a + b + c

    result = func_mixed(5, c=100)
    assert result == 115


def test_rate_limit_passes_args():
    @faultcore.rate_limit(100.0, 50)
    def func_with_args(a, b):
        return a**b

    result = func_with_args(2, 3)
    assert result == 8


def test_rate_limit_passes_kwargs():
    @faultcore.rate_limit(100.0, 50)
    def func_with_kwargs(base=1, exp=1):
        return base**exp

    result = func_with_kwargs(base=3, exp=4)
    assert result == 81


async def test_async_timeout_passes_args():
    @faultcore.timeout(1000)
    async def async_func(a, b):
        return a + b

    result = await async_func(10, 20)
    assert result == 30


async def test_async_timeout_passes_kwargs():
    @faultcore.timeout(1000)
    async def async_func(a=0, b=0):
        return a + b

    result = await async_func(a=100, b=200)
    assert result == 300
