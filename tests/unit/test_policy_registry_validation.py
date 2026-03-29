import pytest

import faultcore
from faultcore.decorator import clear_policies


@pytest.fixture(autouse=True)
def clear_policy_registry() -> None:
    clear_policies()
    yield
    clear_policies()


def test_register_policy_accepts_hostname_target_for_transport_effects() -> None:
    faultcore.register_policy(
        "hostname_transport_match",
        latency="50ms",
        targets=[{"hostname": "api.foo.com"}],
    )

    policy = faultcore.get_policy("hostname_transport_match")
    assert policy is not None
    assert policy["latency"] == 50


@pytest.mark.parametrize(
    ("policy_name", "dns_profile", "targets", "error_match"),
    [
        (
            "sni_dns_mismatch",
            {"timeout": "250ms"},
            [{"sni": "api.foo.com"}],
            r"DNS-observable selectors",
        ),
        (
            "ip_dns_mismatch",
            {"delay": "120ms"},
            [{"host": "127.0.0.1"}],
            r"DNS-observable selectors",
        ),
        (
            "hostname_dns_port_mismatch",
            {"timeout": "300ms"},
            [{"hostname": "api.foo.com", "port": 443}],
            r"hostname-only rules",
        ),
    ],
)
def test_register_policy_rejects_non_dns_observable_target_rules(
    policy_name, dns_profile, targets, error_match
) -> None:
    with pytest.raises(ValueError, match=error_match):
        faultcore.register_policy(
            policy_name,
            dns=dns_profile,
            targets=targets,
        )


def test_register_policy_accepts_mixed_rules_covering_dns_and_transport() -> None:
    faultcore.register_policy(
        "mixed_dns_transport",
        dns={"timeout": "300ms"},
        latency="40ms",
        targets=[
            {"hostname": "api.foo.com", "priority": 200},
            {"sni": "api.foo.com", "priority": 100},
        ],
    )

    policy = faultcore.get_policy("mixed_dns_transport")
    assert policy is not None
    assert "dns_profile" in policy
    assert "latency" in policy
    assert len(policy["target_profiles"]) == 2


def test_register_policy_rejects_dns_non_mapping() -> None:
    with pytest.raises(ValueError, match=r"dns must be a mapping"):
        faultcore.register_policy(
            "dns_invalid_type",
            dns="invalid",  # type: ignore[arg-type]
        )
