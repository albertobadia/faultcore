import faultcore


def test_fallback_invoked_on_failure():
    fallback_called = []

    @faultcore.fallback(lambda: fallback_called.append(True) or "fallback_result")
    def failing_func():
        raise ValueError("error")

    result = failing_func()
    assert result == "fallback_result"
    assert len(fallback_called) == 1


def test_fallback_with_exception_passed_when_fallback_also_fails():
    caught_exceptions = []

    def fallback_func(exception=None):
        caught_exceptions.append(exception)
        if exception is None:
            raise RuntimeError("first call - no exception")

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("test error")

    try:
        failing_func()
    except RuntimeError:
        pass

    assert len(caught_exceptions) == 2
    assert caught_exceptions[0] is None
    assert caught_exceptions[1] is None


def test_fallback_with_args_and_kwargs():
    received_args = []
    received_kwargs = {}

    def fallback_func(*args, **kwargs):
        received_args.append(args)
        received_kwargs.update(kwargs)
        return "fallback"

    @faultcore.fallback(fallback_func)
    def failing_func(a, b, c=0):
        raise ValueError("test error")

    result = failing_func(1, 2, c=3)
    assert result == "fallback"
    assert received_args == [(1, 2)]
    assert received_kwargs == {"c": 3}


def test_fallback_when_function_succeeds_no_exception():
    @faultcore.fallback(lambda: "fallback")
    def successful_func():
        return "success"

    result = successful_func()
    assert result == "success"


def test_fallback_lambda_with_no_args():
    @faultcore.fallback(lambda: "fallback_value")
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == "fallback_value"


def test_fallback_lambda_with_args_and_kwargs():
    @faultcore.fallback(lambda *args, **kwargs: sum(args) + sum(kwargs.values()))
    def func(a, b, c=0):
        raise ValueError("fail")

    result = func(1, 2, c=3)
    assert result == 6


def test_fallback_lambda_with_only_kwargs():
    @faultcore.fallback(lambda *args, **kwargs: "fallback")
    def func_with_default(a, b=0):
        raise ValueError("fail")

    result = func_with_default(1, b=10)
    assert result == "fallback"


def test_fallback_retry_with_fallback_success():
    call_count = 0
    fallback_called = []

    @faultcore.fallback(lambda: fallback_called.append(True) or "fallback")
    @faultcore.retry(1, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("retryable")
        raise RuntimeError("not retryable")

    result = failing_func()
    assert result == "fallback"
    assert call_count == 2


def test_fallback_multiple_decorators_order():
    call_order = []

    @faultcore.fallback(lambda: "fallback")
    @faultcore.timeout(1000)
    def failing_func():
        call_order.append("func")
        raise ValueError("error")

    result = failing_func()
    assert result == "fallback"
    assert call_order == ["func"]


def test_fallback_preserves_args_on_success():
    received_args = []

    @faultcore.fallback(lambda: "fallback")
    def successful_func(a, b, c=0):
        received_args.append((a, b, c))
        return "success"

    result = successful_func(1, 2, c=3)
    assert result == "success"
    assert received_args == [(1, 2, 3)]


def test_fallback_does_not_pass_exception_on_first_call():
    received_kwargs = {}

    def fallback_func(**kwargs):
        received_kwargs.update(kwargs)
        return "fallback"

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("test error")

    result = failing_func()
    assert result == "fallback"
    assert "exception" not in received_kwargs


def test_fallback_passes_exception_when_fallback_also_fails():
    call_count = [0]

    def fallback_func(*args, **kwargs):
        call_count[0] += 1
        raise ValueError("fallback fails")

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("original error")

    try:
        failing_func()
    except ValueError:
        pass

    assert call_count[0] == 2


def test_fallback_with_mixed_args():
    args_received = []
    kwargs_received = {}

    def fallback_func(*args, **kwargs):
        args_received.extend(args)
        kwargs_received.update(kwargs)
        return "fallback"

    @faultcore.fallback(fallback_func)
    def failing_func(a, b=1, *args, c=2, **kwargs):
        raise ValueError("fail")

    result = failing_func(10, 20, 30, c=40, x=50)
    assert result == "fallback"
    assert args_received == [10, 20, 30]
    assert kwargs_received == {"c": 40, "x": 50}


def test_fallback_repr():
    policy = faultcore.Fallback(lambda: "fallback")
    repr_str = repr(policy)
    assert "FallbackPolicy" in repr_str
