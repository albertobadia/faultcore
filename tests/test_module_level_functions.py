import faultcore


def test_register_policy_bundle_basic():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle(
        "test_bundle",
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
    config = manager.get("test_bundle")
    assert config is not None
    assert config.get("timeout_ms") == 1000
    manager.clear()


def test_register_policy_bundle_full_params():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle(
        "full_bundle",
        timeout_ms=500,
        retry_max_retries=3,
        retry_backoff_ms=100,
        retry_on=["ValueError", "TimeoutError"],
        circuit_breaker_failure_threshold=5,
        circuit_breaker_success_threshold=2,
        circuit_breaker_timeout_ms=30000,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )
    config = manager.get("full_bundle")
    assert config is not None
    assert config.get("timeout_ms") == 500
    assert config.get("retry_max_retries") == 3
    assert config.get("retry_backoff_ms") == 100
    assert config.get("circuit_breaker_failure_threshold") == 5
    assert config.get("rate_limit_rate") == 10.0
    assert config.get("rate_limit_capacity") == 100
    manager.clear()


def test_register_policy_bundle_multiple():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle("bundle1", timeout_ms=100)
    faultcore.register_policy_bundle("bundle2", timeout_ms=200)

    keys = manager.list_keys()
    assert "bundle1" in keys
    assert "bundle2" in keys
    manager.clear()


def test_update_policy_bundle_basic():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle(
        "update_bundle",
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

    result = faultcore.update_policy_bundle(
        "update_bundle",
        timeout_ms=2000,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is True
    config = manager.get("update_bundle")
    assert config.get("timeout_ms") == 2000
    manager.clear()


def test_update_policy_bundle_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    result = faultcore.update_policy_bundle(
        "nonexistent_bundle",
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
    assert result is False
    manager.clear()


def test_update_policy_bundle_partial():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle(
        "partial_update",
        timeout_ms=1000,
        retry_max_retries=3,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    result = faultcore.update_policy_bundle(
        "partial_update",
        timeout_ms=None,
        retry_max_retries=5,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is True
    config = manager.get("partial_update")
    assert config.get("timeout_ms") == 1000
    assert config.get("retry_max_retries") == 5
    manager.clear()


def test_get_feature_flag_manager_returns_manager():
    manager = faultcore.get_feature_flag_manager()
    assert manager is not None
    assert hasattr(manager, "register")
    assert hasattr(manager, "update")
    assert hasattr(manager, "get")
    assert hasattr(manager, "is_enabled")


def test_get_feature_flag_manager_cached():
    manager1 = faultcore.get_feature_flag_manager()
    manager2 = faultcore.get_feature_flag_manager()
    assert manager1 is manager2


def test_apply_policy_nonexistent_bundle():
    """When bundle doesn't exist, is_enabled returns False and function passes through."""
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    @faultcore.apply_policy("nonexistent_bundle")
    def my_func():
        return "result_without_policy"

    result = my_func()
    assert result == "result_without_policy"
    manager.clear()


def test_apply_policy_empty_bundle():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()

    faultcore.register_policy_bundle(
        "empty_bundle",
        timeout_ms=None,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )

    @faultcore.apply_policy("empty_bundle")
    def my_func():
        return "result"

    result = my_func()
    assert result == "result"
    manager.clear()
