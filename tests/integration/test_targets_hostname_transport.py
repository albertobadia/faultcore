#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import time
from datetime import datetime

import faultcore
from faultcore.shm_writer import SHM_SIZE

MATCH_LATENCY_MS = 180


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


def tcp_echo(hostname: str, port: int, message: str) -> str:
    with socket.create_connection((hostname, port), timeout=5) as sock:
        sock.sendall(f"{message}\n".encode())
        data = sock.recv(4096)
        return data.decode("utf-8").strip()


def measure_ms(callable_fn, count: int = 4) -> float:
    samples: list[float] = []
    for idx in range(count):
        started = time.perf_counter()
        response = callable_fn(f"targets-hostname-{idx}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not response.startswith("ECHO:"):
            raise RuntimeError(f"unexpected echo response: {response}")
        samples.append(elapsed_ms)
    return sum(samples) / len(samples)


def run_baseline_case(hostname: str, port: int) -> float:
    def call(message: str) -> str:
        return tcp_echo(hostname, port, message)

    avg = measure_ms(call, count=4)
    print(f"baseline avg latency: {avg:.2f}ms")
    return avg


def assert_match_latency(avg_ms: float, baseline_ms: float, label: str) -> None:
    if avg_ms < baseline_ms + 90:
        raise RuntimeError(
            f"{label}: expected avg >= {baseline_ms + 90:.2f}ms (baseline {baseline_ms:.2f}ms), got {avg_ms:.2f}ms"
        )


def assert_no_match_latency(avg_ms: float, baseline_ms: float, label: str) -> None:
    if avg_ms > baseline_ms + 70:
        raise RuntimeError(
            f"{label}: expected avg <= {baseline_ms + 70:.2f}ms (baseline {baseline_ms:.2f}ms), got {avg_ms:.2f}ms"
        )


def run_hostname_exact_case(hostname: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_hostname_transport_exact",
        latency_ms=MATCH_LATENCY_MS,
        targets=[{"hostname": hostname, "priority": 200}],
    )

    @faultcore.apply_policy("targets_hostname_transport_exact")
    def call(message: str) -> str:
        return tcp_echo(hostname, port, message)

    avg = measure_ms(call, count=3)
    print(f"hostname exact avg latency: {avg:.2f}ms")
    assert_match_latency(avg, baseline_ms, "hostname exact transport match")


def run_hostname_port_protocol_case(hostname: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_hostname_transport_port_protocol",
        latency_ms=MATCH_LATENCY_MS,
        targets=[{"hostname": hostname, "port": port, "protocol": "tcp", "priority": 200}],
    )

    @faultcore.apply_policy("targets_hostname_transport_port_protocol")
    def call(message: str) -> str:
        return tcp_echo(hostname, port, message)

    avg = measure_ms(call, count=3)
    print(f"hostname+port/protocol avg latency: {avg:.2f}ms")
    assert_match_latency(avg, baseline_ms, "hostname+port/protocol transport match")


def run_hostname_no_match_case(hostname: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_hostname_transport_no_match",
        latency_ms=MATCH_LATENCY_MS,
        targets=[{"hostname": "other.foo.com", "priority": 200}],
    )

    @faultcore.apply_policy("targets_hostname_transport_no_match")
    def call(message: str) -> str:
        return tcp_echo(hostname, port, message)

    avg = measure_ms(call, count=3)
    print(f"hostname no-match avg latency: {avg:.2f}ms")
    assert_no_match_latency(avg, baseline_ms, "hostname transport no-match")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore hostname transport targets integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host (compat with shared runner)")
    parser.add_argument("--target-hostname", default="localhost", help="hostname used by client connect() and rules")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--mode", choices=["match", "no-match", "all"], default="all")
    args = parser.parse_args()

    print(
        f"[{datetime.now().isoformat()}] targets hostname transport mode={args.mode} "
        f"host={args.host} target_hostname={args.target_hostname}"
    )
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    try:
        baseline_ms = run_baseline_case(args.target_hostname, args.port)
        if args.mode in {"match", "all"}:
            run_hostname_exact_case(args.target_hostname, args.port, baseline_ms)
            run_hostname_port_protocol_case(args.target_hostname, args.port, baseline_ms)
        if args.mode in {"no-match", "all"}:
            run_hostname_no_match_case(args.target_hostname, args.port, baseline_ms)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("targets hostname transport integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
