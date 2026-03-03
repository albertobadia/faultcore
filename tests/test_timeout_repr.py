import faultcore


def test_timeout_repr_contains_timeout_value():
    policy = faultcore.Timeout(500)
    repr_str = repr(policy)
    assert "500" in repr_str


def test_timeout_repr_contains_timeout_policy():
    policy = faultcore.Timeout(500)
    repr_str = repr(policy)
    assert "Timeout" in repr_str


def test_timeout_very_large_value():
    policy = faultcore.Timeout(3600000)
    assert policy.timeout_ms == 3600000


def test_timeout_function_returns_complex_object():
    @faultcore.timeout(1000)
    def func_returning_dict():
        return {"key": [1, 2, 3], "nested": {"a": "b"}}

    result = func_returning_dict()
    assert result == {"key": [1, 2, 3], "nested": {"a": "b"}}


def test_timeout_function_returns_tuple():
    @faultcore.timeout(1000)
    def func_returning_tuple():
        return (1, 2, 3)

    result = func_returning_tuple()
    assert result == (1, 2, 3)


def test_timeout_function_returns_list():
    @faultcore.timeout(1000)
    def func_returning_list():
        return [1, 2, 3]

    result = func_returning_list()
    assert result == [1, 2, 3]


def test_timeout_function_raises_exception_with_message():
    @faultcore.timeout(1000)
    def func_raising():
        raise ValueError("specific error message")

    try:
        func_raising()
    except ValueError as e:
        assert str(e) == "specific error message"


def test_timeout_function_raises_custom_exception():
    class CustomError(Exception):
        pass

    @faultcore.timeout(1000)
    def func_raising():
        raise CustomError("custom")

    try:
        func_raising()
    except CustomError:
        pass
