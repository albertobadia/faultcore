import asyncio

import faultcore


def test_sync_function():
    @faultcore.timeout(1000)
    def sync_func():
        return "sync result"

    assert sync_func() == "sync result"


async def test_async_function():
    @faultcore.timeout(1000)
    async def async_func():
        return "async result"

    result = await async_func()
    assert result == "async result"


if __name__ == "__main__":
    test_sync_function()
    asyncio.run(test_async_function())
