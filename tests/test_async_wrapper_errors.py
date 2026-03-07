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
