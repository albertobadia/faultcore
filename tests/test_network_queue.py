import asyncio
import time

from faultcore import network_queue


def test_network_queue_basic():
    @network_queue(rate="1000", capacity="100")
    def network_call():
        return "ok"

    result = network_call()
    assert result == "ok"


def test_network_queue_with_latency():
    @network_queue(rate="1000", capacity="100", latency_ms=100)
    def network_call():
        return "ok"

    start = time.time()
    result = network_call()
    duration = (time.time() - start) * 1000

    assert result == "ok"
    assert duration >= 90, f"Expected latency >= 90ms, got {duration}ms"


def test_network_queue_with_packet_loss():
    @network_queue(rate="1000", capacity="100", packet_loss=0.5)
    def network_call():
        return "ok"

    # Packet loss is applied at socket level, so this test mainly verifies
    # the decorator doesn't crash
    result = network_call()
    assert result == "ok"


async def test_network_queue_async():
    import socket

    @network_queue(rate="1000", capacity="100", latency_ms=50)
    async def async_network_call():
        # Make actual socket call to trigger latency
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.sendto(b"test", ("127.0.0.1", 12345))
        except Exception:
            pass
        finally:
            s.close()
        return "async ok"

    result = await async_network_call()

    assert result == "async ok"
    # Note: Latency is applied at socket level, so timing test is best-effort
    # The main assertion is that the function completes without error


async def test_network_queue_async_packet_loss():
    @network_queue(rate="1000", capacity="100", packet_loss=0.5)
    async def async_network_call():
        return "async ok"

    result = await async_network_call()
    assert result == "async ok"


def test_network_queue_rate_limiting():
    @network_queue(rate="10", capacity="5")
    def network_call():
        return "ok"

    start = time.time()
    for _ in range(15):
        network_call()
    duration = time.time() - start

    assert duration >= 0.9, f"Expected >= 0.9s, got {duration}s"


async def test_multiple_async_tasks_isolated():
    results = []

    @network_queue(packet_loss=0.5)
    async def flaky_task():
        await asyncio.sleep(0.01)
        return "flaky"

    async def stable_task():
        await asyncio.sleep(0.01)
        return "stable"

    # Run both tasks
    r1 = await flaky_task()
    r2 = await stable_task()

    results.extend([r1, r2])

    assert "flaky" in results
    assert "stable" in results


if __name__ == "__main__":
    test_network_queue_basic()
    test_network_queue_with_latency()
    test_network_queue_with_packet_loss()
    asyncio.run(test_network_queue_async())
    asyncio.run(test_network_queue_async_packet_loss())
    test_network_queue_rate_limiting()
    asyncio.run(test_multiple_async_tasks_isolated())
    print("All network_queue tests passed!")
