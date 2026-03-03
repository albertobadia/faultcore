import faultcore


def test_register_policy_bundle_basic():
    manager = faultcore.FeatureFlagManager()
    manager.register(
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


def test_register_policy_bundle_full_params():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "full_bundle",
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
    config = manager.get("full_bundle")
    assert config is not None
    assert config.get("timeout_ms") == 500
    assert config.get("retry_max_retries") == 3
    assert config.get("retry_backoff_ms") == 100
    assert config.get("circuit_breaker_failure_threshold") == 5
    assert config.get("rate_limit_rate") == 10.0
    assert config.get("rate_limit_capacity") == 100


def test_update_policy_bundle():
    manager = faultcore.FeatureFlagManager()
    manager.register(
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
    result = manager.update(
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


def test_update_policy_bundle_nonexistent():
    manager = faultcore.FeatureFlagManager()
    result = manager.update(
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


def test_update_policy_bundle_partial():
    manager = faultcore.FeatureFlagManager()
    manager.register(
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
    result = manager.update(
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


def test_register_policy_bundle_multiple():
    manager = faultcore.FeatureFlagManager()
    manager.register(
        "bundle1",
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
        "bundle2",
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
    keys = manager.list_keys()
    assert "bundle1" in keys
    assert "bundle2" in keys
