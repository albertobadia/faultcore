#!/usr/bin/env python3
import socket
import time

import faultcore


def tcp_echo(host: str, port: int, message: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(message.encode())
        response = sock.recv(1024)
        return response.decode().strip()
    finally:
        sock.close()


def build_policy() -> None:
    faultcore.register_policy(
        "target_priority_demo",
        latency="150ms",
        targets=[
            {"target": "tcp://10.0.0.0/8:9000", "priority": 10},
            {"target": "tcp://127.0.0.1:9000", "priority": 200},
        ],
    )


def run_demo(host: str, port: int) -> None:
    build_policy()

    policy = faultcore.get_policy("target_priority_demo")
    print("Policy targets (already ordered by priority desc):")
    for idx, rule in enumerate(policy.get("target_profiles", []), start=1):
        print(
            f"  {idx}. priority={rule.get('priority')} "
            f"kind={rule.get('kind')} ip={rule.get('ipv4')} "
            f"port={rule.get('port')} protocol={rule.get('protocol')}"
        )

    @faultcore.fault("target_priority_demo")
    def call_echo() -> str:
        return tcp_echo(host, port, "target-priority")

    start = time.time()
    response = call_echo()
    elapsed_ms = (time.time() - start) * 1000

    print(f"\nResponse: {response}")
    print(f"Elapsed: {elapsed_ms:.1f}ms")
    print("Expected: with matching target, elapsed should include ~150ms policy latency.")


if __name__ == "__main__":
    print("=" * 60)
    print(" Target Priority Example ".center(60, "="))
    print("=" * 60)
    run_demo("127.0.0.1", 9000)
    print("\nStart TCP server first:")
    print("  uv run python tests/integration/servers/tcp_echo_server.py --port 9000")
    print("Run with interceptor (from project root):")
    print("  examples/run_with_preload.sh 10_target_priority.py")
