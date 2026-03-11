import pytest

import faultcore
from faultcore.decorator import clear_policies


@pytest.fixture(autouse=True)
def clear_policy_registry():
    clear_policies()
    yield
    clear_policies()


def test_register_policy_accepts_hostname_target_for_transport_effects():
    faultcore.register_policy(
        "hostname_transport_match",
        latency_ms=50,
        targets=[{"hostname": "api.foo.com"}],
    )

    policy = faultcore.get_policy("hostname_transport_match")
    assert policy is not None
    assert policy["latency_ms"] == 50


def test_register_policy_rejects_sni_target_for_dns_effects():
    with pytest.raises(ValueError, match=r"DNS-observable selectors"):
        faultcore.register_policy(
            "sni_dns_mismatch",
            dns_timeout_ms=250,
            targets=[{"sni": "api.foo.com"}],
        )


def test_register_policy_rejects_ip_target_for_dns_effects():
    with pytest.raises(ValueError, match=r"DNS-observable selectors"):
        faultcore.register_policy(
            "ip_dns_mismatch",
            dns_delay_ms=120,
            targets=[{"target": "127.0.0.1"}],
        )


def test_register_policy_rejects_hostname_with_port_for_dns_effects():
    with pytest.raises(ValueError, match=r"hostname-only rules"):
        faultcore.register_policy(
            "hostname_dns_port_mismatch",
            dns_timeout_ms=300,
            targets=[{"hostname": "api.foo.com", "port": 443}],
        )


def test_register_policy_accepts_mixed_rules_covering_dns_and_transport():
    faultcore.register_policy(
        "mixed_dns_transport",
        dns_timeout_ms=300,
        latency_ms=40,
        targets=[
            {"hostname": "api.foo.com", "priority": 200},
            {"sni": "api.foo.com", "priority": 100},
        ],
    )

    policy = faultcore.get_policy("mixed_dns_transport")
    assert policy is not None
    assert "dns_profile" in policy
    assert "latency_ms" in policy
    assert len(policy["target_profiles"]) == 2
