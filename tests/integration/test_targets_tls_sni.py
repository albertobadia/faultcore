#!/usr/bin/env python3
import argparse
import os
import shutil
import socket
import ssl
import sys
import tempfile
import threading
import time
from contextlib import suppress
from datetime import datetime

import faultcore
from faultcore.shm_writer import SHM_SIZE

TEST_LATENCY_MS = 25
TEST_LATENCY = f"{TEST_LATENCY_MS}ms"
MEASURE_COUNT = 2
NO_MATCH_MAX_MS = 250.0
MATCH_MIN_DELTA_MS = 200.0

CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDCTCCAfGgAwIBAgIUMS/KaDsMi/XVuzdqAT/c2lWMkvowDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI2MDMxMTAyNTIxMloXDTM2MDMw
ODAyNTIxMlowFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEAsNXagfuUOHh+c2vOeAS4hyiuMaLtRfvvhCH7RhSV/K8G
EXHFCiBJQ6GWfBqIqUmUAetufkyxdbazP0v23d0pN4/EUPNh+znoI50hQ7nb2pew
sT+9p2z+WcPIcRGuKBWkGvwo5Edm1QDLb+md2asM36t6pRH+uzAebmnS2If75107
j4pgSi9nj8irFrJWUgvqk2rT8wtjKURaRXhTh91wr+h1OJIh8/wBtAWoNGXaz0sK
JKgCJ+bPW7HgARwzVusNIzkvkAaMYhdW33tPszHP8dAL+AnP/JSqjgT0DTSQ8baZ
pnS9gZ5uEz2PcMF6V6e8mZ0IBoE7OAbgpr3Grs3vTQIDAQABo1MwUTAdBgNVHQ4E
FgQUA+nWloQBhE2mtfmVzD7g8870B5YwHwYDVR0jBBgwFoAUA+nWloQBhE2mtfmV
zD7g8870B5YwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAN8TH
EHFeMMBbPmwREDmYNu9gY/A/Z2G6puM4TPw5hyvk+lg9bo5/Z2XxvfTp+JdmEmq0
XIAz3W8R5j5yEwXKnBYzfficoMO9M2ckBmJteI2xScZc5O0XV/+sjWwhIUdygVWg
T/w0nC6sSLzHSJhdQBTPxa8HXDwtDYuG5l51/m2ZqxvE9NQ9TYBVzhzK88oXEaEJ
WDOEQIDHEVrcHwaRslpousb9VjYShgkeinOyOKAFIGQCRsmalZN1B1sY51JW7oGt
h9a2Vrlat5CjkgMzldI3HzMFVNpwkINLoMnj3TNbgvzvVGjpi45/AintqIqZq0Kf
iV5woYKkTcHKftMpHg==
-----END CERTIFICATE-----
"""

KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCw1dqB+5Q4eH5z
a854BLiHKK4xou1F+++EIftGFJX8rwYRccUKIElDoZZ8GoipSZQB625+TLF1trM/
S/bd3Sk3j8RQ82H7OegjnSFDudval7CxP72nbP5Zw8hxEa4oFaQa/CjkR2bVAMtv
6Z3Zqwzfq3qlEf67MB5uadLYh/vnXTuPimBKL2ePyKsWslZSC+qTatPzC2MpRFpF
eFOH3XCv6HU4kiHz/AG0Bag0ZdrPSwokqAIn5s9bseABHDNW6w0jOS+QBoxiF1bf
e0+zMc/x0Av4Cc/8lKqOBPQNNJDxtpmmdL2Bnm4TPY9wwXpXp7yZnQgGgTs4BuCm
vcauze9NAgMBAAECggEAAPLSk7GlTUmTX0OFgcv3Wjktkkmno8N1/RqWF5ckAtFv
Yxj3mFYcIbHfD4EWzE3uIaTFchbJOW5ZyDAAl3S7xUPKwKbOn2fBYK3tJ40+zHP3
tg/zIb7XDiloWYA/YJEh8zaSYVAnZpYGCd1v7pX3B6VxF3AczkdNmOJrfyzn0kUB
y8HuPOwijlEc7Vs01TeiPqIb7j9m7/VhxTDvd+PvceyUUbm7mYD2+lU52TMkzv0H
ItAaqoJotu/lV+y5ldhVa+hmYxt1l57i05tXEpOwthuQhKnNuYYpytkDqft6rThb
Ahos0HuoL8t0d8TMY3ByjWvK7fuHxsI9dsfUB4YKYQKBgQDp5tCIzWOpkJsuhPe6
SVq5kJGnNiRE5aNuLLTPrtRteuDMPi90WAKd9ZZyRoagN9/HgvMsWd5ynmnUN1QZ
lLymN/nE6PmkCALIsEn52rK1XnqbHc7hYbOPFZkHCziNFLaIYc2KzS3V6M9c0HaZ
rQqXU59elCWP7OpZksVqq0VwhQKBgQDBitMXMalP8k98z2LjlAdFyjmeqnRb2m7G
MwyJzPGcPVBnXDkHZg/bZSZNpqfs3XLwBQ6w2Vanl8s3Rfgh/DU/XqIxk+NfxfK7
EsRhtByU68ihFxIcZBmt73WaVLSB+Gg7wVb1WEo9AE7WgtLMTAOKvWnRISPeDzz9
klM8fexiKQKBgF4xbVkqHTBz44pgUcLbN4XzCjTkQMbeE2qS5l2ccj+EdHLLuCCK
MMOb2vI6JIzw81VNDtCVgFd4I/YqMdv7Yd0uPY9mouHDuBtJowDTaZRQb993qZBp
3/2HHRERG7z00m0ptbRn3EWAc8FU0e4hGVrHei6ESnwjVFyuFoJWZqhhAoGBAKKX
DV6eya3v0fb4AgtNgA6RJHa2m6nOhuDaYd4h3ZdzqugqAX7FruyQvOze5JOINdaN
aRoIe1OvoXh9v0ZNqi3iQj+EDa+Xi6K80V2DAb/ZlGJAD2bqcOg+En3kSwAkvuv0
MClMUpGMgK6UmKIn+ZHELfER9h/GjWY4VtSqtLqBAoGBAOQOSL0EZ9uqOs3zJgJp
T/y/l9wJVN5lkingvA+rAdyX6ZkKS05LOzYrzUcPikv5GBnaZHa3o10EEn/vxYNc
KlSRpEZiCLEFGfYrqeg4yob5t35nMdB65nAm2GREdX8C6h8YrQO5FXUOlp7xdbjU
sJcrBJhQX/YNwTb54Xex0YJU
-----END PRIVATE KEY-----
"""


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


