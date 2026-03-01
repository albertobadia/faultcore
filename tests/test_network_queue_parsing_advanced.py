import faultcore


def test_parse_size_with_bytes_suffix():
    policy = faultcore.NetworkQueue(rate="1", capacity="100b", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 100


def test_parse_size_with_kb_lowercase():
    policy = faultcore.NetworkQueue(rate="1", capacity="100kb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 100 * 1024


def test_parse_size_with_mb_lowercase():
    policy = faultcore.NetworkQueue(rate="1", capacity="50mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 50 * 1024 * 1024


def test_parse_size_with_gb_lowercase():
    policy = faultcore.NetworkQueue(rate="1", capacity="2gb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 2 * 1024 * 1024 * 1024


def test_parse_size_with_tb():
    try:
        faultcore.NetworkQueue(rate="1", capacity="1tb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    except ValueError:
        pass


def test_parse_size_plain_number():
    policy = faultcore.NetworkQueue(rate="1", capacity="1024", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.capacity == 1024


def test_parse_size_zero():
    try:
        faultcore.NetworkQueue(rate="1", capacity="0", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "invalid" in str(e).lower() or "config" in str(e).lower()


def test_parse_rate_with_bps_suffix():
    policy = faultcore.NetworkQueue(rate="1000bps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 1000.0


def test_parse_rate_with_kbps_lowercase():
    policy = faultcore.NetworkQueue(rate="100kbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 100 * 1024.0


def test_parse_rate_with_mbps_lowercase():
    policy = faultcore.NetworkQueue(rate="10mbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 10 * 1024.0 * 1024.0


def test_parse_rate_with_gbps_lowercase():
    policy = faultcore.NetworkQueue(rate="1gbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 1 * 1024.0 * 1024.0 * 1024.0


def test_parse_rate_plain_number():
    policy = faultcore.NetworkQueue(rate="1000", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy.rate == 1000.0


def test_parse_rate_decimal():
    policy = faultcore.NetworkQueue(rate="1.5mbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    expected = 1.5 * 1024.0 * 1024.0
    assert policy.rate == expected


def test_parse_rate_fractional():
    policy = faultcore.NetworkQueue(rate="0.5mbps", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    expected = 0.5 * 1024.0 * 1024.0
    assert policy.rate == expected


def test_parse_size_invalid_format():
    try:
        faultcore.NetworkQueue(rate="1", capacity="invalid_size", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "invalid" in str(e).lower() or "value" in str(e).lower()


def test_parse_rate_invalid_format():
    try:
        faultcore.NetworkQueue(rate="invalid_rate", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "invalid" in str(e).lower() or "value" in str(e).lower()


def test_packet_loss_zero():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy is not None


def test_packet_loss_full():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=1.0, latency_ms=0)
    assert policy is not None


def test_packet_loss_invalid_negative():
    try:
        faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=-0.5, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "packet" in str(e).lower()


def test_packet_loss_invalid_over():
    try:
        faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=1.5, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "packet" in str(e).lower()


def test_max_queue_size_zero():
    try:
        faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=0, packet_loss=0.0, latency_ms=0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "config" in str(e).lower()


def test_max_queue_size_large():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=1000000, packet_loss=0.0, latency_ms=0)
    assert policy is not None


def test_latency_zero():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy is not None


def test_latency_large():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=60000)
    assert policy is not None


def test_latency_min_max():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=100)
    assert policy is not None


def test_strategy_default():
    policy = faultcore.NetworkQueue(rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0)
    assert policy is not None


def test_strategy_reject():
    policy = faultcore.NetworkQueue(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="reject"
    )
    assert policy is not None


def test_strategy_wait():
    policy = faultcore.NetworkQueue(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="wait"
    )
    assert policy is not None


def test_strategy_case_insensitive():
    policy1 = faultcore.NetworkQueue(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="REJECT"
    )
    policy2 = faultcore.NetworkQueue(
        rate="1", capacity="1mb", max_queue_size=100, packet_loss=0.0, latency_ms=0, strategy="Wait"
    )
    assert policy1 is not None
    assert policy2 is not None
