import os
import struct
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import suppress

import pytest

import faultcore.shm_writer as shm_writer_module
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


@pytest.fixture
def shm_writer() -> Iterator[SHMWriter]:
    name = f"faultcore_test_{uuid.uuid4().hex}"
    fd = create_test_shm(name)
    os.close(fd)
    writer = SHMWriter(name)
    try:
        yield writer
    finally:
        writer.close()
        cleanup_test_shm(name)


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

    @pytest.mark.parametrize(
        ("method_name", "args"),
        [
            ("write_latency", (1234, 100)),
            ("write_policy_name", ("policy-a",)),
        ],
    )
    def test_writes_no_shm_no_error(self, monkeypatch, method_name, args):
        monkeypatch.setenv("FAULTCORE_CONFIG_SHM", "nonexistent_shm_12345")
        writer = SHMWriter()
        getattr(writer, method_name)(*args)
        assert writer._mmap is None

    def test_try_open_closes_fd_when_mmap_fails(self, monkeypatch):
        opened: list[int] = []
        closed: list[int] = []
        real_open = os.open
        real_close = os.close

        def fake_open(_path: str, _flags: int, _mode: int = 0o600) -> int:
            fd = real_open("/dev/null", os.O_RDONLY)
            opened.append(fd)
            return fd

        def fake_close(fd: int) -> None:
            closed.append(fd)
            real_close(fd)

        def fail_mmap(*_args, **_kwargs):
            raise OSError("mmap failure")

        monkeypatch.setattr(shm_writer_module.os, "open", fake_open)
        monkeypatch.setattr(shm_writer_module.os, "close", fake_close)
        monkeypatch.setattr(shm_writer_module.mmap, "mmap", fail_mmap)

        writer = SHMWriter("faultcore_test_mmap_failure")

        assert writer._mmap is None
        assert writer._fd is None
        assert opened
        assert closed == opened

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

    def test_clear_resets_previous_fields_before_next_write(self, shm_writer):
        writer = shm_writer
        tid = 4242
        packet_loss_offset = 28

        writer.write_packet_loss(tid, 123_456)
        writer.clear(tid)
        writer.write_latency(tid, 5)

        offset = writer._get_offset(tid)
        magic = struct.unpack_from("<I", writer._mmap, offset)[0]
        packet_loss_ppm = struct.unpack_from("<Q", writer._mmap, offset + packet_loss_offset)[0]

        assert magic == FAULTCORE_MAGIC
        assert packet_loss_ppm == 0


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
    def test_write_session_budget_serializes_all_fields(self, shm_writer):
        writer = shm_writer
        tid = 4242

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

    def test_write_policy_seed_serializes_field(self, shm_writer):
        writer = shm_writer
        tid = 4242

        writer.write_policy_seed(tid, 987654321)
        offset = writer._get_offset(tid)
        assert struct.unpack_from("<Q", writer._mmap, offset + 536)[0] == 987654321


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
    def test_write_targets_rejects_invalid_rule_fields(self, shm_writer, rule, expected):
        writer = shm_writer
        with pytest.raises(ValueError, match=expected):
            writer.write_targets(4242, [rule])

    def test_write_targets_accepts_valid_single_rule(self, shm_writer):
        writer = shm_writer
        tid = 4242

        rule = {"enabled": 1, "kind": 1, "ipv4": 0x7F000001, "prefix_len": 32, "port": 9000, "protocol": 1}
        writer.write_targets(tid, [rule])

        cfg_offset = writer._get_offset(tid)
        target_addr_family = struct.unpack_from("<Q", writer._mmap, cfg_offset + 384)[0]
        target_addr = bytes(writer._mmap[cfg_offset + 392 : cfg_offset + 408])
        assert target_addr_family == 1
        assert target_addr[:4] == bytes([127, 0, 0, 1])
        assert target_addr[4:] == b"\x00" * 12

    def test_write_targets_serializes_address_family_and_addr(self, shm_writer):
        writer = shm_writer
        tid = 4242
        addr = [0x20, 0x01, 0x0D, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10]

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

    def test_write_targets_serializes_port_range(self, shm_writer):
        writer = shm_writer
        tid = 4242

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

    def test_write_targets_serializes_hostname_and_sni_buffers(self, shm_writer):
        writer = shm_writer
        tid = 4242

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

    @pytest.mark.parametrize(
        ("rule", "error_match"),
        [
            (123, "must be a mapping"),
            (
                {
                    "enabled": 1,
                    "kind": "tcp",
                    "ipv4": 0x7F000001,
                    "prefix_len": 32,
                    "port": 9000,
                    "protocol": 1,
                },
                "kind must be an integer",
            ),
        ],
    )
    def test_write_targets_rejects_invalid_rule_types(self, shm_writer, rule, error_match):
        writer = shm_writer
        with pytest.raises(ValueError, match=error_match):
            writer.write_targets(4242, [rule])  # type: ignore[list-item]


class TestExports:
    @pytest.mark.parametrize(
        "symbol",
        [
            "timeout",
            "latency",
            "jitter",
            "rate",
            "packet_loss",
            "burst_loss",
            "uplink",
            "downlink",
            "correlated_loss",
            "connection_error",
            "half_open",
            "packet_duplicate",
            "packet_reorder",
            "payload_mutation",
            "dns",
            "session_budget",
            "register_policy",
            "list_policies",
            "get_policy",
            "get_thread_policy",
            "set_thread_policy",
            "unregister_policy",
            "load_policies",
            "fault",
        ],
    )
    def test_callable_symbols_are_exported(self, symbol):
        import faultcore

        assert symbol in faultcore.__all__
        assert callable(getattr(faultcore, symbol))

    def test_policy_context_is_exported(self):
        import faultcore
        from faultcore import policy_context

        assert "policy_context" in faultcore.__all__
        assert policy_context is not None
