import os
import struct
import uuid
from collections import Counter
from contextlib import suppress

import pytest

from faultcore.shm_writer import (
    FAULTCORE_MAGIC,
    MAX_TIDS,
    SHM_SIZE,
    SHMWriter,
)


def create_test_shm(name: str) -> int:
    fd = os.open(f"/dev/shm/{name}", os.O_CREAT | os.O_RDWR, mode=0o666)
    os.ftruncate(fd, SHM_SIZE)
    return fd


def cleanup_test_shm(name: str) -> None:
    with suppress(FileNotFoundError):
        os.unlink(f"/dev/shm/{name}")


class TestTIDHashCollisions:
    def test_tid_hash_distribution(self):
        writer = SHMWriter()

        tid_slots = [writer._tid_slot(tid) for tid in range(100000)]

        slot_counts = Counter(tid_slots)

        expected_avg = 100000 / MAX_TIDS
        max_count = max(slot_counts.values())
        min_count = min(slot_counts.values())

        max_ratio = max_count / expected_avg
        min_ratio = min_count / expected_avg

        assert max_ratio < 5.0, f"TID hash has poor distribution: max ratio {max_ratio:.2f}"
        assert min_ratio > 0.2, f"TID hash has poor distribution: min ratio {min_ratio:.2f}"

    def test_tid_hash_is_deterministic(self):
        writer = SHMWriter()

        test_tids = [1, 100, 1000, 10000, 100000, 1000000]

        for tid in test_tids:
            slot1 = writer._tid_slot(tid)
            slot2 = writer._tid_slot(tid)
            assert slot1 == slot2, f"TID {tid} maps to different slots: {slot1} vs {slot2}"

    def test_tid_hash_bounds(self):
        writer = SHMWriter()

        for tid in range(0, 100000, 100):
            slot = writer._tid_slot(tid)
            assert 0 <= slot < MAX_TIDS, f"TID {tid} maps to invalid slot: {slot}"

    def test_tid_hash_known_values(self):
        writer = SHMWriter()

        assert writer._tid_slot(0) == writer._tid_slot(0)

        tid1 = writer._tid_slot(12345)
        tid2 = writer._tid_slot(12346)

        assert isinstance(tid1, int)
        assert isinstance(tid2, int)


