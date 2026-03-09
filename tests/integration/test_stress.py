#!/usr/bin/env python3
import argparse
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import faultcore


def read_rss_kb() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1])
    except Exception:  # noqa: BLE001
        return -1
    return -1


def tcp_echo_once(host: str, port: int, payload: str) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        sock.connect((host, port))
        sock.sendall(f"{payload}\n".encode())
        data = sock.recv(4096)
        if not data.startswith(b"ECHO:"):
            raise RuntimeError(f"unexpected response: {data!r}")
    finally:
        sock.close()


@dataclass
class StressStats:
    ops: int = 0
    ok: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.ops if self.ops > 0 else 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.ops if self.ops > 0 else 1.0


def run_stress_phase(
    label: str,
    call_fn,
    *,
    duration_s: float,
    workers: int,
    max_error_rate: float,
) -> StressStats:
    print(f"[{datetime.now().isoformat()}] stress phase={label} duration={duration_s}s workers={workers}")
    stop_at = time.perf_counter() + duration_s
    stats = StressStats()
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        local_ops = 0
        local_ok = 0
        local_errors = 0
        local_total_ms = 0.0
        local_max_ms = 0.0

        while time.perf_counter() < stop_at:
            payload = f"stress-{label}-{worker_id}-{local_ops}"
            started = time.perf_counter()
            try:
                call_fn(payload)
                local_ok += 1
            except Exception:  # noqa: BLE001
                local_errors += 1
            elapsed_ms = (time.perf_counter() - started) * 1000
            local_total_ms += elapsed_ms
            if elapsed_ms > local_max_ms:
                local_max_ms = elapsed_ms
            local_ops += 1

        with lock:
            stats.ops += local_ops
            stats.ok += local_ok
            stats.errors += local_errors
            stats.total_latency_ms += local_total_ms
            stats.max_latency_ms = max(stats.max_latency_ms, local_max_ms)

    threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(
        f"{label}: ops={stats.ops} ok={stats.ok} errors={stats.errors} "
        f"err_rate={stats.error_rate:.3f} avg_ms={stats.avg_latency_ms:.2f} max_ms={stats.max_latency_ms:.2f}"
    )
    if stats.ops == 0:
        raise RuntimeError(f"{label}: no operations executed")
    if stats.error_rate > max_error_rate:
        raise RuntimeError(f"{label}: error_rate {stats.error_rate:.3f} exceeds allowed {max_error_rate:.3f}")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore stress integration (concurrency + stability)")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--mode", choices=["smoke", "long"], default="smoke")
    parser.add_argument("--duration", type=float, default=2.0, help="phase duration in seconds for smoke mode")
    parser.add_argument("--workers", type=int, default=6, help="worker threads for smoke mode")
    parser.add_argument("--max-error-rate", type=float, default=0.10, help="maximum allowed error ratio")
    args = parser.parse_args()

    duration = args.duration if args.mode == "smoke" else max(args.duration, 20.0)
    workers = args.workers if args.mode == "smoke" else max(args.workers, 24)
    print(
        f"[{datetime.now().isoformat()}] stress integration mode={args.mode} "
        f"host={args.host} port={args.port} duration={duration}s workers={workers}"
    )

    rss_before = read_rss_kb()

    def baseline_call(payload: str) -> None:
        tcp_echo_once(args.host, args.port, payload)

    faultcore.register_policy(
        "stress_latency_profile",
        latency_ms=25,
        downlink={"jitter_ms": 5},
    )

    @faultcore.apply_policy("stress_latency_profile")
    def policy_call(payload: str) -> None:
        tcp_echo_once(args.host, args.port, payload)

    try:
        baseline = run_stress_phase(
            "baseline",
            baseline_call,
            duration_s=duration,
            workers=workers,
            max_error_rate=args.max_error_rate,
        )
        policy = run_stress_phase(
            "policy_latency",
            policy_call,
            duration_s=duration,
            workers=workers,
            max_error_rate=args.max_error_rate,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    rss_after = read_rss_kb()
    if rss_before >= 0 and rss_after >= 0:
        print(f"rss_kb: before={rss_before} after={rss_after} delta={rss_after - rss_before}")
    print(
        "summary: "
        f"baseline_rps={baseline.ops / duration:.2f} "
        f"policy_rps={policy.ops / duration:.2f} "
        f"baseline_avg_ms={baseline.avg_latency_ms:.2f} "
        f"policy_avg_ms={policy.avg_latency_ms:.2f}"
    )
    print("stress integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
