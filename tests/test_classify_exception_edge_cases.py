import faultcore


def test_classify_exception_case_insensitive_timeout():
    class TIMEOUTException(Exception):
        pass

    exc = TIMEOUTException("operation timed out")
    result = faultcore.classify_exception(exc)
    assert result == "Timeout"


def test_classify_exception_case_insensitive_network():
    class NETWORKException(Exception):
        pass

    exc = NETWORKException("network unreachable")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_exception_case_insensitive_connection():
    class CONNECTIONException(Exception):
        pass

    exc = CONNECTIONException("connection refused")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_exception_case_insensitive_rate_limit():
    class RATELIMITException(Exception):
        pass

    exc = RATELIMITException("rate limit exceeded")
    result = faultcore.classify_exception(exc)
    assert result == "RateLimit"


def test_classify_exception_transient_with_value():
    class ValueErrorCustom(Exception):
        pass

    exc = ValueErrorCustom("some value error")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"


def test_classify_exception_transient_with_runtime():
    class RuntimeErrorCustom(Exception):
        pass

    exc = RuntimeErrorCustom("runtime error")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"


def test_classify_exception_not_type_error():
    class TypeErrorCustom(Exception):
        pass

    exc = TypeErrorCustom("type error occurred")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"


def test_classify_exception_disconnected():
    class DisconnectedException(Exception):
        pass

    exc = DisconnectedException("client disconnected")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_exception_remote():
    class RemoteException(Exception):
        pass

    exc = RemoteException("remote host unreachable")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_exception_protocol():
    class ProtocolException(Exception):
        pass

    exc = ProtocolException("protocol error")
    result = faultcore.classify_exception(exc)
    assert result == "Network"


def test_classify_exception_transient_standalone():
    class TransientFailure(Exception):
        pass

    exc = TransientFailure("transient failure")
    result = faultcore.classify_exception(exc)
    assert result == "Transient"


def test_classify_exception_timedout_variant():
    class TimedOutException(Exception):
        pass

    exc = TimedOutException("connection timed out")
    result = faultcore.classify_exception(exc)
    assert result == "Timeout"


def test_classify_exception_rate_throttle_variant():
    class RateThrottleException(Exception):
        pass

    exc = RateThrottleException("throttled")
    result = faultcore.classify_exception(exc)
    assert result == "RateLimit"
