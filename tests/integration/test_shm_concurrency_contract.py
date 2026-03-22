#!/usr/bin/env python3
import argparse
import os
import socket
import struct
import sys
import threading
import time
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from faultcore.shm_writer import (
    _OFFSET_BANDWIDTH_BPS,
    _OFFSET_DOWNLINK_JITTER_NS,
    _OFFSET_DOWNLINK_LATENCY_NS,
    _OFFSET_JITTER_NS,
    _OFFSET_LATENCY_NS,
    _OFFSET_PACKET_LOSS_PPM,
    _OFFSET_RULESET_GENERATION,
    _OFFSET_UPLINK_JITTER_NS,
    _OFFSET_UPLINK_LATENCY_NS,
    SHM_SIZE,
    get_shm_writer,
)

NS_PER_MS = 1_000_000
FAST_LATENCY_MAX_MS = 120.0
SLOW_LATENCY_MIN_MS = 250.0

PROFILE_A = (
    1 * NS_PER_MS,
    2 * NS_PER_MS,
    0,
    1 * NS_PER_MS,
    1 * NS_PER_MS,
    1 * NS_PER_MS,
)
PROFILE_B = (
    180 * NS_PER_MS,
    25 * NS_PER_MS,
    0,
    120 * NS_PER_MS,
    120 * NS_PER_MS,
    120 * NS_PER_MS,
)


@dataclass
class TrafficStats:
    ops: int = 0
    errors: int = 0
    fast_samples: int = 0
    slow_samples: int = 0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    first_error: str | None = None

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.ops if self.ops else 0.0


@dataclass
class ReadStats:
    samples: int = 0
    invalid_snapshots: int = 0
    unstable_retries: int = 0
    first_invalid: tuple[int, tuple[int, int, int, int, int, int]] | None = None


def ensure_shm_ready() -> str:
    name = os.environ.get("FAULTCORE_CONFIG_SHM", f"/faultcore_{os.getpid()}_config")
    os.environ["FAULTCORE_CONFIG_SHM"] = name
    path = f"/dev/shm/{name.lstrip('/')}"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.ftruncate(fd, SHM_SIZE)
    finally:
        os.close(fd)


class TestTIDHashIntegration:
    def test_concurrent_thread_policy_isolation(self):
        ensure_shm_ready()
        from faultcore import get_thread_policy, set_thread_policy

        errors = []
        barrier = threading.Barrier(10)

        def writer_thread(thread_id: int):
            policy_name = f"policy_{thread_id}"
            set_thread_policy(policy_name)

            barrier.wait()

            for _ in range(100):
                current = get_thread_policy()
                if current != policy_name:
                    errors.append(f"Thread {thread_id} expected {policy_name}, got {current}")

        threads = [threading.Thread(target=writer_thread, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Policy interference detected: {errors[:5]}"

    def test_high_thread_count_hash_distribution(self):
        ensure_shm_ready()

        slot_counts = Counter()

        writer = get_shm_writer()

        test_tids = list(range(0, 100000, 100))

        for tid in test_tids:
            slot = writer._tid_slot(tid)
            slot_counts[slot] += 1

        num_unique_slots = len(slot_counts)
        unique_ratio = num_unique_slots / len(test_tids)

        msg = f"Hash collisions: {num_unique_slots} slots for {len(test_tids)} TIDs"
        assert unique_ratio > 0.1, msg


def tcp_echo_once(host: str, port: int, payload: str) -> float:
    started = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((host, port))
        sock.sendall(f"{payload}\n".encode())
        data = sock.recv(4096)
        if not data.startswith(b"ECHO:"):
            raise RuntimeError(f"unexpected response: {data!r}")
    finally:
        sock.close()
    return (time.perf_counter() - started) * 1000


def publish_profile(writer, tid: int, profile: tuple[int, int, int, int, int, int]) -> None:
    latency_ns, jitter_ns, packet_loss_ppm, uplink_latency_ns, uplink_jitter_ns, downlink_latency_ns = profile

    def mutate(offset: int) -> None:
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_LATENCY_NS, latency_ns)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_JITTER_NS, jitter_ns)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_PACKET_LOSS_PPM, packet_loss_ppm)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_UPLINK_LATENCY_NS, uplink_latency_ns)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_UPLINK_JITTER_NS, uplink_jitter_ns)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_DOWNLINK_LATENCY_NS, downlink_latency_ns)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_DOWNLINK_JITTER_NS, 0)
        struct.pack_into("<Q", writer._mmap, offset + _OFFSET_BANDWIDTH_BPS, 0)

    writer._write_with_generation_publish(tid, mutate)


