import pytest

from faultcore.profile_parsers import build_target_profile


def test_build_target_profile_includes_unified_fields_for_ipv4_host():
    profile = build_target_profile(host="10.1.2.3", port=443, protocol="tcp")
    assert profile["address_family"] == 1
    assert profile["addr"] == [10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def test_build_target_profile_accepts_ipv6_host_parameter():
    profile = build_target_profile(host="2001:db8::10", port=443, protocol="tcp")
    assert profile == {
        "enabled": 1,
        "kind": 1,
        "ipv4": 0,
        "prefix_len": 128,
        "port": 443,
        "protocol": 1,
        "priority": 100,
        "address_family": 2,
        "addr": [32, 1, 13, 184, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 16],
    }


def test_build_target_profile_accepts_ipv6_cidr():
    profile = build_target_profile(cidr="2001:db8:abcd::/48", protocol="udp")
    assert profile == {
        "enabled": 1,
        "kind": 2,
        "ipv4": 0,
        "prefix_len": 48,
        "port": 0,
        "protocol": 2,
        "priority": 100,
        "address_family": 2,
        "addr": [32, 1, 13, 184, 171, 205, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    }


def test_build_target_profile_accepts_bracketed_ipv6_target_string():
    profile = build_target_profile(target="tcp://[2001:db8::10]:443")
    assert profile["kind"] == 1
    assert profile["address_family"] == 2
    assert profile["prefix_len"] == 128
    assert profile["port"] == 443
    assert profile["protocol"] == 1
    assert profile["addr"] == [32, 1, 13, 184, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 16]


def test_build_target_profile_rejects_unbracketed_ipv6_target_string():
    with pytest.raises(ValueError, match=r"(?i)bracket"):
        build_target_profile(target="tcp://2001:db8::10:443")


def test_build_target_profile_rejects_invalid_prefix_len_by_family():
    with pytest.raises(ValueError, match=r"(?i)cidr"):
        build_target_profile(cidr="10.0.0.0/33")
    with pytest.raises(ValueError, match=r"(?i)cidr"):
        build_target_profile(cidr="2001:db8::/129")
