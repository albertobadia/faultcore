#!/usr/bin/env python3
import argparse
import json
import socket
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import faultcore


def _tcp_roundtrip_raw(host: str, port: int, payload: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect((host, port))
        sock.sendall(payload.encode("utf-8"))
        data = sock.recv(4096)
        return len(data)


def _udp_roundtrip_raw(host: str, port: int, payload: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(payload.encode("utf-8"), (host, port))
        data, _ = sock.recvfrom(4096)
        return len(data)


def _http_roundtrip_raw(base_url: str, path: str) -> int:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
        body = response.read()
    return len(body)


@faultcore.latency("25ms")
@faultcore.jitter("10ms")
def tcp_roundtrip(host: str, port: int, payload: str) -> int:
    return _tcp_roundtrip_raw(host, port, payload)


@faultcore.rate("4mbps")
def udp_roundtrip(host: str, port: int, payload: str) -> int:
    return _udp_roundtrip_raw(host, port, payload)


@faultcore.latency("40ms")
def http_roundtrip(base_url: str, path: str) -> int:
    return _http_roundtrip_raw(base_url, path)


@faultcore.timeout(connect="1000ms", recv="1000ms")
def test_timeout_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"timeout-{idx}\n")


@faultcore.packet_loss("100%")
def test_packet_loss_udp(host: str, port: int, idx: int) -> int:
    return _udp_roundtrip_raw(host, port, f"packet-loss-{idx}")


@faultcore.burst_loss("2")
def test_burst_loss_udp(host: str, port: int, idx: int) -> int:
    return _udp_roundtrip_raw(host, port, f"burst-loss-{idx}")


@faultcore.latency("1ms")
def test_uplink_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"uplink-{idx}\n")


@faultcore.jitter("1ms")
def test_downlink_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"downlink-{idx}\n")


@faultcore.correlated_loss(p_good_to_bad="100%", p_bad_to_good="0%", loss_good="0%", loss_bad="100%")
def test_correlated_loss_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"correlated-loss-{idx}\n")


@faultcore.connection_error(kind="reset", prob="100%")
def test_connection_error_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"connection-error-{idx}\n")


@faultcore.connection_error(kind="refused", prob="100%")
def test_half_open_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"half-open-{idx}\n")


@faultcore.packet_duplicate(prob="100%", max_extra=1)
def test_packet_duplicate_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"packet-duplicate-{idx}\n")


@faultcore.packet_reorder(prob="100%", max_delay="10ms", window=2)
def test_packet_reorder_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"packet-reorder-{idx}\n")


@faultcore.payload_mutation(enabled=True, prob="100%", type="truncate", target="both", truncate_size="1kb")
def test_payload_mutation_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"payload-mutation-{idx}\n")


@faultcore.session_budget(max_tx="1kb", max_rx="1gb", max_ops=1_000_000, max_duration="600s", action="drop")
def test_session_budget_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"session-budget-{idx}\n")


@faultcore.dns(delay="1ms", timeout="0ms", nxdomain="0%")
def test_dns_http(base_url: str, idx: int) -> int:
    return _http_roundtrip_raw(base_url, f"/echo/dns-{idx}")


@faultcore.fault("docker_policy_safe")
def test_fault_policy_tcp(host: str, port: int, idx: int) -> int:
    return _tcp_roundtrip_raw(host, port, f"fault-policy-{idx}\n")


def _run_case_once(name: str, operation: Callable[[], int]) -> tuple[str, dict[str, object]]:
    start = time.perf_counter()
    try:
        payload_bytes = int(operation())
    except OSError:
        payload_bytes = 0
    elapsed_ms = (time.perf_counter() - start) * 1000
    profile = _build_function_profile(
        latency_ms=[elapsed_ms],
        bytes_series=[payload_bytes],
        duration_series_ms=[elapsed_ms],
        total_bytes=payload_bytes,
        wall_seconds=max(0.001, elapsed_ms / 1000.0),
    )
    return name, profile


def _avg(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def _jitter(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    diffs = [abs(values[idx] - values[idx - 1]) for idx in range(1, len(values))]
    return _avg(diffs)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95)))
    return ordered[pos]


