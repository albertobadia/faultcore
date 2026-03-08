import mmap
import os
import struct
import threading

FAULTCORE_MAGIC = 0xFACC0DE
MAX_FDS = 131072
MAX_TIDS = 65536
CONFIG_SIZE = 224

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


class SHMWriter:
    def __init__(self, shm_name: str | None = None):
        self._fd = None
        self._mmap = None
        self._lock = threading.Lock()

        name = shm_name or os.environ.get("FAULTCORE_CONFIG_SHM", f"/faultcore_{os.getpid()}_config")

        try:
            self._fd = os.open(f"/dev/shm/{name}", os.O_RDWR)
            self._mmap = mmap.mmap(self._fd, 0, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        except (FileNotFoundError, PermissionError, OSError):
            self._fd = None
            self._mmap = None

    def _is_available(self) -> bool:
        return self._mmap is not None

    def _get_offset(self, tid: int) -> int:
        hash_val = (tid ^ (tid >> 16)) * 0x45D9F3B ^ (tid >> 16)
        idx = MAX_FDS + (hash_val % MAX_TIDS)
        return idx * CONFIG_SIZE

    def _write_versioned(self, tid: int, writer) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)
            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            writer(offset)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, (version + 2) & ~1)

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

    def clear(self, tid: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, 0)

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
