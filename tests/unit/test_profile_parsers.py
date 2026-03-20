import pytest

from faultcore.profile_parsers import (
    build_payload_mutation_profile,
    build_session_budget_profile,
    build_target_profile,
    build_timeout_profile,
    parse_duration,
    parse_rate,
    parse_size,
)


class TestConstantsConsistency:
    """Tests to verify constants are properly defined without duplicates."""

    def test_size_suffix_multipliers_no_duplicates(self):
        """Verify _SIZE_SUFFIX_MULTIPLIERS doesn't have duplicate keys (confusing)."""
        from faultcore.profile_parsers import _SIZE_SUFFIX_MULTIPLIERS

        keys = list(_SIZE_SUFFIX_MULTIPLIERS.keys())
        duplicates = [k for k in keys if keys.count(k) > 1]

        assert len(duplicates) == 0, f"Found duplicate keys in _SIZE_SUFFIX_MULTIPLIERS: {duplicates}"

    def test_rate_suffix_multipliers_no_duplicates(self):
        """Verify _RATE_SUFFIX_MULTIPLIERS doesn't have duplicate keys."""
        from faultcore.profile_parsers import _RATE_SUFFIX_MULTIPLIERS

        keys = list(_RATE_SUFFIX_MULTIPLIERS.keys())
        duplicates = [k for k in keys if keys.count(k) > 1]

        assert len(duplicates) == 0, f"Found duplicate keys in _RATE_SUFFIX_MULTIPLIERS: {duplicates}"

    def test_size_and_rate_suffixes_are_separate(self):
        """Verify that size and rate suffixes are properly separated."""
        from faultcore.profile_parsers import _RATE_SUFFIX_MULTIPLIERS, _SIZE_SUFFIX_MULTIPLIERS

        size_only_suffixes = {"kb", "mb", "gb", "bps"}
        rate_only_suffixes = {"kbps", "mbps", "gbps"}

        for suffix in size_only_suffixes:
            assert suffix in _SIZE_SUFFIX_MULTIPLIERS, f"Size suffix {suffix} missing"

        for suffix in rate_only_suffixes:
            assert suffix in _RATE_SUFFIX_MULTIPLIERS, f"Rate suffix {suffix} missing"


class TestParseSizeEdgeCases:
    """Additional edge case tests for parse_size function."""

    def test_parse_size_case_insensitive(self):
        """Verify parse_size handles case-insensitive input."""
        assert parse_size("1KB") == 1_000
        assert parse_size("1MB") == 1_000_000
        assert parse_size("1GB") == 1_000_000_000

    def test_parse_size_with_decimals(self):
        """Verify parse_size handles decimal values."""
        assert parse_size("1.5kb") == 1500
        assert parse_size("2.5mb") == 2_500_000


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


def test_build_target_profile_accepts_explicit_any_protocol_parameter():
    profile = build_target_profile(host="10.1.2.3", port=443, protocol="any")
    assert profile["protocol"] == 0


def test_build_target_profile_accepts_any_protocol_in_target_string():
    profile = build_target_profile(target="any://10.1.2.3:443")
    assert profile["protocol"] == 0
    assert profile["kind"] == 1
    assert profile["address_family"] == 1


def test_build_target_profile_accepts_port_range():
    profile = build_target_profile(host="10.1.2.3", port="8000-9000")
    assert profile["port"] == 0
    assert profile["port_start"] == 8000
    assert profile["port_end"] == 9000


def test_build_target_profile_rejects_invalid_port_range_order():
    with pytest.raises(ValueError, match=r"(?i)port.*<="):
        build_target_profile(host="10.1.2.3", port="9000-8000")


def test_build_target_profile_rejects_unbracketed_ipv6_target_string():
    with pytest.raises(ValueError, match=r"(?i)bracket"):
        build_target_profile(target="tcp://2001:db8::10:443")


def test_build_target_profile_rejects_invalid_prefix_len_by_family():
    with pytest.raises(ValueError, match=r"(?i)cidr"):
        build_target_profile(cidr="10.0.0.0/33")
    with pytest.raises(ValueError, match=r"(?i)cidr"):
        build_target_profile(cidr="2001:db8::/129")


def test_build_target_profile_accepts_hostname_and_normalizes_punycode_lowercase():
    profile = build_target_profile(hostname="T\u00e4st.FOO.com")
    assert profile["kind"] == 0
    assert profile["hostname"] == "xn--tst-qla.foo.com"
    assert profile["address_family"] == 0


