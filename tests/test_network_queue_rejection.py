from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_reject_strategy_creation():
    policy = NetworkQueuePolicy(
        rate="1", capacity="1", max_queue_size=1, packet_loss=0.0, latency_ms=0, strategy="reject"
    )
    assert policy is not None


def test_network_queue_reject_strategy_error_type():
    policy = NetworkQueuePolicy(
        rate="1", capacity="1", max_queue_size=1, packet_loss=0.0, latency_ms=0, strategy="reject"
    )

    def dummy():
        return "ok"

    policy(dummy, (), {})

    try:
        policy(dummy, (), {})
        raise AssertionError("Expected ResourceWarning")
    except Exception as e:
        assert "ResourceWarning" in type(e).__name__ or "queue" in str(e).lower() or "limit" in str(e).lower()


def test_network_queue_wait_strategy_no_error():
    policy = NetworkQueuePolicy(
        rate="1", capacity="1", max_queue_size=1, packet_loss=0.0, latency_ms=0, strategy="wait"
    )

    def dummy():
        return "ok"

    policy(dummy, (), {})

    result = policy(dummy, (), {})
    assert result == "ok"


def test_network_queue_strategy_case_insensitive():
    policy1 = NetworkQueuePolicy(
        rate="1", capacity="1", max_queue_size=1, packet_loss=0.0, latency_ms=0, strategy="REJECT"
    )
    policy2 = NetworkQueuePolicy(
        rate="1", capacity="1", max_queue_size=1, packet_loss=0.0, latency_ms=0, strategy="Wait"
    )
    assert policy1 is not None
    assert policy2 is not None
