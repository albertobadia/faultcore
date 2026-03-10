import mmap
import os
import struct
import threading
from collections.abc import Callable, Sequence
from typing import Any

from faultcore.target_name_helpers import encode_target_name_bytes
from faultcore.target_rule_helpers import (
    normalize_target_address,
    resolve_port_range,
    validate_target_rule,
)

FAULTCORE_MAGIC = 0xFACC0DE
MAX_FDS = 131072
MAX_TIDS = 65536
MAX_POLICIES = 1024
MAX_TARGET_RULES_PER_TID = 8
CONFIG_SIZE = 472
POLICY_STATE_SIZE = 56
TARGET_RULE_SIZE = 152
SHM_SIZE = (
    ((MAX_FDS + MAX_TIDS) * CONFIG_SIZE)
    + (MAX_POLICIES * POLICY_STATE_SIZE)
    + (MAX_TIDS * MAX_TARGET_RULES_PER_TID * TARGET_RULE_SIZE)
    + (MAX_FDS * 8)
)

_CONFIG_REGION_SIZE = (MAX_FDS + MAX_TIDS) * CONFIG_SIZE
_POLICY_REGION_OFFSET = _CONFIG_REGION_SIZE
_POLICY_REGION_SIZE = MAX_POLICIES * POLICY_STATE_SIZE
_TARGET_RULES_REGION_OFFSET = _POLICY_REGION_OFFSET + _POLICY_REGION_SIZE
_TARGET_RULES_REGION_SIZE = MAX_TARGET_RULES_PER_TID * TARGET_RULE_SIZE
_NS_PER_MS = 1_000_000

U64Field = tuple[int, int]
OptionalU64Field = tuple[int, int | None]
DirectionOffsets = tuple[int, int, int, int, int]

_OFFSET_MAGIC = 0
_OFFSET_LATENCY_NS = 12
_OFFSET_JITTER_NS = 20
_OFFSET_PACKET_LOSS_PPM = 28
_OFFSET_BURST_LOSS_LEN = 36
_OFFSET_BANDWIDTH_BPS = 44
_OFFSET_CONNECT_TIMEOUT_MS = 52
_OFFSET_RECV_TIMEOUT_MS = 60
_OFFSET_UPLINK_LATENCY_NS = 68
_OFFSET_UPLINK_JITTER_NS = 76
_OFFSET_UPLINK_PACKET_LOSS_PPM = 84
_OFFSET_UPLINK_BURST_LOSS_LEN = 92
_OFFSET_UPLINK_BANDWIDTH_BPS = 100
_OFFSET_DOWNLINK_LATENCY_NS = 108
_OFFSET_DOWNLINK_JITTER_NS = 116
_OFFSET_DOWNLINK_PACKET_LOSS_PPM = 124
_OFFSET_DOWNLINK_BURST_LOSS_LEN = 132
_OFFSET_DOWNLINK_BANDWIDTH_BPS = 140
_OFFSET_GE_ENABLED = 148
_OFFSET_GE_P_GOOD_TO_BAD_PPM = 156
_OFFSET_GE_P_BAD_TO_GOOD_PPM = 164
_OFFSET_GE_LOSS_GOOD_PPM = 172
_OFFSET_GE_LOSS_BAD_PPM = 180
_OFFSET_CONN_ERR_KIND = 188
_OFFSET_CONN_ERR_PROB_PPM = 196
_OFFSET_HALF_OPEN_AFTER_BYTES = 204
_OFFSET_HALF_OPEN_ERR_KIND = 212
_OFFSET_DUP_PROB_PPM = 220
_OFFSET_DUP_MAX_EXTRA = 228
_OFFSET_REORDER_PROB_PPM = 236
_OFFSET_REORDER_MAX_DELAY_NS = 244
_OFFSET_REORDER_WINDOW = 252
_OFFSET_DNS_DELAY_NS = 260
_OFFSET_DNS_TIMEOUT_MS = 268
_OFFSET_DNS_NXDOMAIN_PPM = 276
_OFFSET_TARGET_ENABLED = 284
_OFFSET_TARGET_KIND = 292
_OFFSET_TARGET_IPV4 = 300
_OFFSET_TARGET_PREFIX_LEN = 308
_OFFSET_TARGET_PORT = 316
_OFFSET_TARGET_PROTOCOL = 324
_OFFSET_SCHEDULE_TYPE = 332
_OFFSET_SCHEDULE_PARAM_A = 340
_OFFSET_SCHEDULE_PARAM_B = 348
_OFFSET_SCHEDULE_PARAM_C = 356
_OFFSET_SCHEDULE_STARTED_MONOTONIC_NS = 364
_OFFSET_RULESET_GENERATION = 376
_OFFSET_TARGET_ADDRESS_FAMILY = 384
_OFFSET_TARGET_ADDR = 392
_OFFSET_TARGET_HOSTNAME = 408
_OFFSET_TARGET_SNI = 440

