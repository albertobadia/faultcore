#!/usr/bin/env python3
import argparse
import socket
import statistics
import time

import faultcore


def tcp_echo(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(f"{message}\n".encode())
        response = sock.recv(4096)
        return response.decode().strip()
    finally:
        sock.close()


def run_calls(fn, *, count: int) -> dict[str, float]:
    samples_ms: list[float] = []
    start = time.perf_counter()
    for idx in range(count):
        one_start = time.perf_counter()
        response = fn(f"perf-{idx}")
        if not response.startswith("ECHO:"):
            raise RuntimeError(f"unexpected response: {response!r}")
        samples_ms.append((time.perf_counter() - one_start) * 1000)
    elapsed = time.perf_counter() - start
    sorted_samples = sorted(samples_ms)
    p95_idx = max(0, min(len(sorted_samples) - 1, int(len(sorted_samples) * 0.95) - 1))
    return {
        "count": float(count),
        "total_s": elapsed,
        "avg_ms": statistics.fmean(samples_ms),
        "p95_ms": sorted_samples[p95_idx],
        "min_ms": sorted_samples[0],
        "max_ms": sorted_samples[-1],
        "throughput_rps": count / elapsed if elapsed > 0 else 0.0,
    }


def print_result(title: str, data: dict[str, float]) -> None:
    print(f"{title}:")
    print(
        f"  count={int(data['count'])} total={data['total_s']:.3f}s "
        f"avg={data['avg_ms']:.3f}ms p95={data['p95_ms']:.3f}ms "
        f"min={data['min_ms']:.3f}ms max={data['max_ms']:.3f}ms "
        f"throughput={data['throughput_rps']:.2f} rps"
    )


def run_benchmark(host: str, port: int, count: int, latency_ms: int) -> None:
    faultcore.register_policy("perf_latency", latency_ms=latency_ms)

    def baseline_call(msg: str) -> str:
        return tcp_echo(host, port, msg)

    @faultcore.apply_policy("perf_latency")
    def policy_call(msg: str) -> str:
        return tcp_echo(host, port, msg)

    baseline = run_calls(baseline_call, count=count)
    policy = run_calls(policy_call, count=count)

    print_result("baseline(no policy)", baseline)
    print_result(f"with policy(latency_ms={latency_ms})", policy)

    print("delta:")
    print(
        f"  avg_ms +{policy['avg_ms'] - baseline['avg_ms']:.3f} "
        f"p95_ms +{policy['p95_ms'] - baseline['p95_ms']:.3f} "
        f"throughput {policy['throughput_rps'] - baseline['throughput_rps']:.2f} rps"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultCore baseline benchmark (no policy vs policy)")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--count", type=int, default=100, help="requests per scenario")
    parser.add_argument("--latency-ms", type=int, default=50, help="policy latency for comparison")
    args = parser.parse_args()

    if args.count <= 0:
        raise ValueError("--count must be > 0")
    if args.latency_ms < 0:
        raise ValueError("--latency-ms must be >= 0")

    print("=" * 64)
    print(" FaultCore Baseline Benchmark ".center(64, "="))
    print("=" * 64)
    run_benchmark(args.host, args.port, args.count, args.latency_ms)
    print("\nStart TCP server first:")
    print("  python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Run with interceptor:")
    print("  examples/run_with_preload.sh 12_perf_baseline.py")
