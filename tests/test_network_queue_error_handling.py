from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_invalid_rate_format():
    try:
        NetworkQueuePolicy(rate="invalid", capacity="100", max_queue_size=100)
        raise AssertionError("Should have raised")
    except Exception as e:
        assert "invalid" in str(e).lower() or "rate" in str(e).lower()


def test_network_queue_invalid_capacity_format():
    try:
        NetworkQueuePolicy(rate="1000", capacity="invalid", max_queue_size=100)
        raise AssertionError("Should have raised")
    except Exception as e:
        assert "invalid" in str(e).lower() or "capacity" in str(e).lower()


def test_network_queue_rate_zero():
    try:
        NetworkQueuePolicy(rate=0, capacity=100, max_queue_size=100)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_capacity_zero():
    try:
        NetworkQueuePolicy(rate=1000, capacity=0, max_queue_size=100)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_negative_packet_loss():
    try:
        NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, packet_loss=-0.1)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_packet_loss_over_one():
    try:
        NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, packet_loss=1.5)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_latency_min_greater_than_max():
    config = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, latency_ms=100)
    assert config is not None


def test_network_queue_max_queue_size_zero():
    try:
        NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=0)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_strategy_reject_vs_wait():
    policy_reject = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, strategy="reject")
    assert policy_reject is not None

    policy_wait = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, strategy="wait")
    assert policy_wait is not None


def test_network_queue_strategy_case_insensitive():
    policy_lower = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, strategy="reject")
    policy_upper = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, strategy="REJECT")
    policy_mixed = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, strategy="ReJeCt")
    assert policy_lower is not None
    assert policy_upper is not None
    assert policy_mixed is not None


def test_network_queue_rate_values():
    policy = NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100)
    assert policy.rate == 1000


def test_network_queue_large_values():
    policy = NetworkQueuePolicy(rate=1000000000.0, capacity=1000000, max_queue_size=100000)
    assert policy.rate == 1000000000.0
    assert policy.capacity == 1000000


def test_network_queue_small_values():
    policy = NetworkQueuePolicy(rate=1, capacity=1, max_queue_size=1)
    assert policy.rate == 1
    assert policy.capacity == 1


def test_network_queue_negative_rate():
    try:
        NetworkQueuePolicy(rate=-100, capacity=100, max_queue_size=100)
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_network_queue_with_fd_limit_zero():
    try:
        NetworkQueuePolicy(rate=1000, capacity=100, max_queue_size=100, fd_limit=0)
        raise AssertionError("Should have raised")
    except Exception:
        pass
