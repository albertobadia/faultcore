#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import time
from datetime import datetime

import faultcore
from faultcore.shm_writer import SHM_SIZE

DNS_TIMEOUT_MS = 80
DNS_TIMEOUT = f"{DNS_TIMEOUT_MS}ms"
NO_MATCH_MAX_MS = 120.0
MATCH_MIN_MS = 60.0


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


def resolve_ms(hostname: str, port: int) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ok = True
    except socket.gaierror:
        ok = False
    elapsed_ms = (time.perf_counter() - started) * 1000
    return ok, elapsed_ms


def assert_dns_ok(elapsed_ms: float, label: str) -> None:
    print(f"{label}: ok ({elapsed_ms:.2f}ms)")
    if elapsed_ms > NO_MATCH_MAX_MS:
        raise RuntimeError(f"{label}: expected <= {NO_MATCH_MAX_MS:.0f}ms, got {elapsed_ms:.2f}ms")


def assert_dns_timeout(elapsed_ms: float, label: str) -> None:
    print(f"{label}: timeout ({elapsed_ms:.2f}ms)")
    if elapsed_ms < MATCH_MIN_MS:
        raise RuntimeError(f"{label}: expected >= {MATCH_MIN_MS:.0f}ms, got {elapsed_ms:.2f}ms")


def run_hostname_no_match_case(port: int) -> None:
    faultcore.register_policy(
        "targets_dns_hostname_no_match",
        dns={"timeout": DNS_TIMEOUT},
        targets=[{"hostname": "nomatch.localhost", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_dns_hostname_no_match")

    @faultcore.fault()
    def resolve() -> tuple[bool, float]:
        return resolve_ms("localhost", port)

    ok, elapsed_ms = resolve()
    if not ok:
        raise RuntimeError("hostname no-match should not timeout")
    assert_dns_ok(elapsed_ms, "dns hostname no-match")


def run_hostname_exact_case(port: int) -> None:
    faultcore.register_policy(
        "targets_dns_hostname_exact",
        dns={"timeout": DNS_TIMEOUT},
        targets=[{"hostname": "localhost", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_dns_hostname_exact")

    @faultcore.fault()
    def resolve() -> tuple[bool, float]:
        return resolve_ms("localhost", port)

    ok, elapsed_ms = resolve()
    if ok:
        raise RuntimeError("hostname exact should timeout DNS resolution")
    assert_dns_timeout(elapsed_ms, "dns hostname exact")


def run_ip_vs_hostname_priority_cases(port: int) -> None:
    faultcore.register_policy(
        "targets_dns_ip_priority_over_hostname",
        dns={"timeout": DNS_TIMEOUT},
        targets=[
            {"target": "127.0.0.1", "priority": 300},
            {"hostname": "localhost", "priority": 100},
        ],
    )

    faultcore.set_thread_policy("targets_dns_ip_priority_over_hostname")

    @faultcore.fault()
    def resolve_ip_priority() -> tuple[bool, float]:
        return resolve_ms("localhost", port)

    ok, elapsed_ms = resolve_ip_priority()
    if ok:
        raise RuntimeError("ip>hostname priority case should still timeout via hostname DNS match")
    assert_dns_timeout(elapsed_ms, "dns precedence ip>hostname priority")

    faultcore.register_policy(
        "targets_dns_hostname_priority_over_ip",
        dns={"timeout": DNS_TIMEOUT},
        targets=[
            {"target": "127.0.0.1", "priority": 100},
            {"hostname": "localhost", "priority": 300},
        ],
    )

    faultcore.set_thread_policy("targets_dns_hostname_priority_over_ip")

    @faultcore.fault()
    def resolve_hostname_priority() -> tuple[bool, float]:
        return resolve_ms("localhost", port)

    ok, elapsed_ms = resolve_hostname_priority()
    if ok:
        raise RuntimeError("hostname>ip priority case should timeout via hostname DNS match")
    assert_dns_timeout(elapsed_ms, "dns precedence hostname>ip priority")


def run_ip_vs_hostname_tie_case(port: int) -> None:
    faultcore.register_policy(
        "targets_dns_hostname_tie_with_ip",
        dns={"timeout": DNS_TIMEOUT},
        targets=[
            {"target": "127.0.0.1", "priority": 200},
            {"hostname": "localhost", "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_dns_hostname_tie_with_ip")

    @faultcore.fault()
    def resolve_tie() -> tuple[bool, float]:
        return resolve_ms("localhost", port)

    ok, elapsed_ms = resolve_tie()
    if ok:
        raise RuntimeError("ip/hostname tie case should timeout via hostname DNS match")
    assert_dns_timeout(elapsed_ms, "dns precedence tie ip/hostname")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore DNS hostname targets integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="unused; accepted for tests.sh compatibility")
    parser.add_argument("--port", type=int, default=9000, help="unused; accepted for tests.sh compatibility")
    parser.add_argument("--mode", choices=["all"], default="all")
    args = parser.parse_args()

    print(f"[{datetime.now().isoformat()}] targets DNS/hostname integration mode={args.mode}")
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    try:
        run_hostname_no_match_case(args.port)
        run_hostname_exact_case(args.port)
        run_ip_vs_hostname_priority_cases(args.port)
        run_ip_vs_hostname_tie_case(args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("targets DNS/hostname integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
