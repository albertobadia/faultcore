import asyncio

import faultcore
from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_get_stats():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    stats = policy.get_stats()
    assert isinstance(stats, dict)
    assert "enqueued" in stats
    assert "dequeued" in stats
    assert "rejected" in stats
    assert "dropped" in stats
    assert "current_queue_size" in stats


def test_network_queue_stats_initial_values():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    stats = policy.get_stats()
    assert stats["enqueued"] == 0
    assert stats["dequeued"] == 0
    assert stats["rejected"] == 0
    assert stats["dropped"] == 0
    assert stats["current_queue_size"] == 0


def test_network_queue_queue_size_getter():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    initial_size = policy.queue_size
    assert isinstance(initial_size, int)
    assert initial_size >= 0


def test_network_queue_available_tokens_getter():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    tokens = policy.available_tokens
    assert isinstance(tokens, float)
    assert tokens >= 0


def test_network_queue_rate_getter():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    rate = policy.rate
    assert isinstance(rate, float)
    assert rate == 1000.0


def test_network_queue_capacity_getter():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    capacity = policy.capacity
    assert isinstance(capacity, int)
    assert capacity == 100


def test_network_queue_repr():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    repr_str = repr(policy)
    assert "1000" in repr_str
    assert "100" in repr_str


def test_network_queue_repr_contains_rate():
    policy = NetworkQueuePolicy(rate="1gbps", capacity="10mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    repr_str = repr(policy)
    assert "NetworkQueuePolicy" in repr_str


def test_network_queue_stats_after_enqueue():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)

    def dummy_func():
        return "ok"

    policy(dummy_func, (), {})

    stats = policy.get_stats()
    assert stats["enqueued"] >= 1


async def test_async_network_queue_works():
    @faultcore.network_queue(rate="1000", capacity="100")
    async def async_network_call():
        await asyncio.sleep(0.001)
        return "ok"

    result = await async_network_call()
    assert result == "ok"
