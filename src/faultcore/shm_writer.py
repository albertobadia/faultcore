import mmap
import os
import struct
import threading
from collections.abc import Callable

FAULTCORE_MAGIC = 0xFACC0DE
MAX_FDS = 131072
MAX_TIDS = 65536
MAX_POLICIES = 1024
MAX_TARGET_RULES_PER_TID = 8
CONFIG_SIZE = 376
POLICY_STATE_SIZE = 56
TARGET_RULE_SIZE = 64
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

_OFFSET_MAGIC = 0
_OFFSET_VERSION = 4
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
        except (FileNotFoundError, PermissionError, OSError):
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

    def _write_versioned(self, tid: int, writer: Callable[[int], None]) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)
            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            writer(offset)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, (version + 2) & ~1)

    def _clear_target_rules_table(self, tid_slot: int) -> None:
        target_rules_offset = self._target_rules_offset_for_slot(tid_slot)
        self._mmap[target_rules_offset : target_rules_offset + _TARGET_RULES_REGION_SIZE] = (
            b"\x00" * _TARGET_RULES_REGION_SIZE
        )

    def _write_target_rule_row(self, target_rules_offset: int, idx: int, rule: dict[str, int]) -> None:
        base = target_rules_offset + (idx * TARGET_RULE_SIZE)
        struct.pack_into("<Q", self._mmap, base + 0, 1 if rule.get("enabled", 0) else 0)
        struct.pack_into("<Q", self._mmap, base + 8, int(rule.get("priority", 100)))
        struct.pack_into("<Q", self._mmap, base + 16, int(rule.get("kind", 0)))
        struct.pack_into("<Q", self._mmap, base + 24, int(rule.get("ipv4", 0)))
        struct.pack_into("<Q", self._mmap, base + 32, int(rule.get("prefix_len", 0)))
        struct.pack_into("<Q", self._mmap, base + 40, int(rule.get("port", 0)))
        struct.pack_into("<Q", self._mmap, base + 48, int(rule.get("protocol", 0)))
        struct.pack_into("<Q", self._mmap, base + 56, 0)

    def _write_single_target_fields(self, offset: int, rule: dict[str, int]) -> None:
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_KIND, int(rule.get("kind", 0)))
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_IPV4, int(rule.get("ipv4", 0)))
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PREFIX_LEN, int(rule.get("prefix_len", 0)))
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PORT, int(rule.get("port", 0)))
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PROTOCOL, int(rule.get("protocol", 0)))

    def _clear_single_target_fields(self, offset: int) -> None:
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_KIND, 0)
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_IPV4, 0)
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PREFIX_LEN, 0)
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PORT, 0)
        struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PROTOCOL, 0)

    def _rule_int(self, rule: dict[str, int], key: str, default: int, idx: int) -> int:
        try:
            return int(rule.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"targets[{idx}].{key} must be an integer") from exc

    def _validate_target_rule(self, rule: dict[str, int], idx: int) -> None:
        enabled = self._rule_int(rule, "enabled", 0, idx)
        if enabled not in (0, 1):
            raise ValueError(f"targets[{idx}].enabled must be 0 or 1")

        priority = self._rule_int(rule, "priority", 100, idx)
        if priority < 0 or priority > 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"targets[{idx}].priority must be between 0 and 18446744073709551615")

        kind = self._rule_int(rule, "kind", 0, idx)
        if kind not in (0, 1, 2):
            raise ValueError(f"targets[{idx}].kind must be one of 0, 1, 2")

        prefix_len = self._rule_int(rule, "prefix_len", 0, idx)
        if prefix_len < 0 or prefix_len > 32:
            raise ValueError(f"targets[{idx}].prefix_len must be between 0 and 32")

        port = self._rule_int(rule, "port", 0, idx)
        if port < 0 or port > 65535:
            raise ValueError(f"targets[{idx}].port must be between 0 and 65535")

        protocol = self._rule_int(rule, "protocol", 0, idx)
        if protocol not in (0, 1, 2):
            raise ValueError(f"targets[{idx}].protocol must be one of 0, 1, 2")

        ipv4 = self._rule_int(rule, "ipv4", 0, idx)
        if ipv4 < 0 or ipv4 > 0xFFFFFFFF:
            raise ValueError(f"targets[{idx}].ipv4 must be a valid u32 value")

    def write_latency(self, tid: int, latency_ms: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_LATENCY_NS, latency_ms * 1_000_000)

        self._write_versioned(tid, writer)

    def write_packet_loss(self, tid: int, ppm: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_PACKET_LOSS_PPM, ppm)

        self._write_versioned(tid, writer)

    def write_jitter(self, tid: int, jitter_ms: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_JITTER_NS, jitter_ms * 1_000_000)

        self._write_versioned(tid, writer)

    def write_burst_loss(self, tid: int, burst_loss_len: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_BURST_LOSS_LEN, burst_loss_len)

        self._write_versioned(tid, writer)

    def write_bandwidth(self, tid: int, bps: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_BANDWIDTH_BPS, bps)

        self._write_versioned(tid, writer)

    def write_timeouts(self, tid: int, connect_ms: int, recv_ms: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_CONNECT_TIMEOUT_MS, connect_ms)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_RECV_TIMEOUT_MS, recv_ms)

        self._write_versioned(tid, writer)

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
        def writer(offset: int) -> None:
            if latency_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_UPLINK_LATENCY_NS, latency_ms * 1_000_000)
            if jitter_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_UPLINK_JITTER_NS, jitter_ms * 1_000_000)
            if packet_loss_ppm is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_UPLINK_PACKET_LOSS_PPM, packet_loss_ppm)
            if burst_loss_len is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_UPLINK_BURST_LOSS_LEN, burst_loss_len)
            if bandwidth_bps is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_UPLINK_BANDWIDTH_BPS, bandwidth_bps)

        self._write_versioned(tid, writer)

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
        def writer(offset: int) -> None:
            if latency_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DOWNLINK_LATENCY_NS, latency_ms * 1_000_000)
            if jitter_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DOWNLINK_JITTER_NS, jitter_ms * 1_000_000)
            if packet_loss_ppm is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DOWNLINK_PACKET_LOSS_PPM, packet_loss_ppm)
            if burst_loss_len is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DOWNLINK_BURST_LOSS_LEN, burst_loss_len)
            if bandwidth_bps is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DOWNLINK_BANDWIDTH_BPS, bandwidth_bps)

        self._write_versioned(tid, writer)

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
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_GE_ENABLED, 1 if enabled else 0)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_GE_P_GOOD_TO_BAD_PPM, p_good_to_bad_ppm)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_GE_P_BAD_TO_GOOD_PPM, p_bad_to_good_ppm)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_GE_LOSS_GOOD_PPM, loss_good_ppm)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_GE_LOSS_BAD_PPM, loss_bad_ppm)

        self._write_versioned(tid, writer)

    def write_connection_error(self, tid: int, *, kind: int, prob_ppm: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_CONN_ERR_KIND, kind)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_CONN_ERR_PROB_PPM, prob_ppm)

        self._write_versioned(tid, writer)

    def write_half_open(self, tid: int, *, after_bytes: int, err_kind: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_HALF_OPEN_AFTER_BYTES, after_bytes)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_HALF_OPEN_ERR_KIND, err_kind)

        self._write_versioned(tid, writer)

    def write_packet_duplicate(self, tid: int, *, prob_ppm: int, max_extra: int) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_DUP_PROB_PPM, prob_ppm)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_DUP_MAX_EXTRA, max_extra)

        self._write_versioned(tid, writer)

    def write_packet_reorder(
        self,
        tid: int,
        *,
        prob_ppm: int,
        max_delay_ns: int = 0,
        window: int = 1,
    ) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_REORDER_PROB_PPM, prob_ppm)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_REORDER_MAX_DELAY_NS, max_delay_ns)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_REORDER_WINDOW, window)

        self._write_versioned(tid, writer)

    def write_dns(
        self,
        tid: int,
        *,
        delay_ms: int | None = None,
        timeout_ms: int | None = None,
        nxdomain_ppm: int | None = None,
    ) -> None:
        def writer(offset: int) -> None:
            if delay_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DNS_DELAY_NS, delay_ms * 1_000_000)
            if timeout_ms is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DNS_TIMEOUT_MS, timeout_ms)
            if nxdomain_ppm is not None:
                struct.pack_into("<Q", self._mmap, offset + _OFFSET_DNS_NXDOMAIN_PPM, nxdomain_ppm)

        self._write_versioned(tid, writer)

    def write_target(
        self,
        tid: int,
        *,
        enabled: bool,
        kind: int,
        ipv4: int,
        prefix_len: int,
        port: int,
        protocol: int,
    ) -> None:
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_ENABLED, 1 if enabled else 0)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_KIND, kind)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_IPV4, ipv4)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PREFIX_LEN, prefix_len)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PORT, port)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_PROTOCOL, protocol)

        self._write_versioned(tid, writer)

    def write_targets(self, tid: int, rules: list[dict[str, int]]) -> None:
        if not self._is_available():
            return
        if len(rules) > MAX_TARGET_RULES_PER_TID:
            raise ValueError(f"targets supports up to {MAX_TARGET_RULES_PER_TID} rules")
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(f"targets[{idx}] must be a mapping")
            self._validate_target_rule(rule, idx)

        tid_slot = self._tid_slot(tid)
        target_rules_offset = self._target_rules_offset_for_slot(tid_slot)

        def writer(offset: int) -> None:
            self._clear_target_rules_table(tid_slot)
            for idx, rule in enumerate(rules):
                self._write_target_rule_row(target_rules_offset, idx, rule)

            struct.pack_into("<Q", self._mmap, offset + _OFFSET_TARGET_ENABLED, len(rules))
            if len(rules) == 1:
                self._write_single_target_fields(offset, rules[0])
            else:
                self._clear_single_target_fields(offset)

        self._write_versioned(tid, writer)

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
        def writer(offset: int) -> None:
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_SCHEDULE_TYPE, schedule_type)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_SCHEDULE_PARAM_A, param_a_ns)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_SCHEDULE_PARAM_B, param_b_ns)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_SCHEDULE_PARAM_C, param_c_ns)
            struct.pack_into(
                "<Q",
                self._mmap,
                offset + _OFFSET_SCHEDULE_STARTED_MONOTONIC_NS,
                started_monotonic_ns,
            )

        self._write_versioned(tid, writer)

    def clear(self, tid: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)
            self._mmap[offset : offset + CONFIG_SIZE] = b"\x00" * CONFIG_SIZE
            self._clear_target_rules_table(self._tid_slot(tid))
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, (version + 2) & ~1)

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