_UPLINK_DIRECTION_OFFSETS: DirectionOffsets = (
    _OFFSET_UPLINK_LATENCY_NS,
    _OFFSET_UPLINK_JITTER_NS,
    _OFFSET_UPLINK_PACKET_LOSS_PPM,
    _OFFSET_UPLINK_BURST_LOSS_LEN,
    _OFFSET_UPLINK_BANDWIDTH_BPS,
)

_DOWNLINK_DIRECTION_OFFSETS: DirectionOffsets = (
    _OFFSET_DOWNLINK_LATENCY_NS,
    _OFFSET_DOWNLINK_JITTER_NS,
    _OFFSET_DOWNLINK_PACKET_LOSS_PPM,
    _OFFSET_DOWNLINK_BURST_LOSS_LEN,
    _OFFSET_DOWNLINK_BANDWIDTH_BPS,
)


class SHMWriter:
    def __init__(self, shm_name: str | None = None):
        self._fd = None
        self._mmap = None
        self._lock = threading.Lock()

        raw_name = shm_name or os.environ.get("FAULTCORE_CONFIG_SHM", f"/faultcore_{os.getpid()}_config")
        name = raw_name.lstrip("/")

        try:
            self._fd = os.open(f"/dev/shm/{name}", os.O_RDWR)
            self._mmap = mmap.mmap(self._fd, 0, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        except OSError:
            self._fd = None
            self._mmap = None

    def _is_available(self) -> bool:
        return self._mmap is not None

    def _get_offset(self, tid: int) -> int:
        idx = MAX_FDS + self._tid_slot(tid)
        return idx * CONFIG_SIZE

    def _tid_slot(self, tid: int) -> int:
        hash_val = (tid ^ (tid >> 16)) * 0x45D9F3B ^ (tid >> 16)
        return hash_val % MAX_TIDS

    def _target_rules_offset(self, tid: int) -> int:
        return self._target_rules_offset_for_slot(self._tid_slot(tid))

    def _target_rules_offset_for_slot(self, tid_slot: int) -> int:
        return _TARGET_RULES_REGION_OFFSET + (tid_slot * _TARGET_RULES_REGION_SIZE)

    def _pack_u64_fields(self, base_offset: int, fields: tuple[U64Field, ...]) -> None:
        for relative_offset, value in fields:
            struct.pack_into("<Q", self._mmap, base_offset + relative_offset, value)

    def _write_optional_u64_fields(self, offset: int, fields: tuple[OptionalU64Field, ...]) -> None:
        for relative_offset, value in fields:
            if value is not None:
                struct.pack_into("<Q", self._mmap, offset + relative_offset, value)

    def _ms_to_ns(self, milliseconds: int) -> int:
        return milliseconds * _NS_PER_MS

    def _optional_ms_to_ns(self, milliseconds: int | None) -> int | None:
        return None if milliseconds is None else self._ms_to_ns(milliseconds)

    def _write_with_generation_publish(self, tid: int, writer: Callable[[int], None]) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            start_generation = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_RULESET_GENERATION)[0] | 1
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_RULESET_GENERATION, start_generation)
            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            writer(offset)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_RULESET_GENERATION, (start_generation + 1) & ~1)

    def _clear_target_rules_table(self, tid_slot: int) -> None:
        target_rules_offset = self._target_rules_offset_for_slot(tid_slot)
        self._mmap[target_rules_offset : target_rules_offset + _TARGET_RULES_REGION_SIZE] = (
            b"\x00" * _TARGET_RULES_REGION_SIZE
        )

    def _write_target_rule_row(self, target_rules_offset: int, idx: int, rule: dict[str, Any]) -> None:
        base = target_rules_offset + (idx * TARGET_RULE_SIZE)
        self._mmap[base : base + TARGET_RULE_SIZE] = b"\x00" * TARGET_RULE_SIZE
        address_family, addr = normalize_target_address(rule, idx)
        port_start, port_end = resolve_port_range(rule, idx)
        hostname = encode_target_name_bytes(rule.get("hostname"), f"targets[{idx}].hostname")
        sni = encode_target_name_bytes(rule.get("sni"), f"targets[{idx}].sni")
        self._pack_u64_fields(
            base,
            (
                (0, 1 if rule.get("enabled", 0) else 0),
                (8, int(rule.get("priority", 100))),
                (16, int(rule.get("kind", 0))),
                (24, int(rule.get("ipv4", 0))),
                (32, int(rule.get("prefix_len", 0))),
                (40, port_start),
                (48, int(rule.get("protocol", 0))),
                (56, port_end),
                (64, address_family),
            ),
        )
        self._mmap[base + 72 : base + 88] = addr
        self._mmap[base + 88 : base + 120] = hostname
        self._mmap[base + 120 : base + 152] = sni

    def _write_single_target_fields(self, offset: int, rule: dict[str, Any], idx: int = 0) -> None:
        address_family, addr = normalize_target_address(rule, idx)
        hostname = encode_target_name_bytes(rule.get("hostname"), f"targets[{idx}].hostname")
        sni = encode_target_name_bytes(rule.get("sni"), f"targets[{idx}].sni")
        self._pack_u64_fields(
            offset,
            (
                (_OFFSET_TARGET_KIND, int(rule.get("kind", 0))),
                (_OFFSET_TARGET_IPV4, int(rule.get("ipv4", 0))),
                (_OFFSET_TARGET_PREFIX_LEN, int(rule.get("prefix_len", 0))),
                (_OFFSET_TARGET_PORT, int(rule.get("port", 0))),
                (_OFFSET_TARGET_PROTOCOL, int(rule.get("protocol", 0))),
                (_OFFSET_TARGET_ADDRESS_FAMILY, address_family),
            ),
        )
        self._mmap[offset + _OFFSET_TARGET_ADDR : offset + _OFFSET_TARGET_ADDR + 16] = addr
        self._mmap[offset + _OFFSET_TARGET_HOSTNAME : offset + _OFFSET_TARGET_HOSTNAME + 32] = hostname
        self._mmap[offset + _OFFSET_TARGET_SNI : offset + _OFFSET_TARGET_SNI + 32] = sni

    def _clear_single_target_fields(self, offset: int) -> None:
        self._pack_u64_fields(
            offset,
            (
                (_OFFSET_TARGET_KIND, 0),
                (_OFFSET_TARGET_IPV4, 0),
                (_OFFSET_TARGET_PREFIX_LEN, 0),
                (_OFFSET_TARGET_PORT, 0),
                (_OFFSET_TARGET_PROTOCOL, 0),
                (_OFFSET_TARGET_ADDRESS_FAMILY, 0),
            ),
        )
        self._mmap[offset + _OFFSET_TARGET_ADDR : offset + _OFFSET_TARGET_ADDR + 16] = b"\x00" * 16
        self._mmap[offset + _OFFSET_TARGET_HOSTNAME : offset + _OFFSET_TARGET_HOSTNAME + 32] = b"\x00" * 32
        self._mmap[offset + _OFFSET_TARGET_SNI : offset + _OFFSET_TARGET_SNI + 32] = b"\x00" * 32

    def _write_fields(self, tid: int, fields: tuple[U64Field, ...]) -> None:
        def writer(offset: int) -> None:
            self._pack_u64_fields(offset, fields)

        self._write_with_generation_publish(tid, writer)

    def _write_direction_profile(
        self,
        offset: int,
        *,
        latency_ms: int | None,
        jitter_ms: int | None,
        packet_loss_ppm: int | None,
        burst_loss_len: int | None,
        bandwidth_bps: int | None,
        latency_offset: int,
        jitter_offset: int,
        packet_loss_offset: int,
        burst_loss_offset: int,
        bandwidth_offset: int,
    ) -> None:
        self._write_optional_u64_fields(
            offset,
            (
                (latency_offset, self._optional_ms_to_ns(latency_ms)),
                (jitter_offset, self._optional_ms_to_ns(jitter_ms)),
                (packet_loss_offset, packet_loss_ppm),
                (burst_loss_offset, burst_loss_len),
                (bandwidth_offset, bandwidth_bps),
            ),
        )

    def _write_direction_profile_for_tid(
        self,
        tid: int,
        *,
        latency_ms: int | None,
        jitter_ms: int | None,
        packet_loss_ppm: int | None,
        burst_loss_len: int | None,
        bandwidth_bps: int | None,
        offsets: DirectionOffsets,
    ) -> None:
        latency_offset, jitter_offset, packet_loss_offset, burst_loss_offset, bandwidth_offset = offsets

        def writer(offset: int) -> None:
            self._write_direction_profile(
                offset,
                latency_ms=latency_ms,
                jitter_ms=jitter_ms,
                packet_loss_ppm=packet_loss_ppm,
                burst_loss_len=burst_loss_len,
                bandwidth_bps=bandwidth_bps,
                latency_offset=latency_offset,
                jitter_offset=jitter_offset,
                packet_loss_offset=packet_loss_offset,
                burst_loss_offset=burst_loss_offset,
                bandwidth_offset=bandwidth_offset,
            )

        self._write_with_generation_publish(tid, writer)

    def write_latency(self, tid: int, latency_ms: int) -> None:
        self._write_fields(tid, ((_OFFSET_LATENCY_NS, self._ms_to_ns(latency_ms)),))

    def write_packet_loss(self, tid: int, ppm: int) -> None:
        self._write_fields(tid, ((_OFFSET_PACKET_LOSS_PPM, ppm),))

    def write_jitter(self, tid: int, jitter_ms: int) -> None:
        self._write_fields(tid, ((_OFFSET_JITTER_NS, self._ms_to_ns(jitter_ms)),))

    def write_burst_loss(self, tid: int, burst_loss_len: int) -> None:
        self._write_fields(tid, ((_OFFSET_BURST_LOSS_LEN, burst_loss_len),))

    def write_bandwidth(self, tid: int, bps: int) -> None:
        self._write_fields(tid, ((_OFFSET_BANDWIDTH_BPS, bps),))

    def write_timeouts(self, tid: int, connect_ms: int, recv_ms: int) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_CONNECT_TIMEOUT_MS, connect_ms),
                (_OFFSET_RECV_TIMEOUT_MS, recv_ms),
            ),
        )

    def write_uplink(
        self,
        tid: int,
        *,
        latency_ms: int | None = None,
        jitter_ms: int | None = None,
        packet_loss_ppm: int | None = None,
        burst_loss_len: int | None = None,
        bandwidth_bps: int | None = None,
    ) -> None:
        self._write_direction_profile_for_tid(
            tid,
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            packet_loss_ppm=packet_loss_ppm,
            burst_loss_len=burst_loss_len,
            bandwidth_bps=bandwidth_bps,
            offsets=_UPLINK_DIRECTION_OFFSETS,
        )

    def write_downlink(
        self,
        tid: int,
        *,
        latency_ms: int | None = None,
        jitter_ms: int | None = None,
        packet_loss_ppm: int | None = None,
        burst_loss_len: int | None = None,
        bandwidth_bps: int | None = None,
    ) -> None:
        self._write_direction_profile_for_tid(
            tid,
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            packet_loss_ppm=packet_loss_ppm,
            burst_loss_len=burst_loss_len,
            bandwidth_bps=bandwidth_bps,
            offsets=_DOWNLINK_DIRECTION_OFFSETS,
        )

    def write_correlated_loss(
        self,
        tid: int,
        *,
        enabled: bool,
        p_good_to_bad_ppm: int,
        p_bad_to_good_ppm: int,
        loss_good_ppm: int,
        loss_bad_ppm: int,
    ) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_GE_ENABLED, 1 if enabled else 0),
                (_OFFSET_GE_P_GOOD_TO_BAD_PPM, p_good_to_bad_ppm),
                (_OFFSET_GE_P_BAD_TO_GOOD_PPM, p_bad_to_good_ppm),
                (_OFFSET_GE_LOSS_GOOD_PPM, loss_good_ppm),
                (_OFFSET_GE_LOSS_BAD_PPM, loss_bad_ppm),
            ),
        )

    def write_connection_error(self, tid: int, *, kind: int, prob_ppm: int) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_CONN_ERR_KIND, kind),
                (_OFFSET_CONN_ERR_PROB_PPM, prob_ppm),
            ),
        )

    def write_half_open(self, tid: int, *, after_bytes: int, err_kind: int) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_HALF_OPEN_AFTER_BYTES, after_bytes),
                (_OFFSET_HALF_OPEN_ERR_KIND, err_kind),
            ),
        )

    def write_packet_duplicate(self, tid: int, *, prob_ppm: int, max_extra: int) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_DUP_PROB_PPM, prob_ppm),
                (_OFFSET_DUP_MAX_EXTRA, max_extra),
            ),
        )

    def write_packet_reorder(
        self,
        tid: int,
        *,
        prob_ppm: int,
        max_delay_ns: int = 0,
        window: int = 1,
    ) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_REORDER_PROB_PPM, prob_ppm),
                (_OFFSET_REORDER_MAX_DELAY_NS, max_delay_ns),
                (_OFFSET_REORDER_WINDOW, window),
            ),
        )

    def write_dns(
        self,
        tid: int,
        *,
        delay_ms: int | None = None,
        timeout_ms: int | None = None,
        nxdomain_ppm: int | None = None,
    ) -> None:
        def writer(offset: int) -> None:
            self._write_optional_u64_fields(
                offset,
                (
                    (_OFFSET_DNS_DELAY_NS, self._optional_ms_to_ns(delay_ms)),
                    (_OFFSET_DNS_TIMEOUT_MS, timeout_ms),
                    (_OFFSET_DNS_NXDOMAIN_PPM, nxdomain_ppm),
                ),
            )

        self._write_with_generation_publish(tid, writer)

    def write_target(
        self,
        tid: int,
        *,
        enabled: bool,
        kind: int,
        ipv4: int,
        prefix_len: int,
        port: int,
        port_start: int | None = None,
        port_end: int | None = None,
        protocol: int,
        address_family: int = 0,
        addr: bytes | bytearray | Sequence[int] | None = None,
        hostname: str | None = None,
        sni: str | None = None,
    ) -> None:
        tid_slot = self._tid_slot(tid)
        target_rules_offset = self._target_rules_offset_for_slot(tid_slot)

        def writer(offset: int) -> None:
            rule = {
                "enabled": 1 if enabled else 0,
                "priority": 100,
                "kind": kind,
                "ipv4": ipv4,
                "prefix_len": prefix_len,
                "port": port,
                "port_start": port_start,
                "port_end": port_end,
                "protocol": protocol,
                "address_family": address_family,
                "addr": addr,
                "hostname": hostname,
                "sni": sni,
            }
            validate_target_rule(rule, 0)
            normalized_family, addr_value = normalize_target_address(
                {"kind": kind, "ipv4": ipv4, "address_family": address_family, "addr": addr}, 0
            )
            port_start_value, _port_end_value = resolve_port_range(rule, 0)
            self._pack_u64_fields(
                offset,
                (
                    (_OFFSET_TARGET_ENABLED, 1 if enabled else 0),
                    (_OFFSET_TARGET_KIND, kind),
                    (_OFFSET_TARGET_IPV4, ipv4),
                    (_OFFSET_TARGET_PREFIX_LEN, prefix_len),
                    (_OFFSET_TARGET_PORT, port_start_value),
                    (_OFFSET_TARGET_PROTOCOL, protocol),
                    (_OFFSET_TARGET_ADDRESS_FAMILY, normalized_family),
                ),
            )
            self._mmap[offset + _OFFSET_TARGET_ADDR : offset + _OFFSET_TARGET_ADDR + 16] = addr_value
            self._clear_target_rules_table(tid_slot)
            if enabled:
                self._write_target_rule_row(target_rules_offset, 0, rule)

        self._write_with_generation_publish(tid, writer)

    def write_targets(self, tid: int, rules: list[dict[str, Any]]) -> None:
        if not self._is_available():
            return
        rule_count = len(rules)
        if rule_count > MAX_TARGET_RULES_PER_TID:
            raise ValueError(f"targets supports up to {MAX_TARGET_RULES_PER_TID} rules")
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(f"targets[{idx}] must be a mapping")
            validate_target_rule(rule, idx)

        tid_slot = self._tid_slot(tid)
        target_rules_offset = self._target_rules_offset_for_slot(tid_slot)

        def writer(offset: int) -> None:
            self._clear_target_rules_table(tid_slot)
            for idx, rule in enumerate(rules):
                self._write_target_rule_row(target_rules_offset, idx, rule)

            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_ENABLED, rule_count)
            if rule_count == 1:
                self._write_single_target_fields(offset, rules[0], idx=0)
            else:
                self._clear_single_target_fields(offset)

        self._write_with_generation_publish(tid, writer)

    def write_schedule(
        self,
        tid: int,
        *,
        schedule_type: int,
        param_a_ns: int = 0,
        param_b_ns: int = 0,
        param_c_ns: int = 0,
        started_monotonic_ns: int = 0,
    ) -> None:
        self._write_fields(
            tid,
            (
                (_OFFSET_SCHEDULE_TYPE, schedule_type),
                (_OFFSET_SCHEDULE_PARAM_A, param_a_ns),
                (_OFFSET_SCHEDULE_PARAM_B, param_b_ns),
                (_OFFSET_SCHEDULE_PARAM_C, param_c_ns),
                (_OFFSET_SCHEDULE_STARTED_MONOTONIC_NS, started_monotonic_ns),
            ),
        )

    def clear(self, tid: int) -> None:
        tid_slot = self._tid_slot(tid)

        def writer(offset: int) -> None:
            self._mmap[offset : offset + CONFIG_SIZE] = b"\x00" * CONFIG_SIZE
            self._clear_target_rules_table(tid_slot)

        self._write_with_generation_publish(tid, writer)

    def close(self) -> None:
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "SHMWriter":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


_shm_writer: SHMWriter | None = None
_shm_writer_lock = threading.Lock()


def get_shm_writer() -> SHMWriter:
    global _shm_writer
    if _shm_writer is None:
        with _shm_writer_lock:
            if _shm_writer is None:
                _shm_writer = SHMWriter()
    return _shm_writer
