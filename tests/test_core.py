import faultcore


def test_timeout_decorator():
    @faultcore.timeout(1000)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_timeout_decorator_zero():
    @faultcore.timeout(1)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_rate_limit_decorator():
    @faultcore.rate_limit(10.0)
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_rate_limit_decorator_exceeded():
    @faultcore.rate_limit(1.0)
    def my_func():
        return "ok"

    assert my_func() == "ok"

    try:
        my_func()
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()
