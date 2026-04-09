#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
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


def _resolve(host: str, port: int, socktype: int) -> tuple[int, tuple]:
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socktype)
    family, _, _, _, sockaddr = infos[0]
    return family, sockaddr


def tcp_echo(host: str, port: int, message: str) -> str:
    family, sockaddr = _resolve(host, port, socket.SOCK_STREAM)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(sockaddr)
        sock.sendall(f"{message}\n".encode())
        data = sock.recv(4096)
        return data.decode("utf-8").strip()


def udp_echo(host: str, port: int, message: str) -> str:
    family, sockaddr = _resolve(host, port, socket.SOCK_DGRAM)
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(f"{message}\n".encode(), sockaddr)
        data, _ = sock.recvfrom(4096)
        return data.decode("utf-8").strip()


def measure_ms(callable_fn: Callable[[str], str], count: int = 3) -> float:
    samples: list[float] = []
    for idx in range(count):
        started = time.perf_counter()
        response = callable_fn(f"target-ipv6-{idx}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not response.startswith("ECHO:"):
            raise RuntimeError(f"unexpected echo response: {response}")
        samples.append(elapsed_ms)
    return sum(samples) / len(samples)


class TcpEchoServer:
    def __init__(self, host: str):
        self.host = host
        self.family = socket.AF_INET6 if ":" in host else socket.AF_INET
        self._server: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        self._server = socket.socket(self.family, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.family == socket.AF_INET6:
            self._server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        self._server.bind((self.host, 0))
        self._server.listen(16)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            self._server.settimeout(0.5)
            try:
                client, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
            thread.start()

    @staticmethod
    def _handle_client(client: socket.socket) -> None:
        with client:
            while True:
                data = client.recv(4096)
                if not data:
                    return
                message = data.decode("utf-8").strip()
                client.sendall(f"ECHO: {message}\n".encode())

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            with suppress(OSError):
                self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class UdpEchoServer:
    def __init__(self, host: str):
        self.host = host
        self.family = socket.AF_INET6 if ":" in host else socket.AF_INET
        self._server: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        self._server = socket.socket(self.family, socket.SOCK_DGRAM)
        if self.family == socket.AF_INET6:
            self._server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        self._server.bind((self.host, 0))
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            self._server.settimeout(0.5)
            try:
                data, addr = self._server.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            message = data.decode("utf-8").strip()
            with suppress(OSError):
                self._server.sendto(f"ECHO: {message}\n".encode(), addr)

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            with suppress(OSError):
                self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def assert_match_latency(avg_ms: float, label: str) -> None:
    print(f"{label} avg latency: {avg_ms:.2f}ms")
    if avg_ms < 120:
        raise RuntimeError(f"{label}: expected latency >= 120ms, got {avg_ms:.2f}ms")


def run_tcp_ipv6_host_case(host_v6: str, tcp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_ipv6_tcp_host",
        latency="180ms",
        targets=[
            {"target": f"tcp://[{host_v6}]:{tcp_port_v6}", "priority": 200},
            {"target": "tcp://127.0.0.0/8", "port": 65530, "priority": 10},
        ],
    )

    faultcore.set_thread_policy("targets_ipv6_tcp_host")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host_v6, tcp_port_v6, message)

    assert_match_latency(measure_ms(call, count=3), "ipv6 tcp host match")


def run_tcp_ipv6_cidr_case(host_v6: str, tcp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_ipv6_tcp_cidr",
        latency="180ms",
        targets=[{"target": "::1/128", "port": tcp_port_v6, "protocol": "tcp", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_ipv6_tcp_cidr")

    @faultcore.fault()
    def call(message: str) -> str:
        return tcp_echo(host_v6, tcp_port_v6, message)

    assert_match_latency(measure_ms(call, count=3), "ipv6 tcp cidr match")


def run_udp_ipv6_host_case(host_v6: str, udp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_ipv6_udp_host",
        latency="180ms",
        targets=[{"target": f"udp://[{host_v6}]:{udp_port_v6}", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_ipv6_udp_host")

    @faultcore.fault()
    def call(message: str) -> str:
        return udp_echo(host_v6, udp_port_v6, message)

    assert_match_latency(measure_ms(call, count=3), "ipv6 udp host match")


def run_udp_ipv6_cidr_case(host_v6: str, udp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_ipv6_udp_cidr",
        latency="180ms",
        targets=[{"target": "::1/128", "port": udp_port_v6, "protocol": "udp", "priority": 200}],
    )

    faultcore.set_thread_policy("targets_ipv6_udp_cidr")

    @faultcore.fault()
    def call(message: str) -> str:
        return udp_echo(host_v6, udp_port_v6, message)

    assert_match_latency(measure_ms(call, count=3), "ipv6 udp cidr match")


def run_mixed_ipv4_ipv6_case(host_v4: str, tcp_port_v4: int, host_v6: str, tcp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_mixed_tcp_families",
        latency="180ms",
        targets=[
            {"target": "tcp://127.0.0.0/8", "port": tcp_port_v4, "priority": 200},
            {"target": "::1/128", "port": tcp_port_v6, "protocol": "tcp", "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_mixed_tcp_families")

    @faultcore.fault()
    def call_v4(message: str) -> str:
        return tcp_echo(host_v4, tcp_port_v4, message)

    @faultcore.fault()
    def call_v6(message: str) -> str:
        return tcp_echo(host_v6, tcp_port_v6, message)

    assert_match_latency(measure_ms(call_v4, count=3), "mixed tcp ipv4")
    assert_match_latency(measure_ms(call_v6, count=3), "mixed tcp ipv6")


def run_mixed_udp_ipv4_ipv6_case(host_v4: str, udp_port_v4: int, host_v6: str, udp_port_v6: int) -> None:
    faultcore.register_policy(
        "targets_mixed_udp_families",
        latency="180ms",
        targets=[
            {"target": "udp://127.0.0.0/8", "port": udp_port_v4, "priority": 200},
            {"target": "::1/128", "port": udp_port_v6, "protocol": "udp", "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_mixed_udp_families")

    @faultcore.fault()
    def call_v4(message: str) -> str:
        return udp_echo(host_v4, udp_port_v4, message)

    @faultcore.fault()
    def call_v6(message: str) -> str:
        return udp_echo(host_v6, udp_port_v6, message)

    assert_match_latency(measure_ms(call_v4, count=3), "mixed udp ipv4")
    assert_match_latency(measure_ms(call_v6, count=3), "mixed udp ipv6")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore IPv6 + mixed targets integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="unused; accepted for tests.sh compatibility")
    parser.add_argument("--port", type=int, default=9000, help="unused; accepted for tests.sh compatibility")
    parser.add_argument("--mode", choices=["all"], default="all")
    args = parser.parse_args()

    del args
    print(f"[{datetime.now().isoformat()}] targets IPv6/mixed integration mode=all")
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    tcp_v4 = TcpEchoServer("127.0.0.1")
    tcp_v6 = TcpEchoServer("::1")
    udp_v4 = UdpEchoServer("127.0.0.1")
    udp_v6 = UdpEchoServer("::1")
    try:
        tcp_v4.start()
        tcp_v6.start()
        udp_v4.start()
        udp_v6.start()

        run_tcp_ipv6_host_case("::1", tcp_v6.port)
        run_tcp_ipv6_cidr_case("::1", tcp_v6.port)
        run_udp_ipv6_host_case("::1", udp_v6.port)
        run_udp_ipv6_cidr_case("::1", udp_v6.port)
        run_mixed_ipv4_ipv6_case("127.0.0.1", tcp_v4.port, "::1", tcp_v6.port)
        run_mixed_udp_ipv4_ipv6_case("127.0.0.1", udp_v4.port, "::1", udp_v6.port)
    except OSError as exc:
        print(f"ERROR: IPv6 socket setup failed: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1
    finally:
        tcp_v4.stop()
        tcp_v6.stop()
        udp_v4.stop()
        udp_v6.stop()

    print("targets IPv6/mixed integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