def read_stable_profile(writer, tid: int, retries: int = 30) -> tuple[int, int, int, int, int, int] | None:
    offset = writer._get_offset(tid)
    for _ in range(retries):
        generation_1 = struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_RULESET_GENERATION)[0]
        if generation_1 & 1:
            continue
        snapshot = (
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_LATENCY_NS)[0],
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_JITTER_NS)[0],
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_PACKET_LOSS_PPM)[0],
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_UPLINK_LATENCY_NS)[0],
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_UPLINK_JITTER_NS)[0],
            struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_DOWNLINK_LATENCY_NS)[0],
        )
        generation_2 = struct.unpack_from("<Q", writer._mmap, offset + _OFFSET_RULESET_GENERATION)[0]
        if generation_1 == generation_2 and not (generation_2 & 1):
            return snapshot
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore SHM concurrent writer/reader contract integration")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--duration", type=float, default=3.0, help="traffic/mutation duration in seconds")
    parser.add_argument("--workers", type=int, default=4, help="concurrent traffic workers")
    parser.add_argument("--toggle-interval-ms", type=float, default=30.0, help="profile toggle interval per phase")
    args = parser.parse_args()

    print(
        f"[{datetime.now().isoformat()}] shm concurrency integration "
        f"host={args.host} port={args.port} workers={args.workers} duration={args.duration}s"
    )
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    writer = get_shm_writer()
    if writer._mmap is None:
        print("ERROR: shared memory writer not available")
        return 1

    ready_cond = threading.Condition()
    worker_tids: dict[int, int] = {}
    run_event = threading.Event()
    stop_event = threading.Event()
    traffic_stats = TrafficStats()
    traffic_lock = threading.Lock()
    read_stats = ReadStats()
    read_lock = threading.Lock()

    def traffic_worker(worker_id: int) -> None:
        tid = threading.get_native_id()
        with ready_cond:
            worker_tids[worker_id] = tid
            ready_cond.notify_all()

        run_event.wait()
        seq = 0
        while not stop_event.is_set():
            payload = f"shm-contract-{worker_id}-{seq}"
            seq += 1
            try:
                elapsed_ms = tcp_echo_once(args.host, args.port, payload)
            except Exception as exc:  # noqa: BLE001
                with traffic_lock:
                    traffic_stats.ops += 1
                    traffic_stats.errors += 1
                    if traffic_stats.first_error is None:
                        traffic_stats.first_error = repr(exc)
                continue

            with traffic_lock:
                traffic_stats.ops += 1
                traffic_stats.total_latency_ms += elapsed_ms
                traffic_stats.min_latency_ms = min(traffic_stats.min_latency_ms, elapsed_ms)
                traffic_stats.max_latency_ms = max(traffic_stats.max_latency_ms, elapsed_ms)
                if elapsed_ms <= FAST_LATENCY_MAX_MS:
                    traffic_stats.fast_samples += 1
                if elapsed_ms >= SLOW_LATENCY_MIN_MS:
                    traffic_stats.slow_samples += 1

    workers = [threading.Thread(target=traffic_worker, args=(idx,), daemon=True) for idx in range(args.workers)]
    for thread in workers:
        thread.start()

    with ready_cond:
        ready = ready_cond.wait_for(lambda: len(worker_tids) == args.workers, timeout=5.0)
    if not ready:
        print(f"ERROR: expected {args.workers} worker tids, got {len(worker_tids)}")
        stop_event.set()
        for thread in workers:
            thread.join(timeout=1.0)
        return 1

    tids = [worker_tids[idx] for idx in sorted(worker_tids)]
    for tid in tids:
        writer.clear(tid)
        publish_profile(writer, tid, PROFILE_A)

    def mutator() -> None:
        interval_s = max(0.001, args.toggle_interval_ms / 1000.0)
        while not stop_event.is_set():
            for tid in tids:
                publish_profile(writer, tid, PROFILE_A)
            time.sleep(interval_s)
            for tid in tids:
                publish_profile(writer, tid, PROFILE_B)
            time.sleep(interval_s)

    def stable_reader() -> None:
        expected = {PROFILE_A, PROFILE_B}
        while not stop_event.is_set():
            for tid in tids:
                snapshot = read_stable_profile(writer, tid)
                with read_lock:
                    if snapshot is None:
                        read_stats.unstable_retries += 1
                        continue
                    read_stats.samples += 1
                    if snapshot not in expected:
                        read_stats.invalid_snapshots += 1
                        if read_stats.first_invalid is None:
                            read_stats.first_invalid = (tid, snapshot)

    mutator_thread = threading.Thread(target=mutator, daemon=True)
    reader_thread = threading.Thread(target=stable_reader, daemon=True)
    mutator_thread.start()
    reader_thread.start()

    run_event.set()
    time.sleep(max(0.5, args.duration))

    stop_event.set()
    for thread in workers:
        thread.join(timeout=2.0)
    mutator_thread.join(timeout=2.0)
    reader_thread.join(timeout=2.0)

    for tid in tids:
        writer.clear(tid)

    print(
        "traffic: "
        f"ops={traffic_stats.ops} errors={traffic_stats.errors} "
        f"avg_ms={traffic_stats.avg_latency_ms:.2f} "
        f"min_ms={traffic_stats.min_latency_ms:.2f} "
        f"max_ms={traffic_stats.max_latency_ms:.2f} "
        f"fast={traffic_stats.fast_samples} slow={traffic_stats.slow_samples}"
    )
    print(
        "reader: "
        f"samples={read_stats.samples} unstable_retries={read_stats.unstable_retries} "
        f"invalid_snapshots={read_stats.invalid_snapshots}"
    )

    if traffic_stats.ops == 0:
        print("ERROR: no traffic operations were executed")
        return 1
    if traffic_stats.errors > 0:
        print(f"ERROR: traffic had {traffic_stats.errors} socket errors first={traffic_stats.first_error!r}")
        return 1
    if traffic_stats.fast_samples == 0 or traffic_stats.slow_samples == 0:
        print(
            "ERROR: expected to observe both fast and slow latencies "
            f"(fast={traffic_stats.fast_samples}, slow={traffic_stats.slow_samples})"
        )
        return 1
    if read_stats.samples == 0:
        print("ERROR: no stable SHM snapshots observed")
        return 1
    if read_stats.invalid_snapshots > 0:
        print(f"ERROR: observed invalid SHM snapshots, first={read_stats.first_invalid!r}")
        return 1

    print("shm concurrency integration: PASS")
    return 0