class TlsEchoServer:
    def __init__(self, host: str):
        self.host = host
        self.port = 0
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._tmpdir: str | None = None
        self._sni_seen: list[str] = []
        self._sni_lock = threading.Lock()

    def start(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="faultcore_tls_")
        cert_path = os.path.join(self._tmpdir, "cert.pem")
        key_path = os.path.join(self._tmpdir, "key.pem")
        with open(cert_path, "w", encoding="utf-8") as cert_file:
            cert_file.write(CERT_PEM)
        with open(key_path, "w", encoding="utf-8") as key_file:
            key_file.write(KEY_PEM)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)

        def sni_callback(
            _ssl_sock: ssl.SSLSocket,
            server_name: str | bytes | None,
            _ctx: ssl.SSLContext,
        ) -> None:
            try:
                if server_name is None:
                    return
                if isinstance(server_name, bytes):
                    normalized = server_name.decode("idna", errors="ignore").strip().rstrip(".").lower()
                else:
                    normalized = server_name.strip().rstrip(".").lower()
                if not normalized:
                    return
                with self._sni_lock:
                    self._sni_seen.append(normalized)
            except Exception:
                return

        context.set_servername_callback(sni_callback)

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, 0))
        self._server.listen(32)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._run, args=(context,), daemon=True)
        self._thread.start()

    def _run(self, context: ssl.SSLContext) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            self._server.settimeout(0.5)
            try:
                conn, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            worker = threading.Thread(target=self._handle_client, args=(context, conn), daemon=True)
            worker.start()

    @staticmethod
    def _handle_client(context: ssl.SSLContext, conn: socket.socket) -> None:
        with conn:
            try:
                tls_conn = context.wrap_socket(conn, server_side=True)
            except ssl.SSLError:
                return
            with tls_conn:
                try:
                    data = tls_conn.recv(4096)
                    if not data:
                        return
                    message = data.decode("utf-8").strip()
                    tls_conn.sendall(f"ECHO: {message}\n".encode())
                except OSError:
                    return

    def sni_count(self) -> int:
        with self._sni_lock:
            return len(self._sni_seen)

    def sni_since(self, start_idx: int) -> list[str]:
        with self._sni_lock:
            return list(self._sni_seen[start_idx:])

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            with suppress(OSError):
                self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir, ignore_errors=True)


