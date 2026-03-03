import faultcore


def test_apply_policy_decorator_basic():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "my_policy",
        timeout_ms=1000,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("my_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_retry():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "retry_policy",
        timeout_ms=None,
        retry_max_retries=3,
        retry_backoff_ms=10,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("retry_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_circuit_breaker():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "cb_policy",
        timeout_ms=None,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=5,
        circuit_breaker_success_threshold=2,
        circuit_breaker_timeout_ms=30000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("cb_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_rate_limit():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "rl_policy",
        timeout_ms=None,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )

    @faultcore.apply_policy("rl_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_disabled():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "disabled_policy",
        timeout_ms=1000,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.disable("disabled_policy")

    @faultcore.apply_policy("disabled_policy")
    def my_func():
        return "result"

    result = my_func()
    assert result == "result"


def test_apply_policy_decorator_multiple_policies():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "multi_policy",
        timeout_ms=1000,
        retry_max_retries=2,
        retry_backoff_ms=10,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("multi_policy")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_with_args():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "args_policy",
        timeout_ms=1000,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("args_policy")
    def my_func(a, b, c=0):
        return a + b + c

    result = my_func(1, 2, c=3)
    assert result == 6


def test_apply_policy_decorator_full_combination():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "full_combination",
        timeout_ms=1000,
        retry_max_retries=2,
        retry_backoff_ms=10,
        retry_on=None,
        circuit_breaker_failure_threshold=5,
        circuit_breaker_success_threshold=2,
        circuit_breaker_timeout_ms=30000,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )

    @faultcore.apply_policy("full_combination")
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"


def test_apply_policy_decorator_only_rate_limit():
    manager = faultcore.FeatureFlagManager()
    manager.clear()
    manager.register(
        "only_rl",
        timeout_ms=None,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=1.0,
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
