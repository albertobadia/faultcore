import faultcore


def test_network_queue_parse_size_kb():
    policy = faultcore.NetworkQueue(rate="1", capacity="10kb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 10 * 1024


def test_network_queue_parse_size_mb():
    policy = faultcore.NetworkQueue(rate="1", capacity="10mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 10 * 1024 * 1024


def test_network_queue_parse_size_gb():
    policy = faultcore.NetworkQueue(rate="1", capacity="1gb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 1 * 1024 * 1024 * 1024


def test_network_queue_parse_size_plain():
    policy = faultcore.NetworkQueue(rate="1", capacity="1024", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 1024


def test_network_queue_parse_size_invalid():
    try:
        faultcore.NetworkQueue(rate="1", capacity="invalid", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "invalid" in str(e).lower() or "value" in str(e).lower()


def test_network_queue_parse_rate_kbps():
    policy = faultcore.NetworkQueue(rate="100kbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 100 * 1024.0


def test_network_queue_parse_rate_mbps():
    policy = faultcore.NetworkQueue(rate="10mbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 10 * 1024.0 * 1024.0


def test_network_queue_parse_rate_gbps():
    policy = faultcore.NetworkQueue(rate="1gbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    expected = 1 * 1024.0 * 1024.0 * 1024.0
    assert policy.rate == expected


def test_network_queue_parse_rate_plain():
    policy = faultcore.NetworkQueue(rate="1000", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 1000.0


def test_network_queue_parse_rate_invalid():
    try:
        faultcore.NetworkQueue(rate="invalid", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "invalid" in str(e).lower() or "value" in str(e).lower()


def test_network_queue_invalid_packet_loss():
    try:
        faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=1.5, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "packet" in str(e).lower()


def test_network_queue_invalid_rate_zero():
    try:
        faultcore.NetworkQueue(rate="0", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "rate" in str(e).lower()


def test_network_queue_invalid_capacity_zero():
    try:
        faultcore.NetworkQueue(rate="1", capacity="0", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "invalid" in str(e).lower() or "value" in str(e).lower()
