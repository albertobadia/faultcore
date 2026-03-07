import pytest

from faultcore import fault, get_policy_registry


def test_register_policy_full_config():
    registry = get_policy_registry()

    registry.register_policy(
        "complex_policy",
        {
            "l4_transport": [
                {"type": "timeout", "timeout_ms": 1000},
            ],
            "l2_qos": [
                {"type": "rate_limit", "rate": 100, "capacity": 10},
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
