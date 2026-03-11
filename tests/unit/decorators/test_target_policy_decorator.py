import json
import threading
from unittest.mock import MagicMock, patch

import pytest

import faultcore
from faultcore.decorator import clear_policies, get_thread_policy


class TestTargetDecorators:
    def test_for_target_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=977):

                @faultcore.for_target("tcp://10.1.2.3:443")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_target.assert_called_once_with(
                    977,
                    enabled=True,
                    kind=1,
                    ipv4=167838211,
                    prefix_len=32,
                    port=443,
                    protocol=1,
                    address_family=1,
                    addr=[10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(977)

    def test_for_target_ipv6_is_accepted(self):
        mock_shm = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=978):

                @faultcore.for_target("tcp://[::1]:443")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_target.assert_called_once_with(
                    978,
                    enabled=True,
                    kind=1,
                    ipv4=0,
                    prefix_len=128,
                    port=443,
                    protocol=1,
                    address_family=2,
                    addr=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
                )
                mock_shm.clear.assert_called_once_with(978)

    def test_for_target_accepts_explicit_any_protocol(self):
        mock_shm = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=979):

                @faultcore.for_target("10.1.2.3:443", protocol="any")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_target.assert_called_once_with(
                    979,
                    enabled=True,
                    kind=1,
                    ipv4=167838211,
                    prefix_len=32,
                    port=443,
                    protocol=0,
                    address_family=1,
                    addr=[10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(979)

    def test_for_target_accepts_port_range(self):
        mock_shm = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=980):

                @faultcore.for_target(host="10.1.2.3", port_start=8000, port_end=9000)
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_target.assert_called_once_with(
                    980,
                    enabled=True,
                    kind=1,
                    ipv4=167838211,
                    prefix_len=32,
                    port=0,
                    port_start=8000,
                    port_end=9000,
                    protocol=0,
                    address_family=1,
                    addr=[10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(980)

    def test_for_target_accepts_hostname_filter(self):
        mock_shm = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=981):

                @faultcore.for_target(hostname="T\u00e4st.FOO.com")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_target.assert_called_once_with(
                    981,
                    enabled=True,
                    kind=0,
                    ipv4=0,
                    prefix_len=0,
                    port=0,
                    protocol=0,
                    address_family=0,
                    addr=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    hostname="xn--tst-qla.foo.com",
                )
                mock_shm.clear.assert_called_once_with(981)


class TestTemporalProfiles:
    def test_profile_spike_writes_schedule_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_schedule = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=976):
                with patch("faultcore.decorator.time.monotonic_ns", return_value=555):

                    @faultcore.profile(
                        "spike",
                        every_s=30,
                        duration_s=5,
                        latency_ms=100,
                    )
                    def op():
                        return "ok"

                    assert op() == "ok"
                    mock_shm.write_latency.assert_called_once_with(976, 100)
                    mock_shm.write_schedule.assert_called_once_with(
                        976,
                        schedule_type=2,
                        param_a_ns=30_000_000_000,
                        param_b_ns=5_000_000_000,
                        param_c_ns=0,
                        started_monotonic_ns=555,
                    )
                    mock_shm.clear.assert_called_once_with(976)

    def test_profile_rejects_invalid_schedule(self):
        with pytest.raises(ValueError):
            faultcore.profile("spike", every_s=10)
        with pytest.raises(ValueError):
            faultcore.profile("flapping", on_s=0, off_s=1)
        with pytest.raises(ValueError):
            faultcore.profile("ramp", ramp_s=0)


class TestPolicyRegistry:
    def test_apply_policy_uses_registered_policy(self):
        faultcore.register_policy(
            "slow_link",
            latency_ms=50,
            jitter_ms=10,
            packet_loss="1%",
            burst_loss_len=3,
            rate="2mbps",
            connect_timeout_ms=20,
            recv_timeout_ms=20,
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.write_burst_loss = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=5150):

                @faultcore.apply_policy("slow_link")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(5150, 50)
                mock_shm.write_jitter.assert_called_once_with(5150, 10)
                mock_shm.write_packet_loss.assert_called_once_with(5150, 10_000)
                mock_shm.write_burst_loss.assert_called_once_with(5150, 3)
                mock_shm.write_bandwidth.assert_called_once_with(5150, 2_000_000)
                mock_shm.write_timeouts.assert_called_once_with(5150, 20, 20)
                mock_shm.clear.assert_called_once_with(5150)

    def test_fault_auto_reads_thread_policy(self):
        faultcore.register_policy("auto_policy", packet_loss="0.1%")
        faultcore.set_thread_policy("auto_policy")

        mock_shm = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=5151):

                @faultcore.fault()
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_loss.assert_called_once_with(5151, 1_000)
                mock_shm.clear.assert_called_once_with(5151)

        faultcore.set_thread_policy(None)

    def test_fault_context_sets_and_restores_thread_policy(self):
        faultcore.set_thread_policy("outer")
        with faultcore.fault_context("inner"):
            assert get_thread_policy() == "inner"
        assert get_thread_policy() == "outer"
        faultcore.set_thread_policy(None)

    def test_register_policy_with_split_timeouts(self):
        faultcore.register_policy("split_timeouts", connect_timeout_ms=321, recv_timeout_ms=654)

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=612):

                @faultcore.apply_policy("split_timeouts")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_timeouts.assert_called_once_with(612, 321, 654)
                mock_shm.clear.assert_called_once_with(612)

    def test_register_policy_with_uplink_and_downlink_profiles(self):
        faultcore.register_policy(
            "directional",
            uplink={"latency_ms": 10, "rate": "5mbps"},
            downlink={"packet_loss": "1.5%", "jitter_ms": 4},
        )

        mock_shm = MagicMock()
        mock_shm.write_uplink = MagicMock()
        mock_shm.write_downlink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=890):

                @faultcore.apply_policy("directional")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_uplink.assert_called_once_with(
                    890,
                    latency_ms=10,
                    jitter_ms=None,
                    packet_loss_ppm=None,
                    burst_loss_len=None,
                    bandwidth_bps=5_000_000,
                )
                mock_shm.write_downlink.assert_called_once_with(
                    890,
                    latency_ms=None,
                    jitter_ms=4,
                    packet_loss_ppm=15_000,
                    burst_loss_len=None,
                    bandwidth_bps=None,
                )
                mock_shm.clear.assert_called_once_with(890)

    def test_register_policy_with_correlated_loss_profile(self):
        faultcore.register_policy(
            "ge_policy",
            correlated_loss={
                "p_good_to_bad": "2%",
                "p_bad_to_good": "40%",
                "loss_good": "0.2%",
                "loss_bad": "18%",
            },
        )

        mock_shm = MagicMock()
        mock_shm.write_correlated_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=891):

                @faultcore.apply_policy("ge_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_correlated_loss.assert_called_once_with(
                    891,
                    enabled=True,
                    p_good_to_bad_ppm=20_000,
                    p_bad_to_good_ppm=400_000,
                    loss_good_ppm=2_000,
                    loss_bad_ppm=180_000,
                )
                mock_shm.clear.assert_called_once_with(891)

    def test_register_policy_with_connection_error_and_half_open(self):
        faultcore.register_policy(
            "conn_policy",
            connection_error={"kind": "reset", "prob": "5%"},
            half_open={"after_bytes": 2048, "error": "unreachable"},
        )

        mock_shm = MagicMock()
        mock_shm.write_connection_error = MagicMock()
        mock_shm.write_half_open = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=892):

                @faultcore.apply_policy("conn_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_connection_error.assert_called_once_with(
                    892,
                    kind=1,
                    prob_ppm=50_000,
                )
                mock_shm.write_half_open.assert_called_once_with(
                    892,
                    after_bytes=2048,
                    err_kind=3,
                )
                mock_shm.clear.assert_called_once_with(892)

    def test_register_policy_with_packet_duplicate_and_reorder(self):
        faultcore.register_policy(
            "dup_reorder_policy",
            packet_duplicate={"prob": "3%", "max_extra": 2},
            packet_reorder={"prob": "1%", "max_delay_ms": 50, "window": 3},
        )

        mock_shm = MagicMock()
        mock_shm.write_packet_duplicate = MagicMock()
        mock_shm.write_packet_reorder = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=893):

                @faultcore.apply_policy("dup_reorder_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_duplicate.assert_called_once_with(
                    893,
                    prob_ppm=30_000,
                    max_extra=2,
                )
                mock_shm.write_packet_reorder.assert_called_once_with(
                    893,
                    prob_ppm=10_000,
                    max_delay_ns=50_000_000,
                    window=3,
                )
                mock_shm.clear.assert_called_once_with(893)

    def test_register_policy_with_dns_fields(self):
        faultcore.register_policy(
            "dns_policy",
            dns_delay_ms=150,
            dns_timeout_ms=900,
            dns_nxdomain="7%",
        )

        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=894):

                @faultcore.apply_policy("dns_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_dns.assert_called_once_with(
                    894,
                    delay_ms=150,
                    timeout_ms=900,
                    nxdomain_ppm=70_000,
                )
                mock_shm.clear.assert_called_once_with(894)

    def test_register_policy_with_target_filter(self):
        faultcore.register_policy(
            "target_policy",
            latency_ms=10,
            target={"target": "udp://10.0.0.0/8", "port": 53},
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=895):

                @faultcore.apply_policy("target_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(895, 10)
                mock_shm.write_target.assert_called_once_with(
                    895,
                    enabled=True,
                    kind=2,
                    ipv4=167772160,
                    prefix_len=8,
                    port=53,
                    protocol=2,
                    address_family=1,
                    addr=[10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(895)

    def test_register_policy_target_filter_accepts_explicit_any_protocol(self):
        faultcore.register_policy(
            "target_policy_any",
            latency_ms=10,
            target={"target": "10.0.0.0/8", "port": 53, "protocol": "any"},
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=989):

                @faultcore.apply_policy("target_policy_any")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(989, 10)
                mock_shm.write_target.assert_called_once_with(
                    989,
                    enabled=True,
                    kind=2,
                    ipv4=167772160,
                    prefix_len=8,
                    port=53,
                    protocol=0,
                    address_family=1,
                    addr=[10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(989)

    def test_register_policy_target_filter_accepts_port_range(self):
        faultcore.register_policy(
            "target_policy_range",
            latency_ms=10,
            target={"host": "10.1.2.3", "port_start": 8000, "port_end": 9000},
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=990):

                @faultcore.apply_policy("target_policy_range")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(990, 10)
                mock_shm.write_target.assert_called_once_with(
                    990,
                    enabled=True,
                    kind=1,
                    ipv4=167838211,
                    prefix_len=32,
                    port=0,
                    port_start=8000,
                    port_end=9000,
                    protocol=0,
                    address_family=1,
                    addr=[10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                )
                mock_shm.clear.assert_called_once_with(990)

    def test_register_policy_target_filter_accepts_hostname(self):
        faultcore.register_policy(
            "target_policy_hostname",
            latency_ms=10,
            target={"hostname": "*.Foo.com"},
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_target = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=991):

                @faultcore.apply_policy("target_policy_hostname")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(991, 10)
                mock_shm.write_target.assert_called_once_with(
                    991,
                    enabled=True,
                    kind=0,
                    ipv4=0,
                    prefix_len=0,
                    port=0,
                    protocol=0,
                    address_family=0,
                    addr=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    hostname="*.foo.com",
                )
                mock_shm.clear.assert_called_once_with(991)

    def test_register_policy_with_multiple_targets(self):
        faultcore.register_policy(
            "multi_target_policy",
            latency_ms=10,
            targets=[
                {"target": "udp://10.0.0.0/8", "port": 53, "priority": 10},
                {"target": "tcp://10.1.2.3:443", "priority": 200},
            ],
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_targets = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=905):

                @faultcore.apply_policy("multi_target_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(905, 10)
                mock_shm.write_targets.assert_called_once_with(
                    905,
                    [
                        {
                            "enabled": 1,
                            "kind": 1,
                            "ipv4": 167838211,
                            "prefix_len": 32,
                            "port": 443,
                            "protocol": 1,
                            "priority": 200,
                            "address_family": 1,
                            "addr": [10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                        {
                            "enabled": 1,
                            "kind": 2,
                            "ipv4": 167772160,
                            "prefix_len": 8,
                            "port": 53,
                            "protocol": 2,
                            "priority": 10,
                            "address_family": 1,
                            "addr": [10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                    ],
                )
                mock_shm.clear.assert_called_once_with(905)

    def test_register_policy_with_multiple_targets_keeps_stable_order_on_priority_tie(self):
        faultcore.register_policy(
            "multi_target_tie_policy",
            latency_ms=10,
            targets=[
                {"target": "tcp://10.1.2.3:443", "priority": 100},
                {"target": "tcp://10.1.2.4:443", "priority": 100},
            ],
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_targets = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=906):

                @faultcore.apply_policy("multi_target_tie_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(906, 10)
                mock_shm.write_targets.assert_called_once_with(
                    906,
                    [
                        {
                            "enabled": 1,
                            "kind": 1,
                            "ipv4": 167838211,
                            "prefix_len": 32,
                            "port": 443,
                            "protocol": 1,
                            "priority": 100,
                            "address_family": 1,
                            "addr": [10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                        {
                            "enabled": 1,
                            "kind": 1,
                            "ipv4": 167838212,
                            "prefix_len": 32,
                            "port": 443,
                            "protocol": 1,
                            "priority": 100,
                            "address_family": 1,
                            "addr": [10, 1, 2, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                    ],
                )
                mock_shm.clear.assert_called_once_with(906)

    def test_register_policy_with_multiple_targets_mixed_entries_and_default_priority(self):
        faultcore.register_policy(
            "multi_target_mixed_policy",
            latency_ms=10,
            targets=[
                "10.0.0.0/8",
                {"target": "tcp://10.1.2.3:443", "priority": 200},
            ],
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_targets = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=907):

                @faultcore.apply_policy("multi_target_mixed_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(907, 10)
                mock_shm.write_targets.assert_called_once_with(
                    907,
                    [
                        {
                            "enabled": 1,
                            "kind": 1,
                            "ipv4": 167838211,
                            "prefix_len": 32,
                            "port": 443,
                            "protocol": 1,
                            "priority": 200,
                            "address_family": 1,
                            "addr": [10, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                        {
                            "enabled": 1,
                            "kind": 2,
                            "ipv4": 167772160,
                            "prefix_len": 8,
                            "port": 0,
                            "protocol": 0,
                            "priority": 100,
                            "address_family": 1,
                            "addr": [10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        },
                    ],
                )
                mock_shm.clear.assert_called_once_with(907)

    def test_register_policy_with_schedule(self):
        faultcore.register_policy(
            "scheduled",
            packet_loss="2%",
            schedule={"kind": "flapping", "on_s": 2, "off_s": 3},
        )

        mock_shm = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.write_schedule = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=896):
                with patch("faultcore.decorator.time.monotonic_ns", return_value=777):

                    @faultcore.apply_policy("scheduled")
                    def op():
                        return "ok"

                    assert op() == "ok"
                    mock_shm.write_packet_loss.assert_called_once_with(896, 20_000)
                    mock_shm.write_schedule.assert_called_once_with(
                        896,
                        schedule_type=3,
                        param_a_ns=2_000_000_000,
                        param_b_ns=3_000_000_000,
                        param_c_ns=0,
                        started_monotonic_ns=777,
                    )
                    mock_shm.clear.assert_called_once_with(896)

    def test_register_policy_with_session_budget(self):
        faultcore.register_policy(
            "session_budgeted",
            session_budget={
                "max_bytes_tx": 1024,
                "max_ops": 2,
                "action": "timeout",
                "budget_timeout_ms": 15,
            },
        )

        mock_shm = MagicMock()
        mock_shm.write_session_budget = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=926):

                @faultcore.apply_policy("session_budgeted")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_session_budget.assert_called_once_with(
                    926,
                    max_bytes_tx=1024,
                    max_bytes_rx=None,
                    max_ops=2,
                    max_duration_ms=None,
                    action=2,
                    budget_timeout_ms=15,
                    error_kind=None,
                )
                mock_shm.clear.assert_called_once_with(926)

    def test_register_policy_rejects_invalid_values(self):
        with pytest.raises(ValueError):
            faultcore.register_policy("", latency_ms=1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad1", latency_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad2", jitter_ms=-1)
        with pytest.raises(TypeError):
            faultcore.register_policy("bad3", timeout_ms=-1)  # type: ignore[call-arg]
        with pytest.raises(ValueError):
            faultcore.register_policy("bad4", connect_timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad5", recv_timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad6", rate=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad7", uplink="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad8", downlink="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad9", correlated_loss="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad10", connection_error="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad11", half_open="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad12", packet_duplicate="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad13", packet_reorder="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad14", dns_delay_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad15", dns_timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad16", target=123)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad17", target="tcp://bad_host:80")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad18", schedule="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad19", target="tcp://10.1.2.3:443", targets=["10.0.0.1:80"])
        with pytest.raises(ValueError):
            faultcore.register_policy("bad20", targets="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad21", session_budget="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad22", session_budget={"action": "drop"})

    def test_registry_introspection_and_unregister(self):
        clear_policies()
        faultcore.register_policy("b_policy", latency_ms=2)
        faultcore.register_policy("a_policy", latency_ms=1)

        assert faultcore.list_policies() == ["a_policy", "b_policy"]
        assert faultcore.get_policy("a_policy") == {"latency_ms": 1}
        assert faultcore.get_policy("missing") is None

        assert faultcore.unregister_policy("a_policy") is True
        assert faultcore.unregister_policy("a_policy") is False
        assert faultcore.list_policies() == ["b_policy"]

    def test_get_policy_returns_deep_copy_for_nested_profiles(self):
        clear_policies()
        faultcore.register_policy(
            "deep_copy_policy",
            uplink={"latency_ms": 7},
            targets=[{"target": "tcp://10.1.2.3:443", "priority": 100}],
        )

        policy = faultcore.get_policy("deep_copy_policy")
        assert policy is not None
        policy["uplink_profile"]["latency_ms"] = 999
        policy["target_profiles"][0]["port"] = 1

        fresh = faultcore.get_policy("deep_copy_policy")
        assert fresh is not None
        assert fresh["uplink_profile"]["latency_ms"] == 7
        assert fresh["target_profiles"][0]["port"] == 443

    def test_registry_thread_safety_under_parallel_updates(self):
        clear_policies()

        def worker(idx: int) -> None:
            name = f"p{idx}"
            faultcore.register_policy(name, latency_ms=idx)
            assert faultcore.get_policy(name) is not None
            assert faultcore.unregister_policy(name) is True

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert faultcore.list_policies() == []

    def test_load_policies_from_json(self, tmp_path):
        file_path = tmp_path / "policies.json"
        file_path.write_text(
            json.dumps(
                {
                    "from_file": {
                        "latency_ms": 7,
                        "jitter_ms": 3,
                        "packet_loss": "0.2%",
                        "burst_loss_len": 2,
                        "rate": "1mbps",
                        "connect_timeout_ms": 9,
                        "recv_timeout_ms": 9,
                    }
                }
            )
        )

        loaded = faultcore.load_policies(file_path)
        assert loaded == 1

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.write_burst_loss = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=611):

                @faultcore.apply_policy("from_file")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(611, 7)
                mock_shm.write_jitter.assert_called_once_with(611, 3)
                mock_shm.write_packet_loss.assert_called_once_with(611, 2_000)
                mock_shm.write_burst_loss.assert_called_once_with(611, 2)
                mock_shm.write_bandwidth.assert_called_once_with(611, 1_000_000)
                mock_shm.write_timeouts.assert_called_once_with(611, 9, 9)
