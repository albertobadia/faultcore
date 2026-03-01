import faultcore


def test_classify_timeout_exception():
    exc = TimeoutError("operation timed out")
    result = faultcore.classify_exception(exc)
    assert result == "Timeout"


def test_classify_timedout_exception():
    class TimedOutError(Exception):
        pass

    exc = TimedOutError("request timed out")
    result = faultcore.classify_exception(exc)
    assert result == "Timeout"


def test_classify_rate_limit_exception():
    class RateLimitError(Exception):
        pass

    exc = RateLimitError("rate limit exceeded")
    result = faultcore.classify_exception(exc)
    assert result == "RateLimit"


def test_classify_rate_throttle_exception():
    class RateThrottleError(Exception):
        pass

    exc = RateThrottleError("rate throttle applied")
    result = faultcore.classify_exception(exc)
    assert result == "RateLimit"


def test_classify_connection_exception():
    class ConnectionError(Exception):
        pass

    exc = ConnectionError("connection refused")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_network_exception():
    class NetworkError(Exception):
        pass

    exc = NetworkError("network unreachable")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_remote_exception():
    class RemoteError(Exception):
        pass

    exc = RemoteError("remote host disconnected")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_disconnected_exception():
    class DisconnectedError(Exception):
        pass

    exc = DisconnectedError("client disconnected")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_protocol_exception():
    class ProtocolError(Exception):
        pass

    exc = ProtocolError("protocol violation")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_transient_exception():
    class TransientError(Exception):
        pass

    exc = TransientError("transient failure")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"


def test_classify_unknown_exception_defaults_to_transient():
    class UnknownError(Exception):
        pass

    exc = UnknownError("some random error")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"
