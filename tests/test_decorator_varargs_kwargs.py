import asyncio

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


def test_retry_decorator_with_args():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def func_with_varargs(*args):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return sum(args)

    result = func_with_varargs(10, 20, 30)
    assert result == 60
    assert call_count == 3


def test_retry_decorator_with_kwargs():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def func_with_kwargs(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return sum(kwargs.values())

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 6
    assert call_count == 3


def test_fallback_decorator_with_args():
    @faultcore.fallback(lambda *args: sum(args) + 100)
    def func_with_varargs(*args):
        raise ValueError("fail")

    result = func_with_varargs(1, 2, 3)
    assert result == 106


def test_fallback_decorator_with_kwargs():
    @faultcore.fallback(lambda **kwargs: sum(kwargs.values()) + 100)
    def func_with_kwargs(**kwargs):
        raise ValueError("fail")

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 106


def test_circuit_breaker_decorator_with_args():
    @faultcore.circuit_breaker(5)
    def func_with_varargs(*args):
        return sum(args)

    result = func_with_varargs(1, 2, 3, 4, 5)
    assert result == 15


def test_circuit_breaker_decorator_with_kwargs():
    @faultcore.circuit_breaker(5)
    def func_with_kwargs(**kwargs):
        return sum(kwargs.values())

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 6


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


async def test_async_retry_decorator_with_args():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    async def func_with_varargs(*args):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return sum(args)

    result = await func_with_varargs(10, 20, 30)
    assert result == 60
    assert call_count == 3


async def test_async_retry_decorator_with_kwargs():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    async def func_with_kwargs(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return sum(kwargs.values())

    result = await func_with_kwargs(a=1, b=2, c=3)
    assert result == 6
    assert call_count == 3


def test_network_queue_decorator_with_args():
    @faultcore.network_queue(rate="1000", capacity="100")
    def func_with_varargs(*args):
        return len(args)

    result = func_with_varargs(1, 2, 3)
    assert result == 3


def test_network_queue_decorator_with_kwargs():
    @faultcore.network_queue(rate="1000", capacity="100")
    def func_with_kwargs(**kwargs):
        return len(kwargs)

    result = func_with_kwargs(a=1, b=2, c=3)
    assert result == 3


async def test_async_network_queue_decorator_with_args():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=10)
    async def func_with_varargs(*args):
        await asyncio.sleep(0.001)
        return sum(args)

    result = await func_with_varargs(1, 2, 3)
    assert result == 6


async def test_async_network_queue_decorator_with_kwargs():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=10)
    async def func_with_kwargs(**kwargs):
        await asyncio.sleep(0.001)
        return sum(kwargs.values())

    result = await func_with_kwargs(a=1, b=2, c=3)
    assert result == 6


def test_decorator_args_and_kwargs_combined():
    @faultcore.retry(2, backoff_ms=10)
    @faultcore.timeout(1000)
    def func_mixed(a, b, *args, **kwargs):
        return a + b + sum(args) + sum(kwargs.values())

    result = func_mixed(1, 2, 3, 4, x=5, y=6)
    assert result == 21