def test_build_target_profile_accepts_sni_wildcard():
    profile = build_target_profile(sni="*.Foo.com")
    assert profile["kind"] == 0
    assert profile["sni"] == "*.foo.com"


def test_build_target_profile_rejects_hostname_and_sni_together():
    with pytest.raises(ValueError, match=r"(?i)both hostname and sni"):
        build_target_profile(hostname="api.foo.com", sni="api.foo.com")


def test_build_target_profile_rejects_mixed_ip_and_semantic_targeting():
    with pytest.raises(ValueError, match=r"(?i)mix host/cidr with hostname/sni"):
        build_target_profile(host="10.1.2.3", hostname="api.foo.com")


def test_build_session_budget_profile_accepts_timeout_action():
    profile = build_session_budget_profile(
        max_tx="1kb",
        max_ops=2,
        action="timeout",
        budget_timeout="25ms",
    )
    assert profile == {
        "max_bytes_tx": 1000,
        "max_ops": 2,
        "action": 2,
        "budget_timeout": 25,
    }


def test_build_session_budget_profile_accepts_connection_error_action():
    profile = build_session_budget_profile(
        max_duration="1s",
        action="connection_error",
        error="unreachable",
    )
    assert profile == {
        "max_duration": 1000,
        "action": 3,
        "error_kind": 3,
    }


def test_build_session_budget_profile_rejects_invalid_combinations():
    with pytest.raises(ValueError, match=r"(?i)at least one limit"):
        build_session_budget_profile(action="drop")
    with pytest.raises(ValueError, match=r"(?i)required.*action=timeout"):
        build_session_budget_profile(max_ops=1, action="timeout")
    with pytest.raises(ValueError, match=r"(?i)only applies to action=timeout"):
        build_session_budget_profile(max_ops=1, action="drop", budget_timeout="5ms")


def test_parse_rate_rejects_numeric_types():
    with pytest.raises(TypeError, match=r"must be a string"):
        parse_rate(10)
    with pytest.raises(TypeError, match=r"must be a string"):
        parse_rate(10.5)


def test_parse_rate_accepts_string_with_suffix():
    assert parse_rate("10mbps") == 10_000_000
    assert parse_rate("1gbps") == 1_000_000_000
    assert parse_rate("500kbps") == 500_000


def test_parse_duration_parses_ms():
    assert parse_duration("200ms") == 200
    assert parse_duration("0ms") == 0


def test_parse_duration_parses_seconds():
    assert parse_duration("1s") == 1000
    assert parse_duration("0.5s") == 500
    assert parse_duration("5s") == 5000


def test_parse_duration_rejects_invalid_format():
    with pytest.raises(ValueError, match=r"duration must be"):
        parse_duration("200")
    with pytest.raises(ValueError, match=r"duration must be"):
        parse_duration("invalid")


def test_parse_size_parses_kb_mb_gb():
    assert parse_size("1kb") == 1_000
    assert parse_size("5mb") == 5_000_000
    assert parse_size("1gb") == 1_000_000_000


def test_parse_size_parses_rate_suffixes():
    assert parse_size("100mbps") == 100_000_000
    assert parse_size("1gbps") == 1_000_000_000


def test_parse_size_rejects_invalid_format():
    with pytest.raises(ValueError, match=r"size must be"):
        parse_size("100")
    with pytest.raises(ValueError, match=r"size value"):
        parse_size("invalidkb")


def test_build_timeout_profile_parses_connect_and_recv():
    profile = build_timeout_profile(connect="500ms", recv="1s")
    assert profile == {"connect_ms": 500, "recv_ms": 1000}


def test_build_timeout_profile_accepts_partial():
    profile = build_timeout_profile(connect="200ms")
    assert profile == {"connect_ms": 200}
    profile = build_timeout_profile(recv="300ms")
    assert profile == {"recv_ms": 300}


def test_build_timeout_profile_accepts_empty():
    profile = build_timeout_profile()
    assert profile == {}


def test_build_payload_mutation_profile_parses_expected_shape():
    profile = build_payload_mutation_profile(
        enabled=True,
        type="inject_bytes",
        target="uplink_only",
        prob="50%",
        inject_position=2,
        inject_data=b"xyz",
    )
    assert profile["enabled"] == 1
    assert profile["type"] == 3
    assert profile["target"] == 1
    assert profile["prob_ppm"] == 500_000
    assert profile["inject_len"] == 3
