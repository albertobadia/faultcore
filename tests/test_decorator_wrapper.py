import faultcore


def test_timeout_decorator_sets_policy_attribute():
    @faultcore.timeout(1000)
    def func():
        return "ok"

    assert func() == "ok"


def test_rate_limit_decorator_sets_policy_attribute():
    @faultcore.rate_limit(10.0)
    def func():
        return "ok"

    assert func() == "ok"


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
