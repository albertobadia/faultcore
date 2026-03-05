import faultcore


def test_feature_flag_manager_register():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "test_feature",
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
    config = manager.get("test_feature")
    assert config is not None
    assert config["timeout_ms"] == 1000


def test_feature_flag_manager_register_multiple_params():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "multi_feature",
        timeout_ms=500,
        retry_max_retries=3,
        retry_backoff_ms=100,
        retry_on=None,
        circuit_breaker_failure_threshold=5,
        circuit_breaker_success_threshold=2,
        circuit_breaker_timeout_ms=30000,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )
    config = manager.get("multi_feature")
    assert config is not None
    assert config["timeout_ms"] == 500
    assert config["retry_max_retries"] == 3
    assert config["retry_backoff_ms"] == 100
    assert config["circuit_breaker_failure_threshold"] == 5
    assert config["rate_limit_rate"] == 10.0
    assert config["rate_limit_capacity"] == 100


def test_feature_flag_manager_update():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "update_test",
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
    result = manager.update(
        "update_test",
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
    config = manager.get("update_test")
    assert config["timeout_ms"] == 2000


def test_feature_flag_manager_update_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.update(
        "nonexistent",
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


def test_feature_flag_manager_enable():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "enable_test",
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
    assert manager.is_enabled("enable_test") is True
    manager.disable("enable_test")
    assert manager.is_enabled("enable_test") is False
    manager.enable("enable_test")
    assert manager.is_enabled("enable_test") is True


def test_feature_flag_manager_disable():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "disable_test",
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
    result = manager.disable("disable_test")
    assert result is True
    assert manager.is_enabled("disable_test") is False


def test_feature_flag_manager_disable_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.disable("nonexistent")
    assert result is False


def test_feature_flag_manager_enable_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.enable("nonexistent")
    assert result is False


def test_feature_flag_manager_is_enabled_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.is_enabled("nonexistent")
    assert result is False


def test_feature_flag_manager_get_nonexistent():
    manager = faultcore.FeatureFlagManager()
    config = manager.get("nonexistent")
    assert config is None


def test_feature_flag_manager_list_keys():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "key1",
        timeout_ms=100,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "key2",
        timeout_ms=200,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "key3",
        timeout_ms=300,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    keys = manager.list_keys()
    assert "key1" in keys
    assert "key2" in keys
    assert "key3" in keys
    assert len(keys) == 3


def test_feature_flag_manager_list_keys_empty():
    manager = faultcore.FeatureFlagManager()
    keys = manager.list_keys()
    assert keys == []


def test_feature_flag_manager_remove():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "remove_test",
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
    result = manager.remove("remove_test")
    assert result is True
    config = manager.get("remove_test")
    assert config is None


def test_feature_flag_manager_remove_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.remove("nonexistent")
    assert result is False


def test_feature_flag_manager_clear():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "clear1",
        timeout_ms=100,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "clear2",
        timeout_ms=200,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.clear()
    keys = manager.list_keys()
    assert keys == []


def test_feature_flag_manager_repr():
    manager = faultcore.FeatureFlagManager()
    repr_str = repr(manager)
    assert "FeatureFlagManager" in repr_str


def test_feature_flag_manager_default_enabled():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "default_enabled",
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
    config = manager.get("default_enabled")
    assert config["enabled"] is True


def test_feature_flag_manager_retry_on():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "retry_on_test",
        timeout_ms=None,
        retry_max_retries=None,
        retry_backoff_ms=None,
        retry_on=["ValueError", "TimeoutError"],
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    config = manager.get("retry_on_test")
    assert config is not None
    assert "retry_on" in config
    assert "ValueError" in config["retry_on"]
    assert "TimeoutError" in config["retry_on"]


def test_feature_flag_manager_clone():
    manager1 = faultcore.FeatureFlagManager()
    manager1.register(
        "clone_test_feature",
        timeout_ms=2000,
        retry_max_retries=5,
        retry_backoff_ms=None,
        retry_on=None,
        circuit_breaker_failure_threshold=None,
        circuit_breaker_success_threshold=None,
        circuit_breaker_timeout_ms=None,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    keys_before = manager1.list_keys()
    assert "clone_test_feature" in keys_before
    config_before = manager1.get("clone_test_feature")
    assert config_before is not None
    assert config_before["timeout_ms"] == 2000
    assert config_before["retry_max_retries"] == 5
    manager2 = manager1.clone_manager()
    keys_after = manager2.list_keys()
    assert "clone_test_feature" in keys_after
    config_after = manager2.get("clone_test_feature")
    assert config_after is not None
    assert config_after["timeout_ms"] == 2000
    assert config_after["retry_max_retries"] == 5
