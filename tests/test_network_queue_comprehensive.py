import asyncio

import faultcore
from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_with_high_bandwidth():
    policy = NetworkQueuePolicy(rate="10gbps", capacity="100mb", max_queue_size=1000, packet_loss=0.0, latency_ms=0)
    assert policy.rate >= 10 * 1024 * 1024 * 1024


def test_network_queue_with_low_bandwidth():
    policy = NetworkQueuePolicy(rate="1kbps", capacity="1kb", max_queue_size=10, packet_loss=0.0, latency_ms=0)
    assert policy.rate < 10000


def test_network_queue_latency_only():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=100)
    assert policy is not None


def test_network_queue_packet_loss_only():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.3, latency_ms=0)
    assert policy is not None


def test_network_queue_zero_latency():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy is not None


def test_network_queue_combined_latency_and_packet_loss():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.2, latency_ms=50)
    assert policy is not None


async def test_async_network_queue_sequential_calls():
    @faultcore.network_queue(rate="1000", capacity="100")
    async def async_call():
        await asyncio.sleep(0.001)
        return "ok"

    results = []
    for _ in range(5):
        result = await async_call()
        results.append(result)

    assert all(r == "ok" for r in results)


async def test_async_network_queue_concurrent_calls():
    @faultcore.network_queue(rate="1000", capacity="100", latency_ms=10)
    async def async_call():
        await asyncio.sleep(0.001)
        return "ok"

    results = await asyncio.gather(*[async_call() for _ in range(5)])
    assert all(r == "ok" for r in results)


def test_network_queue_stats_dequeued_increments():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)

    def dummy():
        return "ok"

    policy(dummy, (), {})

    stats = policy.get_stats()
    assert stats["dequeued"] >= 1


def test_network_queue_stats_dropped_with_full_loss():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=1.0, latency_ms=0)

    def dummy():
        return "ok"

    policy(dummy, (), {})

    stats = policy.get_stats()
    assert "dropped" in stats
