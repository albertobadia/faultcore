import time

import faultcore


def test_retry_with_multiple_retry_on_types():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=["ValueError", "TypeError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TypeError("type error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 2


def test_retry_with_string_type_not_in_builtins():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=["CustomError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("not custom")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 2


def test_retry_default_retry_on_includes_transient():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("value error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_custom_error_not_retried():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=["ConnectionError"])
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise KeyError("key error")

    try:
        failing_func()
    except KeyError:
        pass

    assert call_count == 4


def test_retry_empty_retry_on_list_no_retry():
    call_count = 0

    @faultcore.retry(3, backoff_ms=10, retry_on=[])
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("error")

    try:
        failing_func()
    except ValueError:
        pass

    assert call_count == 1


def test_retry_backoff_duration_increases():
    call_times = []

    @faultcore.retry(3, backoff_ms=100)
    def failing_func():
        call_times.append(time.time())
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    assert len(call_times) == 4
    if len(call_times) >= 3:
        gap1 = call_times[1] - call_times[0]
        gap2 = call_times[2] - call_times[1]
        assert gap1 >= 0.09
        assert gap2 >= 0.18


def test_retry_policy_repr_contains_max_retries():
    policy = faultcore.Retry(5, 200, None)
    repr_str = repr(policy)
    assert "5" in repr_str
    assert "200" in repr_str


def test_retry_decorator_preserves_function_metadata():
    @faultcore.retry(3, backoff_ms=10)
    def my_function():
        """Docstring"""
        pass

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "Docstring"