def _build_function_profile(
    latency_ms: list[float],
    bytes_series: list[int],
    duration_series_ms: list[float],
    total_bytes: int,
    wall_seconds: float,
) -> dict[str, object]:
    throughput_series: list[int] = []
    cumulative_bytes: list[int] = []
    acc = 0
    for idx, payload_bytes in enumerate(bytes_series):
        acc += int(payload_bytes)
        cumulative_bytes.append(acc)
        duration_ms = duration_series_ms[idx] if idx < len(duration_series_ms) else 0.0
        throughput_series.append(int((payload_bytes * 8_000.0) / max(0.001, duration_ms)))
    return {
        "latency_avg_ms": round(_avg(latency_ms), 3),
        "latency_p95_ms": round(_p95(latency_ms), 3),
        "jitter_ms": round(_jitter(latency_ms), 3),
        "bytes_total": int(total_bytes),
        "throughput_bps": int((total_bytes * 8) / max(0.001, wall_seconds)),
        "series_latency_ms": [round(v, 3) for v in latency_ms],
        "series_throughput_bps": throughput_series,
        "series_bytes_per_call": [int(v) for v in bytes_series],
        "series_bytes_cumulative": cumulative_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Real multi-protocol network traffic scenario")
    parser.add_argument("--tcp-host", default="tcp-echo")
    parser.add_argument("--tcp-port", type=int, default=9000)
    parser.add_argument("--udp-host", default="udp-echo")
    parser.add_argument("--udp-port", type=int, default=9001)
    parser.add_argument("--http-url", default="http://http-echo:8000")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--metrics-out", default="/workspace/artifacts/network_metrics.json")
    args = parser.parse_args()

    faultcore.register_policy(name="docker_policy_safe", latency="1ms", jitter="0ms", packet_loss="0%")

    tcp_ms: list[float] = []
    udp_ms: list[float] = []
    http_ms: list[float] = []
    tcp_bytes_series: list[int] = []
    udp_bytes_series: list[int] = []
    http_bytes_series: list[int] = []
    tcp_duration_series_ms: list[float] = []
    udp_duration_series_ms: list[float] = []
    http_duration_series_ms: list[float] = []
    tcp_bytes = 0
    udp_bytes = 0
    http_bytes = 0
    error_counts = {"tcp": 0, "udp": 0, "http": 0}
    sample_errors: list[str] = []
    wall_start = time.perf_counter()

    for idx in range(args.iterations):
        t0 = time.perf_counter()
        try:
            tcp_call_bytes = tcp_roundtrip(args.tcp_host, args.tcp_port, f"tcp-{idx}\\n")
        except OSError as exc:
            tcp_call_bytes = 0
            error_counts["tcp"] += 1
            if len(sample_errors) < 10:
                sample_errors.append(f"tcp[{idx}] {exc}")
        tcp_call_ms = (time.perf_counter() - t0) * 1000
        tcp_bytes += tcp_call_bytes
        tcp_ms.append(tcp_call_ms)
        tcp_bytes_series.append(tcp_call_bytes)
        tcp_duration_series_ms.append(tcp_call_ms)

        t0 = time.perf_counter()
        try:
            udp_call_bytes = udp_roundtrip(args.udp_host, args.udp_port, f"udp-{idx}")
        except OSError as exc:
            udp_call_bytes = 0
            error_counts["udp"] += 1
            if len(sample_errors) < 10:
                sample_errors.append(f"udp[{idx}] {exc}")
        udp_call_ms = (time.perf_counter() - t0) * 1000
        udp_bytes += udp_call_bytes
        udp_ms.append(udp_call_ms)
        udp_bytes_series.append(udp_call_bytes)
        udp_duration_series_ms.append(udp_call_ms)

        t0 = time.perf_counter()
        try:
            http_call_bytes = http_roundtrip(args.http_url, f"/echo/http-{idx}")
        except OSError as exc:
            http_call_bytes = 0
            error_counts["http"] += 1
            if len(sample_errors) < 10:
                sample_errors.append(f"http[{idx}] {exc}")
        http_call_ms = (time.perf_counter() - t0) * 1000
        http_bytes += http_call_bytes
        http_ms.append(http_call_ms)
        http_bytes_series.append(http_call_bytes)
        http_duration_series_ms.append(http_call_ms)

    wall_seconds = max(0.001, time.perf_counter() - wall_start)

    function_metrics = {
        "tcp_roundtrip": _build_function_profile(
            tcp_ms, tcp_bytes_series, tcp_duration_series_ms, tcp_bytes, wall_seconds
        ),
        "udp_roundtrip": _build_function_profile(
            udp_ms, udp_bytes_series, udp_duration_series_ms, udp_bytes, wall_seconds
        ),
        "http_roundtrip": _build_function_profile(
            http_ms, http_bytes_series, http_duration_series_ms, http_bytes, wall_seconds
        ),
    }

    unit_case_calls = (
        ("test_latency", lambda: tcp_roundtrip(args.tcp_host, args.tcp_port, "test-latency\n")),
        ("test_jitter", lambda: tcp_roundtrip(args.tcp_host, args.tcp_port, "test-jitter\n")),
        ("test_rate", lambda: udp_roundtrip(args.udp_host, args.udp_port, "test-rate")),
        ("test_timeout", lambda: test_timeout_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_packet_loss", lambda: test_packet_loss_udp(args.udp_host, args.udp_port, 0)),
        ("test_burst_loss", lambda: test_burst_loss_udp(args.udp_host, args.udp_port, 0)),
        ("test_uplink", lambda: test_uplink_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_downlink", lambda: test_downlink_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_correlated_loss", lambda: test_correlated_loss_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_connection_error", lambda: test_connection_error_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_half_open", lambda: test_half_open_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_packet_duplicate", lambda: test_packet_duplicate_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_packet_reorder", lambda: test_packet_reorder_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_payload_mutation", lambda: test_payload_mutation_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_dns", lambda: test_dns_http(args.http_url, 0)),
        ("test_session_budget", lambda: test_session_budget_tcp(args.tcp_host, args.tcp_port, 0)),
        ("test_fault_policy", lambda: test_fault_policy_tcp(args.tcp_host, args.tcp_port, 0)),
    )
    for case_name, case_call in unit_case_calls:
        name, profile = _run_case_once(case_name, case_call)
        function_metrics[name] = profile

    metrics = {
        "scenario": {
            "iterations": args.iterations,
            "duration_ms": int(wall_seconds * 1000),
        },
        "latency_ms": {
            "tcp_avg": round(_avg(tcp_ms), 3),
            "udp_avg": round(_avg(udp_ms), 3),
            "http_avg": round(_avg(http_ms), 3),
            "tcp_p95": round(_p95(tcp_ms), 3),
            "udp_p95": round(_p95(udp_ms), 3),
            "http_p95": round(_p95(http_ms), 3),
        },
        "jitter_ms": {
            "tcp": round(_jitter(tcp_ms), 3),
            "udp": round(_jitter(udp_ms), 3),
            "http": round(_jitter(http_ms), 3),
        },
        "bytes": {
            "tcp_total": tcp_bytes,
            "udp_total": udp_bytes,
            "http_total": http_bytes,
            "total": tcp_bytes + udp_bytes + http_bytes,
        },
        "throughput_bps": {
            "tcp": int((tcp_bytes * 8) / wall_seconds),
            "udp": int((udp_bytes * 8) / wall_seconds),
            "http": int((http_bytes * 8) / wall_seconds),
            "total": int(((tcp_bytes + udp_bytes + http_bytes) * 8) / wall_seconds),
        },
        "errors": {
            "tcp": error_counts["tcp"],
            "udp": error_counts["udp"],
            "http": error_counts["http"],
            "total": error_counts["tcp"] + error_counts["udp"] + error_counts["http"],
            "sample": sample_errors,
        },
        "series": {
            "tcp_latency_ms": [round(v, 3) for v in tcp_ms],
            "udp_latency_ms": [round(v, 3) for v in udp_ms],
            "http_latency_ms": [round(v, 3) for v in http_ms],
        },
        "functions": function_metrics,
    }

    metrics_out = Path(args.metrics_out)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(json.dumps(metrics, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print("scenario_completed")
    print(f"tcp_avg_ms={metrics['latency_ms']['tcp_avg']:.2f}")
    print(f"udp_avg_ms={metrics['latency_ms']['udp_avg']:.2f}")
    print(f"http_avg_ms={metrics['latency_ms']['http_avg']:.2f}")
    print(f"total_throughput_bps={metrics['throughput_bps']['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
