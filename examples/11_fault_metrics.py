#!/usr/bin/env python3
import socket
import time

import faultcore


def tcp_echo(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(f"{message}\n".encode())
        response = sock.recv(1024)
        return response.decode().strip()
    finally:
        sock.close()


def print_totals(label: str, data: dict) -> None:
    totals = data.get("totals", {})
    print(f"{label}: {totals}")


def run_demo(host: str, port: int) -> None:
    faultcore.register_policy("metrics_demo", latency_ms=120)

    @faultcore.apply_policy("metrics_demo")
    def call_once(tag: str) -> str:
        return tcp_echo(host, port, f"metrics-{tag}")

    global_before = faultcore.get_fault_metrics()
    print_totals("global before", global_before)

    with faultcore.fault_context("metrics_demo"):
        ctx_before = faultcore.get_fault_metrics(scope="context")
        print_totals("context before", ctx_before)

        started = time.time()
        resp = call_once("a")
        elapsed_ms = (time.time() - started) * 1000

        ctx_after = faultcore.get_fault_metrics(scope="context")
        print(f"response: {resp}")
        print(f"elapsed: {elapsed_ms:.1f}ms")
        print_totals("context after", ctx_after)

    global_after = faultcore.get_fault_metrics()
    print_totals("global after", global_after)


if __name__ == "__main__":
    print("=" * 60)
    print(" Fault Metrics Example ".center(60, "="))
    print("=" * 60)
    run_demo("127.0.0.1", 9000)
    print("\nStart TCP server first:")
    print("  python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Run with interceptor:")
    print("  examples/run_with_preload.sh 11_fault_metrics.py")
