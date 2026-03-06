import pytest

import faultcore
from faultcore import fault, fault_context, get_policy_registry


def test_thread_policy_override():
    registry = get_policy_registry()
    registry.register_timeout_layer("p1", 100)
    registry.register_timeout_layer("p2", 200)

    @fault("p1")
    def my_func():
        return "ok"

    # Default should be p1
    assert my_func() == "ok"

    # Override with p2
    with fault_context("p2"):
        assert my_func() == "ok"

    # Back to p1
    assert my_func() == "ok"


def test_dynamic_matching_auto():
    registry = get_policy_registry()
    registry.remove_all_rules()

    # Register two policies
    registry.register_timeout_layer("fast", 50)
    registry.register_timeout_layer("slow", 5000)

    # Add a rule: if host is "api.example.com", use "slow"
    # Note: currently CallContext in execute_policy is default (None for host)
    # We need to verify that "auto" defaults to something safe if no match

    @fault("auto")
    def auto_func():
        return "ok"

    assert auto_func() == "ok"


def test_rule_priority_matching():
    registry = get_policy_registry()
    registry.remove_all_rules()

    registry.register_timeout_layer("p_high", 100)
    registry.register_timeout_layer("p_low", 200)

    # Generic protocol-agnostic matching using key-value tags
    registry.add_rule("p_low", [{"type": "key", "key": "service", "value": "auth"}], 1)
    registry.add_rule("p_high", [{"type": "key", "key": "service", "value": "auth"}], 10)

    # match_policy returns None if no match, which is correct for default ctx
    ctx = faultcore.CallContext("test")
    assert registry.match_policy(ctx) is None

    # Now set tag to match
    ctx.set_tag("service", "auth")
    assert registry.match_policy(ctx) == "p_high"


if __name__ == "__main__":
    pytest.main([__file__])
