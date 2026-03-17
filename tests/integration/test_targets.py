#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import time
from datetime import datetime

import faultcore
from faultcore.shm_writer import SHM_SIZE


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


def tcp_echo(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(f"{message}\n".encode())
        data = sock.recv(4096)
        return data.decode("utf-8").strip()
    finally:
        sock.close()


def measure_ms(callable_fn, count: int = 3) -> float:
    samples = []
    for idx in range(count):
        started = time.perf_counter()
        response = callable_fn(f"target-test-{idx}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not response.startswith("ECHO:"):
            raise RuntimeError(f"unexpected echo response: {response}")
        samples.append(elapsed_ms)
    return sum(samples) / len(samples)


def run_match_case(host: str, port: int) -> float:
    faultcore.register_policy(
        "targets_match",
        latency="180ms",
        targets=[
            {"target": f"{host}:{port}", "priority": 200},
            {"target": "10.0.0.0/8", "port": 9000, "priority": 10},
        ],
    )

    faultcore.set_thread_policy("targets_match")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host, port, message)

    avg = measure_ms(call, count=3)
    print(f"match avg latency: {avg:.2f}ms")
    if avg < 120:
        raise RuntimeError(f"expected target match latency >= 120ms, got {avg:.2f}ms")
    return avg


def run_no_match_case(host: str, port: int) -> float:
    faultcore.register_policy(
        "targets_no_match",
        latency="180ms",
        targets=[{"target": "10.0.0.0/8", "port": 9000, "priority": 200}],
    )

    faultcore.set_thread_policy("targets_no_match")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host, port, message)

    avg = measure_ms(call, count=3)
    print(f"no-match avg latency: {avg:.2f}ms")
    if avg > 80:
        raise RuntimeError(f"expected no-match latency <= 80ms, got {avg:.2f}ms")
    return avg


def run_protocol_mismatch_case(host: str, port: int) -> float:
    faultcore.register_policy(
        "targets_protocol_mismatch",
        latency="180ms",
        targets=[{"target": f"{host}:{port}", "protocol": "udp", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_protocol_mismatch")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host, port, message)

    avg = measure_ms(call, count=3)
    print(f"protocol-mismatch avg latency: {avg:.2f}ms")
    if avg > 80:
        raise RuntimeError(f"expected protocol-mismatch latency <= 80ms, got {avg:.2f}ms")
    return avg


def run_port_mismatch_case(host: str, port: int) -> float:
    faultcore.register_policy(
        "targets_port_mismatch",
        latency="180ms",
        targets=[{"target": host, "port": port + 1, "priority": 200}],
    )

    faultcore.set_thread_policy("targets_port_mismatch")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host, port, message)

    avg = measure_ms(call, count=3)
    print(f"port-mismatch avg latency: {avg:.2f}ms")
    if avg > 80:
        raise RuntimeError(f"expected port-mismatch latency <= 80ms, got {avg:.2f}ms")
    return avg


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore targets[] integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="echo server host")
    parser.add_argument("--port", type=int, default=9000, help="echo server port")
    parser.add_argument("--mode", choices=["match", "no-match", "all"], default="all")
    args = parser.parse_args()

    print(f"[{datetime.now().isoformat()}] targets integration mode={args.mode} host={args.host} port={args.port}")
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    try:
        if args.mode in {"match", "all"}:
            run_match_case(args.host, args.port)
        if args.mode in {"no-match", "all"}:
            run_no_match_case(args.host, args.port)
            run_protocol_mismatch_case(args.host, args.port)
            run_port_mismatch_case(args.host, args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("targets integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
