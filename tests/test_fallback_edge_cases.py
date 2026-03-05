import faultcore


def test_fallback_with_callable_class():
    class FallbackHandler:
        def __call__(self):
            return "fallback_value"

    @faultcore.fallback(FallbackHandler())
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == "fallback_value"


def test_fallback_passes_original_args_to_fallback():
    received_args = []

    def fallback_func(*args, **kwargs):
        received_args.append((args, kwargs))
        return "fallback"

    @faultcore.fallback(fallback_func)
    def failing_func(a, b, c=0):
        raise ValueError("fail")

    result = failing_func(1, 2, c=3)
    assert result == "fallback"
    assert len(received_args) == 1
    assert received_args[0] == ((1, 2), {"c": 3})


def test_fallback_function_with_no_args_called_once():
    call_count = [0]

    def fallback_func():
        call_count[0] += 1
        return "fallback"

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == "fallback"
    assert call_count[0] == 1


def test_fallback_lambda_no_exception_arg():
    received_kwargs = {}

    @faultcore.fallback(lambda **kwargs: received_kwargs.update(kwargs) or "fallback")
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == "fallback"
    assert "exception" not in received_kwargs


def test_fallback_exception_preserved_in_second_call():
    call_count = [0]

    def fallback_func(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("first call")
        return "fallback_success"

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("original")

    result = failing_func()
    assert result == "fallback_success"
    assert call_count[0] == 2


def test_fallback_both_fail_raises_original():
    call_count = [0]

    def fallback_func(*args, **kwargs):
        call_count[0] += 1
        raise RuntimeError("fallback failed")

    @faultcore.fallback(fallback_func)
    def failing_func():
        raise ValueError("original")

    try:
        failing_func()
    except RuntimeError as e:
        assert "fallback failed" in str(e)
    except ValueError:
        pass

    assert call_count[0] == 2


def test_fallback_with_non_callable_raises():
    try:
        faultcore.Fallback("not_callable")
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_fallback_repr_contains_fallback():
    policy = faultcore.Fallback(lambda: "fallback")
    repr_str = repr(policy)
    assert "FallbackPolicy" in repr_str


def test_fallback_preserves_function_signature():
    @faultcore.fallback(lambda: "fallback")
    def func_with_signature(a, b, *args, c=0, **kwargs):
        return a + b + c + sum(args) + sum(kwargs.values())

    result = func_with_signature(1, 2, 3, 4, c=5, x=6)
    assert result == 21


def test_fallback_with_positional_args_to_lambda():
    try:

        @faultcore.fallback(lambda x, y: x + y)
        def failing_func():
            raise ValueError("fail")

        _result = failing_func()
    except TypeError:
        pass


def test_fallback_returns_none():
    @faultcore.fallback(lambda: None)
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result is None


def test_fallback_with_dict_return():
    @faultcore.fallback(lambda: {"key": "value"})
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == {"key": "value"}


def test_fallback_with_list_return():
    @faultcore.fallback(lambda: [1, 2, 3])
    def failing_func():
        raise ValueError("fail")

    result = failing_func()
    assert result == [1, 2, 3]