class TestSHMWriterGracefulDegradation:
    def test_no_shm_returns_empty(self):
        writer = SHMWriter("nonexistent_shm_12345")
        assert writer._mmap is None
        assert writer._fd is None

    def test_write_latency_no_shm_no_error(self, monkeypatch):
        monkeypatch.setenv("FAULTCORE_CONFIG_SHM", "nonexistent_shm_12345")
        writer = SHMWriter()
        writer.write_latency(1234, 100)
        assert writer._mmap is None

    def test_write_policy_name_no_shm_no_error(self, monkeypatch):
        monkeypatch.setenv("FAULTCORE_CONFIG_SHM", "nonexistent_shm_12345")
        writer = SHMWriter()
        writer.write_policy_name("policy-a")
        assert writer._mmap is None

    def test_write_targets_attempts_reopen_when_shm_appears_later(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        writer = SHMWriter(name)
        assert writer._mmap is None

        fd = create_test_shm(name)
        os.close(fd)
        try:
            writer.write_targets(
                4242,
                [
                    {
                        "enabled": 1,
                        "kind": 1,
                        "ipv4": 0x7F000001,
                        "prefix_len": 32,
                        "port": 80,
                        "protocol": 1,
                    }
                ],
            )
            assert writer._mmap is not None
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_clear_resets_previous_fields_before_next_write(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242
        packet_loss_offset = 28

        try:
            writer.write_packet_loss(tid, 123_456)
            writer.clear(tid)
            writer.write_latency(tid, 5)

            offset = writer._get_offset(tid)
            magic = struct.unpack_from("<I", writer._mmap, offset)[0]
            packet_loss_ppm = struct.unpack_from("<Q", writer._mmap, offset + packet_loss_offset)[0]

            assert magic == FAULTCORE_MAGIC
            assert packet_loss_ppm == 0
        finally:
            writer.close()
            cleanup_test_shm(name)


class TestDecoratorIntegration:
    def test_timeout_decorator_no_shm_no_error(self):
        from faultcore import timeout

        @timeout(connect="100ms")
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"

    def test_rate_limit_decorator_no_shm_no_error(self):
        from faultcore import rate

        @rate("1mbps")
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"


class TestSessionBudgetSerialization:
    def test_write_session_budget_serializes_all_fields(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242

        try:
            writer.write_session_budget(
                tid,
                max_bytes_tx=1024,
                max_bytes_rx=2048,
                max_ops=12,
                max_duration_ms=5000,
                action=2,
                budget_timeout_ms=150,
                error_kind=None,
            )

            offset = writer._get_offset(tid)
            assert struct.unpack_from("<Q", writer._mmap, offset + 472)[0] == 1
            assert struct.unpack_from("<Q", writer._mmap, offset + 480)[0] == 1024
            assert struct.unpack_from("<Q", writer._mmap, offset + 488)[0] == 2048
            assert struct.unpack_from("<Q", writer._mmap, offset + 496)[0] == 12
            assert struct.unpack_from("<Q", writer._mmap, offset + 504)[0] == 5000
            assert struct.unpack_from("<Q", writer._mmap, offset + 512)[0] == 2
            assert struct.unpack_from("<Q", writer._mmap, offset + 520)[0] == 150
            assert struct.unpack_from("<Q", writer._mmap, offset + 528)[0] == 0
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_policy_seed_serializes_field(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242

        try:
            writer.write_policy_seed(tid, 987654321)
            offset = writer._get_offset(tid)
            assert struct.unpack_from("<Q", writer._mmap, offset + 536)[0] == 987654321
        finally:
            writer.close()
            cleanup_test_shm(name)


class TestTargetRulesValidation:
    @pytest.mark.parametrize(
        ("rule", "expected"),
        [
            (
                {"enabled": 2, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 32, "port": 80, "protocol": 1},
                "enabled",
            ),
            (
                {
                    "enabled": 1,
                    "priority": -1,
                    "kind": 1,
                    "ipv4": 0x7F000001,
                    "prefix_len": 32,
                    "port": 80,
                    "protocol": 1,
                },
                "priority",
            ),
            ({"enabled": 1, "kind": 3, "ipv4": 0x7F000001, "prefix_len": 32, "port": 80, "protocol": 1}, "kind"),
            (
                {"enabled": 1, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 33, "port": 80, "protocol": 1},
                "prefix_len",
            ),
            (
                {"enabled": 1, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 32, "port": 70000, "protocol": 1},
                "port",
            ),
            (
                {"enabled": 1, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 32, "port": 80, "protocol": 9},
                "protocol",
            ),
            (
                {"enabled": 1, "kind": 1, "ipv4": 0x1_0000_0000, "prefix_len": 32, "port": 80, "protocol": 1},
                "ipv4",
            ),
            (
                {
                    "enabled": 1,
                    "kind": 1,
                    "ipv4": 0x7F000001,
                    "prefix_len": 32,
                    "port": 80,
                    "port_start": 70,
                    "port_end": 90,
                    "protocol": 1,
                },
                "both port and port_start/port_end",
            ),
            (
                {
                    "enabled": 1,
                    "kind": 1,
                    "ipv4": 0x7F000001,
                    "prefix_len": 32,
                    "port_start": 90,
                    "protocol": 1,
                },
                "requires both port_start and port_end",
            ),
            (
                {
                    "enabled": 1,
                    "kind": 0,
                    "hostname": "api.foo.com",
                    "sni": "api.foo.com",
                    "protocol": 0,
                },
                "both hostname and sni",
            ),
        ],
    )
    def test_write_targets_rejects_invalid_rule_fields(self, rule, expected):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)

        try:
            with pytest.raises(ValueError, match=expected):
                writer.write_targets(4242, [rule])
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_accepts_valid_single_rule(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242

        try:
            rule = {"enabled": 1, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 32, "port": 9000, "protocol": 1}
            writer.write_targets(tid, [rule])

            cfg_offset = writer._get_offset(tid)
            target_addr_family = struct.unpack_from("<Q", writer._mmap, cfg_offset + 384)[0]
            target_addr = bytes(writer._mmap[cfg_offset + 392 : cfg_offset + 408])
            assert target_addr_family == 1
            assert target_addr[:4] == bytes([127, 0, 0, 1])
            assert target_addr[4:] == b"\x00" * 12
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_serializes_address_family_and_addr(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242
        addr = [0x20, 0x01, 0x0D, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10]

        try:
            rule = {
                "enabled": 1,
                "kind": 1,
                "ipv4": 0,
                "prefix_len": 128,
                "port": 443,
                "protocol": 1,
                "address_family": 2,
                "addr": addr,
            }
            writer.write_targets(tid, [rule])

            cfg_offset = writer._get_offset(tid)
            target_addr_family = struct.unpack_from("<Q", writer._mmap, cfg_offset + 384)[0]
            target_addr = bytes(writer._mmap[cfg_offset + 392 : cfg_offset + 408])
            assert target_addr_family == 2
            assert target_addr == bytes(addr)

            rules_offset = writer._target_rules_offset(tid)
            rule_addr_family = struct.unpack_from("<Q", writer._mmap, rules_offset + 64)[0]
            rule_addr = bytes(writer._mmap[rules_offset + 72 : rules_offset + 88])
            assert rule_addr_family == 2
            assert rule_addr == bytes(addr)
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_serializes_port_range(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242

        try:
            rule = {
                "enabled": 1,
                "kind": 1,
                "ipv4": 0x7F000001,
                "prefix_len": 32,
                "port_start": 8000,
                "port_end": 9000,
                "protocol": 1,
            }
            writer.write_targets(tid, [rule])

            rules_offset = writer._target_rules_offset(tid)
            rule_port_start = struct.unpack_from("<Q", writer._mmap, rules_offset + 40)[0]
            rule_port_end = struct.unpack_from("<Q", writer._mmap, rules_offset + 56)[0]
            assert rule_port_start == 8000
            assert rule_port_end == 9000
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_serializes_hostname_and_sni_buffers(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)
        tid = 4242

        try:
            rule = {
                "enabled": 1,
                "kind": 0,
                "hostname": "*.foo.com",
                "protocol": 0,
            }
            writer.write_targets(tid, [rule])

            cfg_offset = writer._get_offset(tid)
            hostname = bytes(writer._mmap[cfg_offset + 408 : cfg_offset + 440]).rstrip(b"\x00")
            sni = bytes(writer._mmap[cfg_offset + 440 : cfg_offset + 472]).rstrip(b"\x00")
            assert hostname == b"*.foo.com"
            assert sni == b""

            rules_offset = writer._target_rules_offset(tid)
            row_hostname = bytes(writer._mmap[rules_offset + 88 : rules_offset + 120]).rstrip(b"\x00")
            row_sni = bytes(writer._mmap[rules_offset + 120 : rules_offset + 152]).rstrip(b"\x00")
            assert row_hostname == b"*.foo.com"
            assert row_sni == b""
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_rejects_non_mapping_rule(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)

        try:
            with pytest.raises(ValueError, match="must be a mapping"):
                writer.write_targets(4242, [123])  # type: ignore[list-item]
        finally:
            writer.close()
            cleanup_test_shm(name)

    def test_write_targets_rejects_non_integer_fields(self):
        name = f"faultcore_test_{uuid.uuid4().hex}"
        fd = create_test_shm(name)
        os.close(fd)
        writer = SHMWriter(name)

        try:
            bad_rule = {
                "enabled": 1,
                "kind": "tcp",
                "ipv4": 0x7F000001,
                "prefix_len": 32,
                "port": 9000,
                "protocol": 1,
            }
            with pytest.raises(ValueError, match="kind must be an integer"):
                writer.write_targets(4242, [bad_rule])  # type: ignore[list-item]
        finally:
            writer.close()
            cleanup_test_shm(name)


class TestExports:
    def test_timeout_is_exported(self):
        from faultcore import timeout

        assert callable(timeout)

    def test_jitter_is_exported(self):
        from faultcore import jitter

        assert callable(jitter)

    def test_rate_is_exported(self):
        from faultcore import rate

        assert callable(rate)

    def test_packet_loss_is_exported(self):
        from faultcore import packet_loss

        assert callable(packet_loss)

    def test_burst_loss_is_exported(self):
        from faultcore import burst_loss

        assert callable(burst_loss)

    def test_uplink_is_exported(self):
        from faultcore import uplink

        assert callable(uplink)

    def test_downlink_is_exported(self):
        from faultcore import downlink

        assert callable(downlink)

    def test_correlated_loss_is_exported(self):
        from faultcore import correlated_loss

        assert callable(correlated_loss)

    def test_connection_error_is_exported(self):
        from faultcore import connection_error

        assert callable(connection_error)

    def test_half_open_is_exported(self):
        from faultcore import half_open

        assert callable(half_open)

    def test_packet_duplicate_is_exported(self):
        from faultcore import packet_duplicate

        assert callable(packet_duplicate)

    def test_packet_reorder_is_exported(self):
        from faultcore import packet_reorder

        assert callable(packet_reorder)

    def test_dns_is_exported(self):
        from faultcore import dns

        assert callable(dns)

    def test_session_budget_is_exported(self):
        from faultcore import session_budget

        assert callable(session_budget)

    def test_register_policy_is_exported(self):
        from faultcore import register_policy

        assert callable(register_policy)

    def test_list_policies_is_exported(self):
        from faultcore import list_policies

        assert callable(list_policies)

    def test_get_policy_is_exported(self):
        from faultcore import get_policy

        assert callable(get_policy)

    def test_unregister_policy_is_exported(self):
        from faultcore import unregister_policy

        assert callable(unregister_policy)

    def test_load_policies_is_exported(self):
        from faultcore import load_policies

        assert callable(load_policies)

    def test_fault_is_exported(self):
        from faultcore import fault

        assert callable(fault)

    def test_policy_context_is_exported(self):
        from faultcore import policy_context

        assert policy_context is not None
