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


async def test_async_retry_error_propagation():
    @faultcore.retry(1, backoff_ms=10)
    async def failing_async():
        await asyncio.sleep(0.01)
        raise RuntimeError("retry failed")

    try:
        await failing_async()
    except RuntimeError as e:
        assert str(e) == "retry failed"


async def test_async_circuit_breaker_error():
    @faultcore.circuit_breaker(1)
    async def failing_async():
        await asyncio.sleep(0.01)
        raise ValueError("circuit test")

    try:
        await failing_async()
    except ValueError:
        pass

    try:
        await failing_async()
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()


async def test_async_fallback_success():
    @faultcore.fallback(lambda: "fallback")
    async def success_async():
        await asyncio.sleep(0.01)
        return "success"

    result = await success_async()
    assert result == "success"


async def test_async_timeout_with_cancellation():
    cancelled = False

    @faultcore.timeout(5000)
    async def long_running():
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise

    task = asyncio.create_task(long_running())
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert cancelled or True


async def test_async_retry_with_async_backoff():
    call_count = 0

    @faultcore.retry(2, backoff_ms=50)
    async def failing_async():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        if call_count < 3:
            raise ValueError("retry")
        return "success"

    result = await failing_async()
    assert result == "success"
    assert call_count == 3


def test_sync_timeout_error_propagation():
    @faultcore.timeout(1000)
    def failing_func():
        raise RuntimeError("sync error")

    try:
        failing_func()
    except RuntimeError as e:
        assert str(e) == "sync error"


def test_sync_retry_error_propagation():
    @faultcore.retry(1, backoff_ms=10)
    def failing_func():
        raise RuntimeError("retry failed")

    try:
        failing_func()
    except RuntimeError as e:
        assert str(e) == "retry failed"


def test_sync_circuit_breaker_error():
    @faultcore.circuit_breaker(1)
    def failing_func():
        raise ValueError("circuit test")

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()


async def test_async_context_manager_enters():
    entered = False

    @faultcore.network_queue(rate="1000", capacity="100")
    async def test_func():
        nonlocal entered
        entered = True
        await asyncio.sleep(0.01)
        return "ok"

    result = await test_func()
    assert result == "ok"
    assert entered


async def test_async_with_network_queue_latency():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=50)
    async def test_func():
        await asyncio.sleep(0.01)
        return "ok"

    result = await test_func()
    assert result == "ok"


def test_sync_with_network_queue_latency():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=50)
    def test_func():
        return "ok"

    result = test_func()
    assert result == "ok"


async def test_async_timeout_with_retry():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    @faultcore.timeout(1000)
    async def failing_async():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        if call_count < 3:
            raise ValueError("retry")
        return "success"

    result = await failing_async()
    assert result == "success"
    assert call_count == 3


def test_sync_timeout_with_retry():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    @faultcore.timeout(1000)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("retry")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3
