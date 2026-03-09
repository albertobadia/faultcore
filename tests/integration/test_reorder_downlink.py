#!/usr/bin/env python3
import argparse
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


def start_tcp_push_server(host: str) -> tuple[int, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, 0))
    server.listen(1)
    port = server.getsockname()[1]

    def run() -> None:
        conn = None
        try:
            conn, _ = server.accept()
            conn.sendall(b"pkt00001")
            conn.sendall(b"pkt00002")
        finally:
            if conn is not None:
                conn.close()
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, thread


def start_udp_push_sender(host: str, client_port: int) -> threading.Thread:
    def run() -> None:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            time.sleep(0.05)
            sender.sendto(b"dat00001", (host, client_port))
            sender.sendto(b"dat00002", (host, client_port))
        finally:
            sender.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@faultcore.packet_reorder(prob="100%", max_delay_ms=100, window=2)
def recv_two_tcp(sock: socket.socket) -> tuple[bytes, bytes]:
    return sock.recv(8), sock.recv(8)


@faultcore.packet_reorder(prob="100%", max_delay_ms=100, window=2)
def recv_two_udp(sock: socket.socket) -> tuple[bytes, bytes]:
    first, _ = sock.recvfrom(64)
    second, _ = sock.recvfrom(64)
    return first, second


def run_tcp_case(host: str) -> None:
    port, _ = start_tcp_push_server(host)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(None)
    try:
        sock.connect((host, port))
        out1, out2 = recv_two_tcp(sock)
    finally:
        sock.close()

    print(f"tcp recv order: {out1!r} then {out2!r}")
    if out1 != b"pkt00002" or out2 != b"pkt00001":
        raise RuntimeError("tcp recv reorder failed: expected swapped order")


def run_udp_case(host: str) -> None:
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.bind((host, 0))
    client.settimeout(None)
    try:
        client_port = client.getsockname()[1]
        _ = start_udp_push_sender(host, client_port)
        out1, out2 = recv_two_udp(client)
    finally:
        client.close()

    print(f"udp recvfrom order: {out1!r} then {out2!r}")
    if out1 != b"dat00002" or out2 != b"dat00001":
        raise RuntimeError("udp recvfrom reorder failed: expected swapped order")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore downlink reorder integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="bind host for local test servers")
    parser.add_argument("--port", type=int, default=9000, help="unused, kept for integration runner compatibility")
    parser.add_argument("--mode", choices=["tcp", "udp", "all"], default="all")
    args = parser.parse_args()

    print(f"[{datetime.now().isoformat()}] reorder downlink integration mode={args.mode} host={args.host}")
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    try:
        if args.mode in {"tcp", "all"}:
            run_tcp_case(args.host)
        if args.mode in {"udp", "all"}:
            run_udp_case(args.host)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print("reorder downlink integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
