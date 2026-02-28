import faultcore


def test_timeout_decorator():
    @faultcore.timeout(1000)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_retry_decorator():
    @faultcore.retry(3, backoff_ms=100)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_fallback_decorator():
    @faultcore.fallback(lambda: "default")
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_circuit_breaker_decorator():
    @faultcore.circuit_breaker(5)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_rate_limit_decorator():
    @faultcore.rate_limit(10.0, 100)
    def my_func():
        return "ok"

    assert my_func() == "ok"
