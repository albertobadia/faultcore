#!/usr/bin/env python3

import ctypes
import os
import socket
import time
from ctypes import util

import pytest

libc = ctypes.CDLL(util.find_library("c"), use_errno=True)

ECHO_SERVER_HOST = os.environ.get("ECHO_SERVER_HOST", "faultcore-echo-server")
ECHO_SERVER_PORT = int(os.environ.get("ECHO_SERVER_PORT", "9000"))
HTTP_SERVER_HOST = os.environ.get("HTTP_SERVER_HOST", "faultcore-http-server")
HTTP_SERVER_PORT = int(os.environ.get("HTTP_SERVER_PORT", "8000"))

PRIORITY_WHICH = 0
PRIORITY_PRIO = 0

MAGIC_WHICH = 0xFA
MAGIC_BANDWIDTH = 0xFB
MAGIC_TIMEOUT = 0xFC


def setpriority(which, who, prio):
    result = libc.setpriority(which, who, prio)
    if result != 0:
        raise OSError(ctypes.get_errno(), "setpriority failed")
    return result


class TestInterceptorLatency:
    def test_baseline_latency(self):
        latencies = []

        for _ in range(5):
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))
            sock.sendall(b"test\n")
            sock.recv(4096)
            sock.close()
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 100, f"Baseline latency too high: {avg_latency}ms"

    def test_latency_injection(self):
        MAGIC_WHICH = 0xFA
        MAGIC_WHO = 100
        MAGIC_PRIO = 0

        setpriority(MAGIC_WHICH, MAGIC_WHO, MAGIC_PRIO)

        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))
            sock.sendall(b"test\n")
            sock.recv(4096)
            sock.close()
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        setpriority(MAGIC_WHICH, 0, 0)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency >= 90, f"Latency not injected: {avg_latency}ms (expected ~100ms)"


class TestInterceptorBandwidth:
    def test_baseline_bandwidth(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))

        data = b"x" * 1024
        start = time.perf_counter()

        for _ in range(100):
            sock.sendall(data)

        elapsed = time.perf_counter() - start
        sock.close()

        bytes_sent = 1024 * 100
        bps = bytes_sent / elapsed

        assert bps > 100000, f"Baseline bandwidth too low: {bps} bps"

    def test_bandwidth_throttle(self):
        MAGIC_BANDWIDTH = 0xFB
        RATE_KBPS = 10

        setpriority(MAGIC_BANDWIDTH, 0xFFFFFFFF, RATE_KBPS)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))

        data = b"x" * 1024
        start = time.perf_counter()

        for _ in range(50):
            sock.sendall(data)

        elapsed = time.perf_counter() - start
        sock.close()

        setpriority(MAGIC_BANDWIDTH, 0, 0)

        bytes_sent = 1024 * 50
        bps = bytes_sent / elapsed
        expected_bps = RATE_KBPS * 1000

        assert bps < expected_bps * 1.5, f"Bandwidth not throttled: {bps} bps (expected ~{expected_bps})"


class TestInterceptorTimeout:
    def test_connect_timeout(self):
        MAGIC_TIMEOUT = 0xFC
        CONNECT_TIMEOUT_MS = 2000

        setpriority(MAGIC_TIMEOUT, CONNECT_TIMEOUT_MS, 5000)

        start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)

        try:
            sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))
            sock.close()
            elapsed = time.perf_counter() - start
        except TimeoutError:
            elapsed = time.perf_counter() - start
            sock.close()

        setpriority(MAGIC_TIMEOUT, 0, 0)

        assert elapsed >= CONNECT_TIMEOUT_MS * 0.9, (
            f"Timeout not applied: {elapsed * 1000:.0f}ms (expected ~{CONNECT_TIMEOUT_MS}ms)"
        )

    def test_recv_timeout(self):
        MAGIC_TIMEOUT = 0xFC
        RECV_TIMEOUT_MS = 2000

        setpriority(MAGIC_TIMEOUT, 0xFFFFFFFF, RECV_TIMEOUT_MS)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))

        sock.sendall(b"NO RESPONSE\n")

        start = time.perf_counter()

        try:
            sock.recv(4096)
            elapsed = time.perf_counter() - start
        except TimeoutError:
            elapsed = time.perf_counter() - start
            sock.close()

        setpriority(MAGIC_TIMEOUT, 0, 0)

        assert elapsed >= RECV_TIMEOUT_MS * 0.9, (
            f"Recv timeout not applied: {elapsed * 1000:.0f}ms (expected ~{RECV_TIMEOUT_MS}ms)"
        )


class TestInterceptorChaos:
    def test_packet_loss(self):
        MAGIC_WHICH = 0xFA
        LATENCY_MS = 0
        PACKET_LOSS_PCT = 50

        setpriority(MAGIC_WHICH, LATENCY_MS, PACKET_LOSS_PCT * 10000)

        successes = 0
        failures = 0

        for _ in range(20):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((ECHO_SERVER_HOST, ECHO_SERVER_PORT))
                sock.sendall(b"test\n")
                response = sock.recv(4096)
                sock.close()

                if response:
                    successes += 1
                else:
                    failures += 1
            except Exception:
                failures += 1

        setpriority(MAGIC_WHICH, 0, 0)

        loss_rate = failures / (successes + failures) if (successes + failures) > 0 else 0

        assert loss_rate > 0.3, f"Packet loss not injected: {loss_rate * 100:.1f}% (expected ~50%)"


class TestHTTPIntegration:
    def test_http_health(self):
        import urllib.request

        response = urllib.request.urlopen(f"http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}/health", timeout=5)
        assert response.status == 200
        data = response.read()
        assert b"healthy" in data

    def test_http_echo(self):
        import urllib.request

        response = urllib.request.urlopen(f"http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}/echo/test_message", timeout=5)
        assert response.status == 200
        data = response.read()
        assert b"test_message" in data

    def test_http_upload(self):
        import json
        import urllib.request

        data = json.dumps({"key": "value", "numbers": [1, 2, 3]}).encode("utf-8")
        req = urllib.request.Request(
            f"http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}/upload",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        response = urllib.request.urlopen(req, timeout=5)
        assert response.status == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
