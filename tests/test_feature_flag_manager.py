import faultcore


def test_feature_flag_manager_register():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "test_feature",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    config = manager.get("test_feature")
    assert config is not None
    assert config["timeout_ms"] == 1000


def test_feature_flag_manager_register_multiple_params():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "multi_feature",
        timeout_ms=500,
        rate_limit_rate=10.0,
        rate_limit_capacity=100,
    )
    config = manager.get("multi_feature")
    assert config is not None
    assert config["timeout_ms"] == 500
    assert config["rate_limit_rate"] == 10.0
    assert config["rate_limit_capacity"] == 100


def test_feature_flag_manager_update():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "update_test",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    result = manager.update(
        "update_test",
        timeout_ms=2000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is True
    config = manager.get("update_test")
    assert config["timeout_ms"] == 2000


def test_feature_flag_manager_update_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.update(
        "nonexistent",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert result is False


def test_feature_flag_manager_enable():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "enable_test",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    assert manager.is_enabled("enable_test") is True
    manager.disable("enable_test")
    assert manager.is_enabled("enable_test") is False
    manager.enable("enable_test")
    assert manager.is_enabled("enable_test") is True


def test_feature_flag_manager_disable():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "disable_test",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    result = manager.disable("disable_test")
    assert result is True
    assert manager.is_enabled("disable_test") is False


def test_feature_flag_manager_disable_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.disable("nonexistent")
    assert result is False


def test_feature_flag_manager_enable_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.enable("nonexistent")
    assert result is False


def test_feature_flag_manager_is_enabled_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.is_enabled("nonexistent")
    assert result is False


def test_feature_flag_manager_get_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    config = manager.get("nonexistent")
    assert config is None


def test_feature_flag_manager_list_keys():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "key1",
        timeout_ms=100,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "key2",
        timeout_ms=200,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "key3",
        timeout_ms=300,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    keys = manager.list_keys()
    assert "key1" in keys
    assert "key2" in keys
    assert "key3" in keys
    assert len(keys) == 3


def test_feature_flag_manager_list_keys_empty():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    keys = manager.list_keys()
    assert keys == []


def test_feature_flag_manager_remove():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "remove_test",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    result = manager.remove("remove_test")
    assert result is True
    config = manager.get("remove_test")
    assert config is None


def test_feature_flag_manager_remove_nonexistent():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    result = manager.remove("nonexistent")
    assert result is False


def test_feature_flag_manager_clear():
    manager = faultcore.get_feature_flag_manager()
    manager.register(
        "clear1",
        timeout_ms=100,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.register(
        "clear2",
        timeout_ms=200,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    manager.clear()
    keys = manager.list_keys()
    assert keys == []


def test_feature_flag_manager_repr():
    manager = faultcore.get_feature_flag_manager()
    repr_str = repr(manager)
    assert "FeatureFlagManager" in repr_str


def test_feature_flag_manager_default_enabled():
    manager = faultcore.get_feature_flag_manager()
    manager.clear()
    manager.register(
        "default_enabled",
        timeout_ms=1000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    config = manager.get("default_enabled")
    assert config["enabled"] is True


def test_feature_flag_manager_clone():
    manager1 = faultcore.get_feature_flag_manager()
    manager1.clear()
    manager1.register(
        "clone_test_feature",
        timeout_ms=2000,
        rate_limit_rate=None,
        rate_limit_capacity=None,
    )
    keys_before = manager1.list_keys()
    assert "clone_test_feature" in keys_before
    config_before = manager1.get("clone_test_feature")
    assert config_before is not None
    assert config_before["timeout_ms"] == 2000
    manager2 = manager1.clone_manager()
    keys_after = manager2.list_keys()
    assert "clone_test_feature" in keys_after
    config_after = manager2.get("clone_test_feature")
    assert config_after is not None
    assert config_after["timeout_ms"] == 2000
