#!/usr/bin/env python3
import argparse
import errno
import os
import socket
import sys
import threading
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


def _budget_payload(action: str) -> dict[str, object]:
    payload: dict[str, object] = {"max_ops": 1, "action": action}
    if action == "timeout":
        payload["budget_timeout_ms"] = 15
    if action == "connection_error":
        payload["error"] = "reset"
    return payload


def run_tcp_case(host: str, port: int, action: str, expected_errno: int) -> None:
    policy = f"session_budget_tcp_{action}"
    faultcore.register_policy(policy, session_budget=_budget_payload(action))

    @faultcore.apply_policy(policy)
    def tcp_probe() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((host, port))
            sent = sock.send(b"budget-tcp-1\n")
            if sent <= 0:
                raise RuntimeError("tcp first send did not send bytes")
            try:
                sock.send(b"budget-tcp-2\n")
            except OSError as exc:
                if exc.errno != expected_errno:
                    raise RuntimeError(
                        f"tcp action={action} expected errno={expected_errno}, got errno={exc.errno}"
                    ) from exc
                return
            raise RuntimeError(f"tcp action={action} expected an OSError on second send")
        finally:
            sock.close()

    started = time.perf_counter()
    tcp_probe()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"tcp action={action}: PASS ({elapsed_ms:.2f}ms)")


def run_udp_case(host: str, action: str, expected_errno: int) -> None:
    policy = f"session_budget_udp_{action}"
    faultcore.register_policy(policy, session_budget=_budget_payload(action))

    @faultcore.apply_policy(policy)
    def udp_probe() -> None:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.bind((host, 0))
        client.settimeout(2.0)
        client_port = client.getsockname()[1]

        def sender() -> None:
            tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                tx.sendto(b"budget-udp-1", (host, client_port))
                time.sleep(0.05)
                tx.sendto(b"budget-udp-2", (host, client_port))
            finally:
                tx.close()

        thread = threading.Thread(target=sender)
        thread.start()
        try:
            first, _ = client.recvfrom(64)
            if first != b"budget-udp-1":
                raise RuntimeError(f"udp first packet mismatch: {first!r}")
            try:
                client.recvfrom(64)
            except OSError as exc:
                if exc.errno != expected_errno:
                    raise RuntimeError(
                        f"udp action={action} expected errno={expected_errno}, got errno={exc.errno}"
                    ) from exc
                return
            raise RuntimeError(f"udp action={action} expected an OSError on second recvfrom")
        finally:
            thread.join(timeout=1.0)
            client.close()

    started = time.perf_counter()
    udp_probe()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"udp action={action}: PASS ({elapsed_ms:.2f}ms)")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore session_budget integration (TCP/UDP)")
    parser.add_argument("--host", default="127.0.0.1", help="host for probes")
    parser.add_argument("--port", type=int, default=9000, help="TCP echo server port")
    parser.add_argument("--mode", choices=["drop", "timeout", "connection_error", "all"], default="all")
    args = parser.parse_args()

    print(
        f"[{datetime.now().isoformat()}] session_budget integration mode={args.mode} host={args.host} port={args.port}"
    )
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    cases = []
    if args.mode in {"drop", "all"}:
        cases.append(("drop", errno.EIO))
    if args.mode in {"timeout", "all"}:
        cases.append(("timeout", errno.ETIMEDOUT))
    if args.mode in {"connection_error", "all"}:
        cases.append(("connection_error", errno.ECONNRESET))

    try:
        for action, expected_errno in cases:
            run_tcp_case(args.host, args.port, action, expected_errno)
            run_udp_case(args.host, action, expected_errno)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("session_budget integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
