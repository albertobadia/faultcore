import pytest

from faultcore import fault, get_policy_registry


def test_register_policy_full_config():
    registry = get_policy_registry()

    def my_fallback_fn(exception=None):
        return "fallback_success"

    registry.register_policy(
        "complex_policy",
        {
            "l4_transport": [
                {"type": "timeout", "timeout_ms": 1000},
                {"type": "circuit_breaker", "failure_threshold": 3, "timeout_ms": 5000},
            ],
            "l3_routing": [
                {"type": "retry", "max_retries": 2, "backoff_ms": 10},
                {"type": "fallback", "fn": my_fallback_fn},
            ],
            "l2_qos": [
                {"type": "rate_limit", "rate": 100.0, "capacity": 10.0},
            ],
            "l1_chaos": [
                {"type": "latency", "latency_ms": 50},
                {"type": "packet_loss", "ppm": 100},
            ],
        },
    )

    assert registry.is_policy_enabled("complex_policy")

    @fault("complex_policy")
    def my_func():
        return "ok"

    assert my_func() == "ok"


def test_register_policy_invalid_type():
    registry = get_policy_registry()
    with pytest.raises(ValueError, match="Unknown L4 type: unknown_type"):
        registry.register_policy(
            "invalid_policy",
            {
                "l4_transport": [{"type": "unknown_type"}],
            },
        )


if __name__ == "__main__":
    pytest.main([__file__])
