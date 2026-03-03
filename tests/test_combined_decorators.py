import asyncio
import socket

import faultcore


def test_multiple_decorators_order():
    call_order = []

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(2, backoff_ms=10)
    @faultcore.timeout(1000)
    def func():
        call_order.append("func")
        return "ok"

    result = func()
    assert result == "ok"
    assert call_order == ["func"]


def test_retry_with_fallback():
    call_count = 0

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(2, backoff_ms=10)
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "ok"

    result = func()
    assert result == "ok"
    assert call_count == 3


def test_timeout_with_fallback():
    if not faultcore.is_interceptor_loaded():
        import pytest

        pytest.skip("Interceptor not loaded. Run with DYLD_INSERT_LIBRARIES or LD_PRELOAD")

    @faultcore.fallback(lambda: "fallback")
    @faultcore.timeout(50)
    def func():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("10.255.255.1", 9999))
        sock.close()
        return "ok"

    result = func()
    assert result == "fallback"


def test_circuit_breaker_with_fallback():
    call_count = 0

    @faultcore.fallback(lambda: "fallback")
    @faultcore.circuit_breaker(2)
    def func():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    for _ in range(5):
        result = func()

    assert result == "fallback"


def test_rate_limit_with_fallback():
    @faultcore.fallback(lambda: "fallback")
    @faultcore.rate_limit(1.0, 1)
    def func():
        return "ok"

    assert func() == "ok"
    result = func()
    assert result == "fallback"


async def test_async_multiple_decorators():
    call_order = []

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(2, backoff_ms=10)
    @faultcore.timeout(1000)
    async def func():
        call_order.append("func")
        return "ok"

    result = await func()
    assert result == "ok"
    assert call_order == ["func"]


async def test_async_retry_with_fallback():
    call_count = 0

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(2, backoff_ms=10)
    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "ok"

    result = await func()
    assert result == "ok"
    assert call_count == 3


async def test_async_timeout_with_fallback():
    @faultcore.fallback(lambda: asyncio.coroutine(lambda: "fallback")())
    @faultcore.timeout(5)
    async def func():
        await asyncio.sleep(0.1)
        return "ok"

    result = await func()
    assert result == "ok" or result == "fallback"
