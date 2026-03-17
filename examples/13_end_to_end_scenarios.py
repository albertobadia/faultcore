#!/usr/bin/env python3
import argparse
import socket
import time

import faultcore

try:
    import requests
except ImportError:
    requests = None


def tcp_echo(host: str, port: int, payload: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(f"{payload}\n".encode())
        return sock.recv(4096).decode().strip()
    finally:
        sock.close()


def udp_echo(host: str, port: int, payload: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        sock.sendto(payload.encode(), (host, port))
        data, _ = sock.recvfrom(4096)
        return data.decode().strip()
    finally:
        sock.close()


def http_echo(base_url: str, payload: str) -> int:
    if requests is None:
        raise RuntimeError("requests is not installed")
    resp = requests.get(f"{base_url}/echo/{payload}", timeout=5)
    resp.raise_for_status()
    return resp.status_code


def resolve_once(host: str, port: int) -> int:
    return len(socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM))


def run_tcp_scenario(host: str, port: int) -> None:
    faultcore.register_policy("e2e_tcp", latency="120ms")

    @faultcore.fault("e2e_tcp")
    def call() -> str:
        return tcp_echo(host, port, "e2e-tcp")

    started = time.perf_counter()
    response = call()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"tcp: response={response!r} elapsed_ms={elapsed_ms:.1f}")


def run_udp_scenario(host: str, port: int) -> None:
    faultcore.register_policy("e2e_udp", downlink={"jitter": "5ms"})

    @faultcore.fault("e2e_udp")
    def call() -> str:
        return udp_echo(host, port, "e2e-udp")

    started = time.perf_counter()
    response = call()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"udp: response={response!r} elapsed_ms={elapsed_ms:.1f}")


def run_http_scenario(base_url: str) -> None:
    if requests is None:
        print("http: skipped (requests not installed)")
        return

    faultcore.register_policy("e2e_http", latency="80ms")

    @faultcore.fault("e2e_http")
    def call() -> int:
        return http_echo(base_url, "e2e-http")

    started = time.perf_counter()
    status = call()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"http: status={status} elapsed_ms={elapsed_ms:.1f}")


def run_dns_scenario(host: str, port: int) -> None:
    faultcore.register_policy("e2e_dns", dns={"delay": "150ms"})

    @faultcore.fault("e2e_dns")
    def call() -> int:
        return resolve_once(host, port)

    started = time.perf_counter()
    records = call()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"dns: records={records} elapsed_ms={elapsed_ms:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore end-to-end scenarios (TCP/UDP/HTTP/DNS)")
    parser.add_argument("--tcp-host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=9000)
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=9001)
    parser.add_argument("--http-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dns-host", default="localhost")
    parser.add_argument("--dns-port", type=int, default=80)
    args = parser.parse_args()

    print("=" * 60)
    print(" End-to-End Scenarios ".center(60, "="))
    print("=" * 60)

    run_tcp_scenario(args.tcp_host, args.tcp_port)
    run_udp_scenario(args.udp_host, args.udp_port)
    run_http_scenario(args.http_url)
    run_dns_scenario(args.dns_host, args.dns_port)

    print("done: tcp/udp/http/dns scenarios executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
