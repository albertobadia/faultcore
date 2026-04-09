#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from http.client import HTTPConnection
from time import perf_counter

import faultcore
from faultcore.shm_writer import SHM_SIZE

MATCH_LATENCY_MS = 180
MATCH_LATENCY = f"{MATCH_LATENCY_MS}ms"


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


def http_echo(hostname: str, port: int, message: str) -> str:
    encoded = urllib.parse.quote(message, safe="")
    conn = HTTPConnection(hostname, port, timeout=5)
    try:
        conn.request("GET", f"/echo/{encoded}")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
    finally:
        conn.close()
    if resp.status != 200:
        raise RuntimeError(f"unexpected HTTP status: {resp.status}, body={body!r}")
    payload = json.loads(body)
    echoed = payload.get("message")
    if echoed != message:
        raise RuntimeError(f"unexpected echo payload: {payload!r}")
    return echoed


def measure_ms(callable_fn: Callable[[str], str], count: int = 3) -> float:
    samples: list[float] = []
    for idx in range(count):
        started = perf_counter()
        out = callable_fn(f"http-hostname-{idx}")
        elapsed_ms = (perf_counter() - started) * 1000
        if not out.startswith("http-hostname-"):
            raise RuntimeError(f"unexpected HTTP echo output: {out!r}")
        samples.append(elapsed_ms)
    return sum(samples) / len(samples)


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


def run_baseline_case(hostname: str, port: int) -> float:
    def call(message: str) -> str:
        return http_echo(hostname, port, message)

    avg = measure_ms(call, count=4)
    print(f"http baseline avg latency: {avg:.2f}ms")
    return avg


