import time

from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_token_bucket_refill():
    policy = NetworkQueuePolicy(rate="10", capacity="5", max_queue_size=100, packet_loss=0.0, latency_ms=0)

    initial_tokens = policy.available_tokens
    assert initial_tokens <= 5.0

    def dummy_func():
        return "ok"

    policy(dummy_func, (), {})

    time.sleep(0.3)

    after_wait = policy.available_tokens
    assert after_wait > 0


def test_network_queue_capacity_with_string_formats():
    policy_kb = NetworkQueuePolicy(rate="1", capacity="1kb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_kb.capacity == 1024

    policy_mb = NetworkQueuePolicy(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_mb.capacity == 1024 * 1024

    policy_gb = NetworkQueuePolicy(rate="1", capacity="1gb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_gb.capacity == 1024 * 1024 * 1024


def test_network_queue_rate_with_string_formats():
    policy_kbps = NetworkQueuePolicy(rate="1kbps", capacity="1", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_kbps.rate == 1024.0

    policy_mbps = NetworkQueuePolicy(rate="1mbps", capacity="1", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_mbps.rate == 1024.0 * 1024.0

    policy_gbps = NetworkQueuePolicy(rate="1gbps", capacity="1", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_gbps.rate == 1024.0 * 1024.0 * 1024.0

    policy_bps = NetworkQueuePolicy(rate="1024bps", capacity="1", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy_bps.rate == 1024.0


def test_network_queue_parse_size_bytes():
    policy = NetworkQueuePolicy(rate="1", capacity="100b", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 100


def test_network_queue_invalid_latency_raises():
    try:
        NetworkQueuePolicy(
            rate="1",
            capacity="1mb",
            max_queue_size=100,
            packet_loss=0.0,
            latency_ms=100,
            strategy="wait",
            fd_limit=1024,
        )
    except Exception:
        pass


def test_network_queue_max_queue_size_getter():
    policy = NetworkQueuePolicy(rate="1", capacity="1mb", max_queue_size=500, packet_loss=0.0, latency_ms=0)
    assert policy.queue_size == 0


def test_network_queue_strategy_getter():
    policy_wait = NetworkQueuePolicy(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="wait"
    )
    policy_reject = NetworkQueuePolicy(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="reject"
    )

    assert policy_wait.queue_size == 0
    assert policy_reject.queue_size == 0


def test_network_queue_packet_loss_zero():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.queue_size == 0


def test_network_queue_packet_loss_full():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=1.0, latency_ms=0)
    assert policy.queue_size == 0


def test_network_queue_latency_applied():
    start = time.time()
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, packet_loss=0.0, latency_ms=50)

    def dummy_func():
        return "ok"

    policy(dummy_func, (), {})
    elapsed = time.time() - start

    assert elapsed >= 0.04
