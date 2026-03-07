import faultcore


def test_apply_policy_decorator_basic():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "my_policy",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("my_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_rate_limit():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "rl_policy",
        timeout_ms=None,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )

    @faultcore.apply_policy("rl_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_disabled():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "disabled_policy",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.disable("disabled_policy")

    @faultcore.apply_policy("disabled_policy")
    def my_func():
        return "result"

    result = my_func()
    assert result == "result"


def test_apply_policy_decorator_with_args():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "args_policy",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("args_policy")
    def my_func(a, b, c=0):
        return a + b + c

    result = my_func(1, 2, c=3)
    assert result == 6


def test_apply_policy_decorator_only_rate_limit():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "only_rl",
        timeout_ms=None,
        rate_limit_rate=1000.0,
        rate_limit_capacity=1,
    )

    @faultcore.apply_policy("only_rl")
    def my_func():
        return "first"

    result1 = my_func()
    assert result1 == "first"

    try:
        my_func()
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()
