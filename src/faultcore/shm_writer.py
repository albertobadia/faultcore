import logging
import mmap
import os
import struct
import threading

logger = logging.getLogger(__name__)

FAULTCORE_MAGIC = 0xFACC0DE
MAX_FDS = 131072
MAX_TIDS = 65536
CONFIG_SIZE = 56

_OFFSET_MAGIC = 0
_OFFSET_VERSION = 4
_OFFSET_LATENCY_NS = 12
_OFFSET_PACKET_LOSS_PPM = 20
_OFFSET_BANDWIDTH_BPS = 28
_OFFSET_CONNECT_TIMEOUT_MS = 36
_OFFSET_RECV_TIMEOUT_MS = 44


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

    def write_latency(self, tid: int, latency_ms: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)

            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_LATENCY_NS, latency_ms * 1_000_000)

            new_version = (version + 2) & ~1
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, new_version)

    def write_packet_loss(self, tid: int, ppm: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)

            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_PACKET_LOSS_PPM, ppm)

            new_version = (version + 2) & ~1
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, new_version)

    def write_bandwidth(self, tid: int, bps: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)

            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_BANDWIDTH_BPS, bps)

            new_version = (version + 2) & ~1
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, new_version)

    def write_timeouts(self, tid: int, connect_ms: int, recv_ms: int) -> None:
        if not self._is_available():
            return

        offset = self._get_offset(tid)

        with self._lock:
            version = struct.unpack_from("<Q", self._mmap, offset + _OFFSET_VERSION)[0]
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, version | 1)

            struct.pack_into("<I", self._mmap, offset + _OFFSET_MAGIC, FAULTCORE_MAGIC)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_CONNECT_TIMEOUT_MS, connect_ms)
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_RECV_TIMEOUT_MS, recv_ms)

            new_version = (version + 2) & ~1
            struct.pack_into("<Q", self._mmap, offset + _OFFSET_VERSION, new_version)

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

    def __enter__(self):
        return self

    def __exit__(self, *args):
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