def run_hostname_exact_case(hostname: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_http_hostname_exact",
        latency=MATCH_LATENCY,
        targets=[{"hostname": hostname, "port": port, "protocol": "tcp", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_http_hostname_exact")

    @faultcore.fault()
    def call(message: str) -> str:
        return http_echo(hostname, port, message)

    avg = measure_ms(call)
    print(f"http hostname exact avg latency: {avg:.2f}ms")
    assert_match_latency(avg, baseline_ms, "http hostname exact")


def run_ip_vs_hostname_precedence_cases(hostname: str, ip_host: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_http_ip_priority_over_hostname",
        latency=MATCH_LATENCY,
        targets=[
            {"target": f"tcp://{ip_host}:{port}", "priority": 300},
            {"hostname": hostname, "port": port, "protocol": "tcp", "priority": 100},
        ],
    )

    faultcore.set_thread_policy("targets_http_ip_priority_over_hostname")

    @faultcore.fault()
    def call_ip_priority(message: str) -> str:
        return http_echo(hostname, port, message)

    avg_ip_priority = measure_ms(call_ip_priority)
    print(f"http precedence ip>hostname avg latency: {avg_ip_priority:.2f}ms")
    assert_match_latency(avg_ip_priority, baseline_ms, "http precedence ip>hostname")

    faultcore.register_policy(
        "targets_http_hostname_priority_over_ip",
        latency=MATCH_LATENCY,
        targets=[
            {"target": f"tcp://{ip_host}:{port}", "priority": 100},
            {"hostname": hostname, "port": port, "protocol": "tcp", "priority": 300},
        ],
    )

    faultcore.set_thread_policy("targets_http_hostname_priority_over_ip")

    @faultcore.fault()
    def call_hostname_priority(message: str) -> str:
        return http_echo(hostname, port, message)

    avg_hostname_priority = measure_ms(call_hostname_priority)
    print(f"http precedence hostname>ip avg latency: {avg_hostname_priority:.2f}ms")
    assert_match_latency(avg_hostname_priority, baseline_ms, "http precedence hostname>ip")

    faultcore.register_policy(
        "targets_http_hostname_tie_with_ip",
        latency=MATCH_LATENCY,
        targets=[
            {"target": f"tcp://{ip_host}:{port}", "priority": 200},
            {"hostname": hostname, "port": port, "protocol": "tcp", "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_http_hostname_tie_with_ip")

    @faultcore.fault()
    def call_tie(message: str) -> str:
        return http_echo(hostname, port, message)

    avg_tie = measure_ms(call_tie)
    print(f"http precedence tie ip/hostname avg latency: {avg_tie:.2f}ms")
    assert_match_latency(avg_tie, baseline_ms, "http precedence tie ip/hostname")


def run_fallback_when_higher_priority_rule_does_not_match(
    hostname: str, ip_host: str, port: int, baseline_ms: float
) -> None:
    faultcore.register_policy(
        "targets_http_fallback_hostname_lower_priority",
        latency=MATCH_LATENCY,
        targets=[
            {"target": "tcp://10.255.255.1:1", "priority": 300},
            {"hostname": hostname, "port": port, "protocol": "tcp", "priority": 100},
        ],
    )

    faultcore.set_thread_policy("targets_http_fallback_hostname_lower_priority")

    @faultcore.fault()
    def call_hostname_fallback(message: str) -> str:
        return http_echo(hostname, port, message)

    avg_hostname_fallback = measure_ms(call_hostname_fallback)
    print(f"http fallback to hostname avg latency: {avg_hostname_fallback:.2f}ms")
    assert_match_latency(avg_hostname_fallback, baseline_ms, "http fallback hostname")

    faultcore.register_policy(
        "targets_http_fallback_ip_lower_priority",
        latency=MATCH_LATENCY,
        targets=[
            {"hostname": "other.localhost", "port": port, "protocol": "tcp", "priority": 300},
            {"target": f"tcp://{ip_host}:{port}", "priority": 100},
        ],
    )

    faultcore.set_thread_policy("targets_http_fallback_ip_lower_priority")

    @faultcore.fault()
    def call_ip_fallback(message: str) -> str:
        return http_echo(hostname, port, message)

    avg_ip_fallback = measure_ms(call_ip_fallback)
    print(f"http fallback to ip avg latency: {avg_ip_fallback:.2f}ms")
    assert_match_latency(avg_ip_fallback, baseline_ms, "http fallback ip")


def run_no_match_case(hostname: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_http_no_match",
        latency=MATCH_LATENCY,
        targets=[
            {"target": "tcp://10.255.255.1:1", "priority": 300},
            {"hostname": "other.localhost", "port": port, "protocol": "tcp", "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_http_no_match")

    @faultcore.fault()
    def call(message: str) -> str:
        return http_echo(hostname, port, message)

    avg = measure_ms(call)
    print(f"http no-match avg latency: {avg:.2f}ms")
    assert_no_match_latency(avg, baseline_ms, "http no-match")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore HTTP hostname/IP precedence integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="server IP used in IP target rules")
    parser.add_argument("--port", type=int, default=9000, help="compat arg (unused by HTTP probe runner)")
    parser.add_argument(
        "--http-port",
        type=int,
        default=int(os.environ.get("HTTP_SERVER_PORT", "8000")),
        help="HTTP server port",
    )
    parser.add_argument("--target-hostname", default="localhost", help="hostname used for client and hostname rules")
    parser.add_argument("--mode", choices=["match", "no-match", "all"], default="all")
    args = parser.parse_args()

    print(
        f"[{datetime.now().isoformat()}] targets HTTP/hostname integration mode={args.mode} "
        f"ip_host={args.host} target_hostname={args.target_hostname} http_port={args.http_port}"
    )
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    try:
        baseline_ms = run_baseline_case(args.target_hostname, args.http_port)
        if args.mode in {"match", "all"}:
            run_hostname_exact_case(args.target_hostname, args.http_port, baseline_ms)
            run_ip_vs_hostname_precedence_cases(args.target_hostname, args.host, args.http_port, baseline_ms)
            run_fallback_when_higher_priority_rule_does_not_match(
                args.target_hostname, args.host, args.http_port, baseline_ms
            )
        if args.mode in {"no-match", "all"}:
            run_no_match_case(args.target_hostname, args.http_port, baseline_ms)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("targets HTTP/hostname integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
