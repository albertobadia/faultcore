import asyncio

import faultcore


async def test_async_timeout_error_propagation():
    @faultcore.timeout(1000)
    async def failing_async():
        await asyncio.sleep(0.01)
        raise RuntimeError("async error")

    try:
        await failing_async()
    except RuntimeError as e:
        assert str(e) == "async error"


def test_sync_timeout_error_propagation():
    @faultcore.timeout(1000)
    def failing_func():
        raise RuntimeError("sync error")

    try:
        failing_func()
    except RuntimeError as e:
        assert str(e) == "sync error"


async def test_async_context_manager_enters():
    entered = False

    @faultcore.network_queue(rate="10mbps", capacity="1mb")
    async def test_func():
        nonlocal entered
        entered = True
        await asyncio.sleep(0.01)
        return "ok"

    result = await test_func()
    assert result == "ok"
    assert entered


async def test_async_with_network_queue_latency():
    @faultcore.network_queue(rate="10mbps", capacity="1mb", latency_ms=50)
    async def test_func():
        await asyncio.sleep(0.01)
        return "ok"

    result = await test_func()
    assert result == "ok"


def test_sync_with_network_queue_latency():
    @faultcore.network_queue(rate="10mbps", capacity="1mb", latency_ms=50)
    def test_func():
        return "ok"

    result = test_func()
    assert result == "ok"