def tls_echo(host: str, port: int, message: str, server_hostname: str) -> str:
    client_ctx = ssl.create_default_context()
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection((host, port), timeout=5) as raw,
        client_ctx.wrap_socket(raw, server_hostname=server_hostname) as tls_sock,
    ):
        tls_sock.sendall(f"{message}\n".encode())
        data = tls_sock.recv(4096)
        return data.decode("utf-8").strip()


def measure_ms(callable_fn, count: int = MEASURE_COUNT) -> float:
    samples = []
    for idx in range(count):
        started = time.perf_counter()
        response = callable_fn(f"target-tls-sni-{idx}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not response.startswith("ECHO:"):
            raise RuntimeError(f"unexpected echo response: {response}")
        samples.append(elapsed_ms)
    return sum(samples) / len(samples)


def assert_match_latency(avg_ms: float, baseline_ms: float, label: str) -> None:
    print(f"{label} avg latency: {avg_ms:.2f}ms (baseline no-match: {baseline_ms:.2f}ms)")
    if avg_ms < (baseline_ms + MATCH_MIN_DELTA_MS):
        raise RuntimeError(
            f"{label}: expected latency >= baseline + {MATCH_MIN_DELTA_MS:.0f}ms, "
            f"got avg={avg_ms:.2f}ms baseline={baseline_ms:.2f}ms"
        )


def assert_no_match_latency(avg_ms: float, label: str) -> None:
    print(f"{label} avg latency: {avg_ms:.2f}ms")
    if avg_ms > NO_MATCH_MAX_MS:
        raise RuntimeError(f"{label}: expected latency <= {NO_MATCH_MAX_MS:.0f}ms, got {avg_ms:.2f}ms")


def assert_observed_sni(server: TlsEchoServer, start_idx: int, expected: str) -> None:
    seen = server.sni_since(start_idx)
    normalized_expected = expected.strip().rstrip(".").lower()
    if normalized_expected not in seen:
        raise RuntimeError(f"expected observed SNI {normalized_expected!r}, got {seen!r}")


def run_sni_exact_case(server: TlsEchoServer, host: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_tls_sni_exact",
        latency=TEST_LATENCY,
        targets=[{"sni": "api.foo.com", "protocol": "tcp", "port": port, "priority": 200}],
    )

    faultcore.set_thread_policy("targets_tls_sni_exact")

    @faultcore.fault()
    def call(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="api.foo.com")

    start_idx = server.sni_count()
    avg = measure_ms(call)
    assert_observed_sni(server, start_idx, "api.foo.com")
    assert_match_latency(avg, baseline_ms, "tls sni exact match")


def run_sni_wildcard_case(server: TlsEchoServer, host: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_tls_sni_wildcard",
        latency=TEST_LATENCY,
        targets=[{"sni": "*.foo.com", "protocol": "tcp", "port": port, "priority": 200}],
    )

    faultcore.set_thread_policy("targets_tls_sni_wildcard")

    @faultcore.fault()
    def call(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="edge.foo.com")

    start_idx = server.sni_count()
    avg = measure_ms(call)
    assert_observed_sni(server, start_idx, "edge.foo.com")
    assert_match_latency(avg, baseline_ms, "tls sni wildcard match")


def run_sni_no_match_case(server: TlsEchoServer, host: str, port: int) -> float:
    faultcore.register_policy(
        "targets_tls_sni_no_match",
        latency=TEST_LATENCY,
        targets=[{"sni": "api.foo.com", "protocol": "tcp", "port": port, "priority": 200}],
    )

    faultcore.set_thread_policy("targets_tls_sni_no_match")

    @faultcore.fault()
    def call(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="other.foo.com")

    start_idx = server.sni_count()
    avg = measure_ms(call)
    assert_observed_sni(server, start_idx, "other.foo.com")
    assert_no_match_latency(avg, "tls sni no-match")
    return avg


def run_ip_vs_sni_priority_cases(server: TlsEchoServer, host: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_tls_ip_priority_over_sni",
        latency=TEST_LATENCY,
        targets=[
            {"target": f"tcp://{host}:{port}", "priority": 300},
            {"sni": "api.foo.com", "protocol": "tcp", "port": port, "priority": 100},
        ],
    )

    faultcore.set_thread_policy("targets_tls_ip_priority_over_sni")

    @faultcore.fault()
    def call_ip_priority(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="api.foo.com")

    start_idx = server.sni_count()
    avg_ip_priority = measure_ms(call_ip_priority)
    assert_observed_sni(server, start_idx, "api.foo.com")
    assert_match_latency(avg_ip_priority, baseline_ms, "tls precedence ip> sni priority")

    faultcore.register_policy(
        "targets_tls_sni_priority_over_ip",
        latency=TEST_LATENCY,
        targets=[
            {"target": f"tcp://{host}:{port}", "priority": 100},
            {"sni": "api.foo.com", "protocol": "tcp", "port": port, "priority": 300},
        ],
    )

    faultcore.set_thread_policy("targets_tls_sni_priority_over_ip")

    @faultcore.fault()
    def call_sni_priority(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="api.foo.com")

    start_idx = server.sni_count()
    avg_sni_priority = measure_ms(call_sni_priority)
    assert_observed_sni(server, start_idx, "api.foo.com")
    assert_match_latency(avg_sni_priority, baseline_ms, "tls precedence sni> ip priority")


def run_ip_vs_sni_tie_case(server: TlsEchoServer, host: str, port: int, baseline_ms: float) -> None:
    faultcore.register_policy(
        "targets_tls_sni_tie_break_over_ip",
        latency=TEST_LATENCY,
        targets=[
            {"target": f"tcp://{host}:{port}", "priority": 200},
            {"sni": "api.foo.com", "protocol": "tcp", "port": port, "priority": 200},
        ],
    )

    faultcore.set_thread_policy("targets_tls_sni_tie_break_over_ip")

    @faultcore.fault()
    def call(message: str) -> str:
        return tls_echo(host, port, message, server_hostname="api.foo.com")

    start_idx = server.sni_count()
    avg = measure_ms(call)
    assert_observed_sni(server, start_idx, "api.foo.com")
    assert_match_latency(avg, baseline_ms, "tls precedence tie ip/sni")


def main() -> int:
    parser = argparse.ArgumentParser(description="FaultCore TLS SNI targets integration probe")
    parser.add_argument("--host", default="127.0.0.1", help="tls test server host")
    parser.add_argument("--port", type=int, default=9000, help="unused; accepted for tests.sh compatibility")
    parser.add_argument("--mode", choices=["all"], default="all")
    args = parser.parse_args()

    print(f"[{datetime.now().isoformat()}] targets TLS/SNI integration mode={args.mode} host={args.host}")
    shm_name = ensure_shm_ready()
    print(f"using shm: {shm_name}")

    server = TlsEchoServer(args.host)
    try:
        server.start()
        baseline_ms = run_sni_no_match_case(server, args.host, server.port)
        run_sni_exact_case(server, args.host, server.port, baseline_ms)
        run_sni_wildcard_case(server, args.host, server.port, baseline_ms)
        run_ip_vs_sni_priority_cases(server, args.host, server.port, baseline_ms)
        run_ip_vs_sni_tie_case(server, args.host, server.port, baseline_ms)
    except OSError as exc:
        print(f"ERROR: TLS socket setup failed: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1
    finally:
        server.stop()

    print("targets TLS/SNI integration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
