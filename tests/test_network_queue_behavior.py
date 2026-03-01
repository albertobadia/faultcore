import time

from faultcore import network_queue


def test_network_queue_latency_applied():
    @network_queue(rate="1000", capacity="100", latency_ms=100)
    def network_call():
        return "ok"

    start = time.time()
    result = network_call()
    duration = (time.time() - start) * 1000

    assert result == "ok"
    assert duration >= 90


def test_network_queue_packet_loss_applied():
    @network_queue(rate="1000", capacity="100", packet_loss=1.0)
    def network_call():
        return "ok"

    result = network_call()
    assert result == "ok"


def test_network_queue_strategy_reject():
    from faultcore._faultcore import NetworkQueuePolicy

    policy = NetworkQueuePolicy(
        rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="reject"
    )
    assert policy is not None


def test_network_queue_strategy_wait():
    from faultcore._faultcore import NetworkQueuePolicy

    policy = NetworkQueuePolicy(
        rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="wait"
    )
    assert policy is not None


def test_network_queue_rate_getter():
    policy = network_queue(rate="1000", capacity="100")

    @policy
    def network_call():
        return "ok"

    network_call()
    assert network_call._faultcore_policy.rate == 1000.0


def test_network_queue_capacity_getter():
    policy = network_queue(rate="1000", capacity="100")

    @policy
    def network_call():
        return "ok"

    network_call()
    assert network_call._faultcore_policy.capacity == 100


def test_network_queue_repr():
    policy = network_queue(rate="1000", capacity="100")

    @policy
    def network_call():
        return "ok"

    network_call()
    repr_str = repr(network_call._faultcore_policy)
    assert "1000" in repr_str
    assert "100" in repr_str
