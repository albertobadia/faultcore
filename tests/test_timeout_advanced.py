import faultcore


def test_timeout_decorator_preserves_function_metadata():
    @faultcore.timeout(1000)
    def my_function():
        """Docstring"""
        pass

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "Docstring"


def test_timeout_policy_repr_contains_timeout():
    policy = faultcore.Timeout(500)
    repr_str = repr(policy)
    assert "500" in repr_str
    assert "TimeoutPolicy" in repr_str


def test_timeout_very_small_value():
    policy = faultcore.Timeout(1)
    assert policy.timeout_ms == 1


def test_timeout_large_value():
    policy = faultcore.Timeout(60000)
    assert policy.timeout_ms == 60000


def test_timeout_function_with_return_value():
    @faultcore.timeout(1000)
    def func_with_return():
        return {"key": "value"}

    result = func_with_return()
    assert result == {"key": "value"}


def test_timeout_function_with_none_return():
    @faultcore.timeout(1000)
    def func_returning_none():
        return None

    result = func_returning_none()
    assert result is None


def test_timeout_function_with_exception():
    @faultcore.timeout(1000)
    def func_raising():
        raise RuntimeError("test error")

    try:
        func_raising()
    except RuntimeError as e:
        assert str(e) == "test error"


def test_timeout_decorator_stacking():
    @faultcore.timeout(1000)
    @faultcore.timeout(500)
    def nested_func():
        return "ok"

    result = nested_func()
    assert result == "ok"


def test_timeout_with_fallback_and_retry():
    call_count = 0

    @faultcore.fallback(lambda: "fallback")
    @faultcore.retry(1, backoff_ms=10)
    @faultcore.timeout(1000)
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("retryable")
        return "success"

    result = func()
    assert result == "success"
    assert call_count == 2


def test_timeout_preserves_wrapped_attribute():
    @faultcore.timeout(1000)
    def my_func():
        return "ok"

    assert hasattr(my_func, "_faultcore_policy")
