from unittest.mock import MagicMock, patch

import pytest

import faultcore
from faultcore.decorator import (
    clear_policies,
    get_policy,
    list_policies,
    register_policy,
    set_thread_policy,
    unregister_policy,
)


@pytest.fixture(autouse=True)
def cleanup():
    clear_policies()
    set_thread_policy(None)
    yield
    clear_policies()
    set_thread_policy(None)


class TestPolicyRegistry:
    def test_fault_auto_reads_thread_policy(self):
        register_policy("test_policy", latency="100ms")
        set_thread_policy("test_policy")

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with (
            patch("faultcore.decorator.get_shm_writer", return_value=mock_shm),
            patch("faultcore.decorator.threading.get_native_id", return_value=123),
        ):

            @faultcore.fault()
            def op():
                return "ok"

            result = op()
            assert result == "ok"

        mock_shm.write_latency.assert_called_once_with(123, 100)
        mock_shm.clear.assert_called_once_with(123)

    def test_fault_auto_resolves_policy_at_call_time(self):
        register_policy("policy_a", latency="50ms")
        register_policy("policy_b", latency="100ms")
        set_thread_policy("policy_a")

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with (
            patch("faultcore.decorator.get_shm_writer", return_value=mock_shm),
            patch("faultcore.decorator.threading.get_native_id", return_value=456),
        ):

            @faultcore.fault()
            def op():
                return "ok"

            set_thread_policy("policy_b")
            result = op()
            assert result == "ok"

        mock_shm.write_latency.assert_called_once_with(456, 100)

    def test_register_policy_with_timeout_dict(self):
        register_policy("timeout_policy", timeout={"connect": "1s", "recv": "500ms"})
        policy = get_policy("timeout_policy")
        assert policy is not None
        assert "timeouts" in policy

    def test_register_policy_with_uplink_and_downlink_profiles(self):
        register_policy(
            "network_policy",
            uplink={"latency": "50ms", "rate": "10mbps"},
            downlink={"latency": "100ms", "rate": "5mbps"},
        )
        policy = get_policy("network_policy")
        assert policy is not None
        assert "uplink_profile" in policy
        assert "downlink_profile" in policy

    def test_register_policy_with_correlated_loss_profile(self):
        register_policy(
            "correlated_policy",
            correlated_loss={
                "p_good_to_bad": "5%",
                "p_bad_to_good": "10%",
                "loss_good": "0%",
                "loss_bad": "50%",
            },
        )
        policy = get_policy("correlated_policy")
        assert policy is not None

    def test_register_policy_with_connection_error_and_half_open(self):
        register_policy(
            "connection_policy",
            connection_error={"kind": "reset", "prob": "100%"},
            half_open={"after": "1kb", "error": "reset"},
        )
        policy = get_policy("connection_policy")
        assert policy is not None

    def test_register_policy_with_packet_duplicate_and_reorder(self):
        register_policy(
            "packet_policy",
            packet_duplicate={"prob": "10%", "max_extra": 2},
            packet_reorder={"prob": "5%", "max_delay": "100ms", "window": 3},
        )
        policy = get_policy("packet_policy")
        assert policy is not None

    def test_register_policy_with_dns_fields(self):
        register_policy(
            "dns_policy",
            dns={"delay": "200ms", "timeout": "1s", "nxdomain": "50%"},
        )
        policy = get_policy("dns_policy")
        assert policy is not None

    def test_register_policy_with_targets(self):
        register_policy(
            "target_policy",
            targets=[{"host": "10.1.2.3", "port": 443, "protocol": "tcp"}],
        )
        policy = get_policy("target_policy")
        assert policy is not None

    def test_register_policy_with_schedule(self):
        register_policy(
            "schedule_policy",
            schedule={
                "kind": "spike",
                "every": "10s",
                "duration": "2s",
            },
        )
        policy = get_policy("schedule_policy")
        assert policy is not None

    def test_register_policy_with_session_budget(self):
        register_policy(
            "budget_policy",
            session_budget={
                "max_tx": "1kb",
                "max_rx": "2kb",
                "max_ops": 100,
                "action": "drop",
            },
        )
        policy = get_policy("budget_policy")
        assert policy is not None

    def test_register_policy_rejects_invalid_values(self):
        with pytest.raises((ValueError, TypeError)):
            register_policy("invalid", latency="invalid")

    def test_registry_introspection_and_unregister(self):
        register_policy("test1", latency="10ms")
        register_policy("test2", latency="20ms")

        assert "test1" in list_policies()
        assert "test2" in list_policies()

        assert unregister_policy("test1")
        assert "test1" not in list_policies()
        assert "test2" in list_policies()

    def test_get_policy_returns_copy(self):
        register_policy("copy_test", latency="10ms")
        policy1 = get_policy("copy_test")
        policy2 = get_policy("copy_test")
        assert policy1 is not None
        assert policy2 is not None
