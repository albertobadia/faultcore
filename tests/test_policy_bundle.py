import faultcore


def test_register_policy_bundle_basic():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "test_bundle",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    config = manager.get("test_bundle")
    assert config is not None
    assert config.get("timeout_ms") == 1000


def test_register_policy_bundle_full_params():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "full_bundle",
        timeout_ms=500,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )
    config = manager.get("full_bundle")
    assert config is not None
    assert config.get("timeout_ms") == 500
    assert config.get("rate_limit_rate") == 10.0
    assert config.get("rate_limit_capacity") == 100
    assert "retry_max_retries" not in config
    assert "circuit_breaker_failure_threshold" not in config


def test_update_policy_bundle():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "update_bundle",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    result = manager.update(
        "update_bundle",
        timeout_ms=2000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is True
    config = manager.get("update_bundle")
    assert config.get("timeout_ms") == 2000


def test_update_policy_bundle_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.update(
        "nonexistent_bundle",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is False


def test_update_policy_bundle_partial():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "partial_update",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    result = manager.update(
        "partial_update",
        timeout_ms=None,
        rate_limit_rate=5.0,
        rate_limit_capacity=50,
    )
    assert result is True
    config = manager.get("partial_update")
    assert config.get("timeout_ms") == 1000
    assert config.get("rate_limit_rate") == 5.0
    assert config.get("rate_limit_capacity") == 50


def test_register_policy_bundle_multiple():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "bundle1",
        timeout_ms=100,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "bundle2",
        timeout_ms=200,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    keys = manager.list_keys()
    assert "bundle1" in keys
    assert "bundle2" in keys
