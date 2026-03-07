import asyncio

import pytest

from faultcore import apply_policy, register_policy_bundle


class ExecutionCounter:
    def __init__(self):
        self.count = 0

    async def async_method(self):
        self.count += 1
        await asyncio.sleep(0.01)
        return "async_done"

    def sync_method(self):
        self.count += 1
        return "sync_done"


@pytest.mark.asyncio
async def test_async_decorator_fix():
    counter = ExecutionCounter()
    register_policy_bundle("test_key", timeout_ms=100)

    wrapped = apply_policy("test_key")(counter.async_method)
    result = await wrapped()

    assert result == "async_done"
    assert counter.count == 1


def test_sync_decorator_still_works():
    counter = ExecutionCounter()
    register_policy_bundle("test_key_sync", timeout_ms=100)

    wrapped = apply_policy("test_key_sync")(counter.sync_method)
    result = wrapped()

    assert result == "sync_done"
    assert counter.count == 1
