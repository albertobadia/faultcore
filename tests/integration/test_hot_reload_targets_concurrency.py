#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from faultcore.profile_parsers import build_target_profile
from faultcore.shm_writer import SHM_SIZE, get_shm_writer

MATCH_LATENCY_MS = 180
FAST_LATENCY_MAX_MS = 120.0
SLOW_LATENCY_MIN_MS = 250.0


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


def ensure_shm_ready() -> str:
    name = os.environ.get("FAULTCORE_CONFIG_SHM", f"/faultcore_{os.getpid()}_config")
    os.environ["FAULTCORE_CONFIG_SHM"] = name
    path = f"/dev/shm/{name.lstrip('/')}"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.ftruncate(fd, SHM_SIZE)
    finally:
        os.close(fd)
    return name


def tcp_echo_once(host: str, port: int, payload: str) -> float:
    started = time.perf_counter()
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(f"{payload}\n".encode())
        data = sock.recv(4096)
    if not data.startswith(b"ECHO:"):
        raise RuntimeError(f"unexpected response: {data!r}")
    return (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore hot reload targets[] concurrency integration")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--duration", type=float, default=3.0, help="stress duration in seconds")
    parser.add_argument("--workers", type=int, default=4, help="concurrent traffic workers")
    parser.add_argument(
        "--toggle-interval-ms",
        type=float,
        default=300.0,
        help="targets reload interval (stable default for mixed fast/slow sampling)",
    )
    args = parser.parse_args()

    print(
        f"[{datetime.now().isoformat()}] hot reload targets concurrency "
        f"host={args.host} port={args.port} workers={args.workers} duration={args.duration}s"
    )
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    writer = get_shm_writer()
    if writer._mmap is None:
        print("ERROR: shared memory writer not available")
        return 1

    match_rules = [
        build_target_profile(target=f"tcp://{args.host}:{args.port}", priority=300),
        build_target_profile(target="10.0.0.0/8", port=6553, protocol="tcp", priority=100),
    ]
    no_match_rules = [
        build_target_profile(target="10.0.0.0/8", port=6553, protocol="tcp", priority=300),
        build_target_profile(target="192.168.0.0/16", port=6553, protocol="tcp", priority=100),
    ]

    ready_cond = threading.Condition()
    worker_tids: dict[int, int] = {}
    run_event = threading.Event()
    stop_event = threading.Event()
    stats = TrafficStats()
    stats_lock = threading.Lock()

    def worker(worker_id: int) -> None:
        tid = threading.get_native_id()
        with ready_cond:
            worker_tids[worker_id] = tid
            ready_cond.notify_all()

        run_event.wait()
        seq = 0
        while not stop_event.is_set():
            payload = f"reload-targets-{worker_id}-{seq}"
            seq += 1
            try:
                elapsed_ms = tcp_echo_once(args.host, args.port, payload)
            except Exception as exc:  # noqa: BLE001
                with stats_lock:
                    stats.ops += 1
                    stats.errors += 1
                    if stats.first_error is None:
                        stats.first_error = repr(exc)
                continue

            with stats_lock:
                stats.ops += 1
                stats.total_latency_ms += elapsed_ms
                stats.min_latency_ms = min(stats.min_latency_ms, elapsed_ms)
                stats.max_latency_ms = max(stats.max_latency_ms, elapsed_ms)
                if elapsed_ms <= FAST_LATENCY_MAX_MS:
                    stats.fast_samples += 1
                if elapsed_ms >= SLOW_LATENCY_MIN_MS:
                    stats.slow_samples += 1

    workers = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(args.workers)]
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
        writer.write_latency(tid, MATCH_LATENCY_MS)
        writer.write_targets(tid, match_rules)

    def reloader() -> None:
        interval_s = max(0.001, args.toggle_interval_ms / 1000.0)
        while not stop_event.is_set():
            for tid in tids:
                writer.write_targets(tid, match_rules)
            time.sleep(interval_s)
            for tid in tids:
                writer.write_targets(tid, no_match_rules)
            time.sleep(interval_s)

    reloader_thread = threading.Thread(target=reloader, daemon=True)
    reloader_thread.start()

    run_event.set()
    time.sleep(max(0.5, args.duration))
    stop_event.set()

    for thread in workers:
        thread.join(timeout=2.0)
    reloader_thread.join(timeout=2.0)
    for tid in tids:
        writer.clear(tid)

    print(
        "traffic: "
        f"ops={stats.ops} errors={stats.errors} "
        f"avg_ms={stats.avg_latency_ms:.2f} "
        f"min_ms={stats.min_latency_ms:.2f} "
        f"max_ms={stats.max_latency_ms:.2f} "
        f"fast={stats.fast_samples} slow={stats.slow_samples}"
    )

    if stats.ops == 0:
        print("ERROR: no traffic operations were executed")
        return 1
    if stats.errors > 0:
        print(f"ERROR: traffic had {stats.errors} socket errors first={stats.first_error!r}")
        return 1
    if stats.fast_samples == 0 or stats.slow_samples == 0:
        print(
            "ERROR: expected both fast and slow latency samples during hot reload "
            f"(fast={stats.fast_samples}, slow={stats.slow_samples})"
        )
        return 1

    print("hot reload targets concurrency integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
