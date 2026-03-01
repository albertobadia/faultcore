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


def test_retry_passes_args():
    @faultcore.retry(3, backoff_ms=10)
    def func_with_args(a, b):
        return a * b

    result = func_with_args(3, 4)
    assert result == 12


def test_retry_passes_kwargs():
    @faultcore.retry(3, backoff_ms=10)
    def func_with_kwargs(x=1, y=2):
        return x * y

    result = func_with_kwargs(x=5, y=6)
    assert result == 30


def test_fallback_passes_args():
    @faultcore.fallback(lambda: 0)
    def func_with_args(a, b):
        return a - b

    result = func_with_args(10, 3)
    assert result == 7


def test_fallback_passes_kwargs():
    @faultcore.fallback(lambda: 0)
    def func_with_kwargs(a=0, b=0):
        return a - b

    result = func_with_kwargs(a=10, b=5)
    assert result == 5


def test_circuit_breaker_passes_args():
    @faultcore.circuit_breaker(5)
    def func_with_args(a, b, c):
        return a + b + c

    result = func_with_args(1, 2, 3)
    assert result == 6


def test_circuit_breaker_passes_kwargs():
    @faultcore.circuit_breaker(5)
    def func_with_kwargs(a=0, b=0):
        return a * b

    result = func_with_kwargs(a=5, b=4)
    assert result == 20


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


async def test_async_retry_passes_args():
    @faultcore.retry(3, backoff_ms=10)
    async def async_func(a, b):
        return a * b

    result = await async_func(5, 6)
    assert result == 30


async def test_async_retry_passes_kwargs():
    @faultcore.retry(3, backoff_ms=10)
    async def async_func(x=1, y=1):
        return x * y

    result = await async_func(x=7, y=8)
    assert result == 56
