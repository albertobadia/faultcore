import faultcore


def test_timeout_decorator_sets_policy_attribute():
    @faultcore.timeout(1000)
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_retry_decorator_sets_policy_attribute():
    @faultcore.retry(3, backoff_ms=100)
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_fallback_decorator_sets_policy_attribute():
    @faultcore.fallback(lambda: "fallback")
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_circuit_breaker_decorator_sets_policy_attribute():
    @faultcore.circuit_breaker(5)
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_rate_limit_decorator_sets_policy_attribute():
    @faultcore.rate_limit(10.0, 100)
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_network_queue_decorator_sets_policy_attribute():
    @faultcore.network_queue(rate="1000", capacity="100")
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")
    assert func._faultcore_policy is not None


def test_retry_decorator_with_retry_on_string_types_sets_policy():
    @faultcore.retry(3, backoff_ms=100, retry_on=["ValueError", "TimeoutError"])
    def func():
        return "ok"

    assert hasattr(func, "_faultcore_policy")


def test_decorator_preserves_function_name():
    @faultcore.timeout(1000)
    def my_function():
        return "ok"

    assert my_function.__name__ == "my_function"


def test_decorator_preserves_function_docstring():
    @faultcore.timeout(1000)
    def my_function():
        """This is my docstring."""
        return "ok"

    assert my_function.__doc__ == "This is my docstring."


def test_decorator_preserves_function_module():
    @faultcore.timeout(1000)
    def my_function():
        return "ok"

    assert my_function.__module__ is not None