class TestSHMErrorHandling:
    def test_shm_graceful_degradation_on_invalid_shm(self):
        import os
        from unittest.mock import patch

        invalid_name = f"/dev/shm/test_invalid_shm_{os.getpid()}"

        with suppress(FileNotFoundError):
            os.unlink(invalid_name)

        with patch.dict(os.environ, {"FAULTCORE_CONFIG_SHM": invalid_name}):
            from faultcore.shm_writer import SHMWriter

            writer = SHMWriter()

            assert writer._mmap is None or writer._fd is None

    def test_shm_graceful_degradation_on_permission_denied(self):
        import os
        from unittest.mock import patch

        import pytest

        protected_name = f"/dev/shm/test_protected_shm_{os.getpid()}"

        try:
            fd = os.open(protected_name, os.O_CREAT | os.O_RDWR, 0o000)
            os.close(fd)

            with patch.dict(os.environ, {"FAULTCORE_CONFIG_SHM": protected_name}):
                from faultcore.shm_writer import SHMWriter

                writer = SHMWriter()

                assert writer._mmap is None or writer._fd is None
        except PermissionError:
            pytest.skip("Cannot test permission denied in this environment")
        finally:
            with suppress(FileNotFoundError):
                os.unlink(protected_name)


if __name__ == "__main__":
    sys.exit(main())
