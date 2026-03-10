import asyncio
import contextvars
import functools
import ipaddress
import json
import signal
import threading
import time
from asyncio import iscoroutine, wait_for
from collections.abc import Callable
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any

from faultcore.shm_writer import get_shm_writer

_POLICY_REGISTRY: dict[str, dict[str, Any]] = {}
_THREAD_POLICY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "faultcore_thread_policy",
    default=None,
)
_METRICS_CONTEXT_BASELINE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "faultcore_metrics_context_baseline",
    default=None,
)
_POLICY_LOCK = threading.RLock()

_METRICS_FIELDS = (
    "continue",
    "delay",
    "drop",
    "timeout",
    "error",
    "connection_error",
    "reorder",
    "duplicate",
    "nxdomain",
    "skipped",
)


def _read_fault_metrics_snapshot() -> dict[str, Any] | None:
    import ctypes

    class LayerMetrics(ctypes.Structure):
        _fields_ = [
            ("stage", ctypes.c_uint8),
            ("reserved", ctypes.c_uint8 * 7),
            ("continue_count", ctypes.c_uint64),
            ("delay_count", ctypes.c_uint64),
            ("drop_count", ctypes.c_uint64),
            ("timeout_count", ctypes.c_uint64),
            ("error_count", ctypes.c_uint64),
            ("connection_error_count", ctypes.c_uint64),
            ("reorder_count", ctypes.c_uint64),
            ("duplicate_count", ctypes.c_uint64),
            ("nxdomain_count", ctypes.c_uint64),
            ("skipped_count", ctypes.c_uint64),
        ]

    class MetricsSnapshot(ctypes.Structure):
        _fields_ = [
            ("len", ctypes.c_uint64),
            ("layers", LayerMetrics * 7),
        ]

    lib = ctypes.CDLL(None)
    if not hasattr(lib, "faultcore_metrics_snapshot"):
        return None

    snapshot_fn = lib.faultcore_metrics_snapshot
    snapshot_fn.argtypes = [ctypes.POINTER(MetricsSnapshot)]
    snapshot_fn.restype = ctypes.c_bool

    snapshot = MetricsSnapshot()
    if not snapshot_fn(ctypes.byref(snapshot)):
        return None

    stage_name = {
        1: "L1",
        2: "L2",
        3: "L3",
        4: "L4",
        5: "L5",
        6: "L6",
        7: "L7",
    }
    layers: list[dict[str, Any]] = []
    for idx in range(int(snapshot.len)):
        layer = snapshot.layers[idx]
        layers.append(
            {
                "stage": stage_name.get(int(layer.stage), f"UNKNOWN_{int(layer.stage)}"),
                "continue": int(layer.continue_count),
                "delay": int(layer.delay_count),
                "drop": int(layer.drop_count),
                "timeout": int(layer.timeout_count),
                "error": int(layer.error_count),
                "connection_error": int(layer.connection_error_count),
                "reorder": int(layer.reorder_count),
                "duplicate": int(layer.duplicate_count),
                "nxdomain": int(layer.nxdomain_count),
                "skipped": int(layer.skipped_count),
            }
        )

    totals = {name: sum(item[name] for item in layers) for name in _METRICS_FIELDS}
    return {"layers": layers, "totals": totals}


def _capture_metrics_context() -> contextvars.Token[dict[str, Any] | None] | None:
    snapshot = _read_fault_metrics_snapshot()
    if snapshot is None:
        return None
    return _METRICS_CONTEXT_BASELINE.set(snapshot)


def _restore_metrics_context(token: contextvars.Token[dict[str, Any] | None] | None) -> None:
    if token is None:
        return
    _METRICS_CONTEXT_BASELINE.reset(token)


def _get_metrics_context_baseline() -> dict[str, Any] | None:
    return _METRICS_CONTEXT_BASELINE.get()


def _build_direction_profile(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        profile["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        profile["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        profile["packet_loss_ppm"] = _parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        profile["burst_loss_len"] = b
    if rate is not None:
        profile["bandwidth_bps"] = _parse_rate(rate)
    return profile


def _build_correlated_loss_profile(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
) -> dict[str, int]:
    profile = {
        "p_good_to_bad_ppm": _parse_packet_loss(p_good_to_bad),
        "p_bad_to_good_ppm": _parse_packet_loss(p_bad_to_good),
        "loss_good_ppm": _parse_packet_loss(loss_good),
        "loss_bad_ppm": _parse_packet_loss(loss_bad),
    }
    profile["enabled"] = 1
    return profile


def _parse_error_kind(kind: str) -> int:
    normalized = kind.strip().lower()
    if normalized == "reset":
        return 1
    if normalized == "refused":
        return 2
    if normalized == "unreachable":
        return 3
    raise ValueError("error kind must be one of: reset, refused, unreachable")


def _build_connection_error_profile(*, kind: str, prob: str | int | float = "100%") -> dict[str, int]:
    return {"kind": _parse_error_kind(kind), "prob_ppm": _parse_packet_loss(prob)}


def _build_half_open_profile(*, after_bytes: int, error: str = "reset") -> dict[str, int]:
    threshold = int(after_bytes)
    if threshold <= 0:
        raise ValueError("after_bytes must be > 0")
    return {"after_bytes": threshold, "err_kind": _parse_error_kind(error)}


def _build_packet_duplicate_profile(*, prob: str | int | float = "100%", max_extra: int = 1) -> dict[str, int]:
    extra = int(max_extra)
    if extra <= 0:
        raise ValueError("max_extra must be > 0")
    return {"prob_ppm": _parse_packet_loss(prob), "max_extra": extra}


def _build_packet_reorder_profile(
    *,
    prob: str | int | float = "100%",
    max_delay_ms: int = 0,
    window: int = 1,
) -> dict[str, int]:
    delay_ms = int(max_delay_ms)
    if delay_ms < 0:
        raise ValueError("max_delay_ms must be >= 0")
    reorder_window = int(window)
    if reorder_window <= 0:
        raise ValueError("window must be > 0")
    return {
        "prob_ppm": _parse_packet_loss(prob),
        "max_delay_ns": delay_ms * 1_000_000,
        "window": reorder_window,
    }


def _build_dns_profile(
    *,
    delay_ms: int | None = None,
    timeout_ms: int | None = None,
    nxdomain: str | int | float | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if delay_ms is not None:
        d = int(delay_ms)
        if d < 0:
            raise ValueError("dns delay must be >= 0")
        profile["delay_ms"] = d
    if timeout_ms is not None:
        t = int(timeout_ms)
        if t < 0:
            raise ValueError("dns timeout must be >= 0")
        profile["timeout_ms"] = t
    if nxdomain is not None:
        profile["nxdomain_ppm"] = _parse_packet_loss(nxdomain)
    return profile


def _parse_target_protocol(protocol: str | None) -> int:
    if protocol is None:
        return 0
    normalized = protocol.strip().lower()
    if normalized == "tcp":
        return 1
    if normalized == "udp":
        return 2
    raise ValueError("target protocol must be one of: tcp, udp")


def _build_target_profile(
    *,
    target: str | None = None,
    host: str | None = None,
    cidr: str | None = None,
    port: int | None = None,
    protocol: str | None = None,
    priority: int | None = None,
) -> dict[str, int]:
    parsed_protocol = _parse_target_protocol(protocol)
    parsed_host = host
    parsed_port = int(port) if port is not None else 0
    parsed_cidr = cidr

    if target is not None:
        raw = target.strip()
        if not raw:
            raise ValueError("target must be non-empty")
        if "://" in raw:
            proto_raw, raw = raw.split("://", 1)
            proto_from_target = _parse_target_protocol(proto_raw)
            if parsed_protocol and parsed_protocol != proto_from_target:
                raise ValueError("target protocol conflicts with protocol parameter")
            parsed_protocol = proto_from_target
        if "/" in raw:
            parsed_cidr = raw
        else:
            if ":" in raw:
                host_part, port_part = raw.rsplit(":", 1)
                raw = host_part
                if parsed_port != 0 and parsed_port != int(port_part):
                    raise ValueError("target port conflicts with port parameter")
                parsed_port = int(port_part)
            parsed_host = raw

    if parsed_port < 0 or parsed_port > 65535:
        raise ValueError("target port must be between 0 and 65535")
    parsed_priority = 100 if priority is None else int(priority)
    if parsed_priority < 0 or parsed_priority > 65535:
        raise ValueError("target priority must be between 0 and 65535")

    if parsed_host and parsed_cidr:
        raise ValueError("target cannot define both host and cidr")
    if not parsed_host and not parsed_cidr:
        raise ValueError("target requires either host or cidr")

    if parsed_host:
        ipv4 = int(ipaddress.IPv4Address(parsed_host))
        return {
            "enabled": 1,
            "kind": 1,
            "ipv4": ipv4,
            "prefix_len": 32,
            "port": parsed_port,
            "protocol": parsed_protocol,
            "priority": parsed_priority,
        }

    network = ipaddress.IPv4Network(parsed_cidr, strict=False)
    return {
        "enabled": 1,
        "kind": 2,
        "ipv4": int(network.network_address),
        "prefix_len": int(network.prefixlen),
        "port": parsed_port,
        "protocol": parsed_protocol,
        "priority": parsed_priority,
    }


def _build_schedule_profile(
    *,
    kind: str,
    every_s: int | float | None = None,
    duration_s: int | float | None = None,
    on_s: int | float | None = None,
    off_s: int | float | None = None,
    ramp_s: int | float | None = None,
) -> dict[str, int]:
    normalized = kind.strip().lower()
    if normalized == "spike":
        if every_s is None or duration_s is None:
            raise ValueError("spike profile requires every_s and duration_s")
        cycle_ns = int(float(every_s) * 1_000_000_000)
        active_ns = int(float(duration_s) * 1_000_000_000)
        if cycle_ns <= 0 or active_ns <= 0 or active_ns > cycle_ns:
            raise ValueError("spike profile requires 0 < duration_s <= every_s")
        return {"schedule_type": 2, "param_a_ns": cycle_ns, "param_b_ns": active_ns, "param_c_ns": 0}

    if normalized == "flapping":
        if on_s is None or off_s is None:
            raise ValueError("flapping profile requires on_s and off_s")
        on_ns = int(float(on_s) * 1_000_000_000)
        off_ns = int(float(off_s) * 1_000_000_000)
        if on_ns <= 0 or off_ns <= 0:
            raise ValueError("flapping profile requires on_s > 0 and off_s > 0")
        return {"schedule_type": 3, "param_a_ns": on_ns, "param_b_ns": off_ns, "param_c_ns": 0}

    if normalized == "ramp":
        if ramp_s is None:
            raise ValueError("ramp profile requires ramp_s")
        ramp_ns = int(float(ramp_s) * 1_000_000_000)
        if ramp_ns <= 0:
            raise ValueError("ramp profile requires ramp_s > 0")
        return {"schedule_type": 1, "param_a_ns": ramp_ns, "param_b_ns": 0, "param_c_ns": 0}

    raise ValueError("schedule kind must be one of: ramp, spike, flapping")


class FaultWrapper:
    def __init__(
        self,
        func: Callable[..., Any],
        latency_ms: int | None = None,
        jitter_ms: int | None = None,
        packet_loss_ppm: int | None = None,
        burst_loss_len: int | None = None,
        bandwidth_bps: int | None = None,
        timeouts: tuple[int, int] | None = None,
        uplink_profile: dict[str, int] | None = None,
        downlink_profile: dict[str, int] | None = None,
        correlated_loss_profile: dict[str, int] | None = None,
        connection_error_profile: dict[str, int] | None = None,
        half_open_profile: dict[str, int] | None = None,
        packet_duplicate_profile: dict[str, int] | None = None,
        packet_reorder_profile: dict[str, int] | None = None,
        dns_profile: dict[str, int] | None = None,
        target_profile: dict[str, int] | None = None,
        target_profiles: list[dict[str, int]] | None = None,
        schedule_profile: dict[str, int] | None = None,
    ):
        functools.update_wrapper(self, func)
        self._func = func
        self._latency_ms = latency_ms
        self._jitter_ms = jitter_ms
        self._packet_loss_ppm = packet_loss_ppm
        self._burst_loss_len = burst_loss_len
        self._bandwidth_bps = bandwidth_bps
        self._timeouts = timeouts
        self._uplink_profile = uplink_profile or {}
        self._downlink_profile = downlink_profile or {}
        self._correlated_loss_profile = correlated_loss_profile or {}
        self._connection_error_profile = connection_error_profile or {}
        self._half_open_profile = half_open_profile or {}
        self._packet_duplicate_profile = packet_duplicate_profile or {}
        self._packet_reorder_profile = packet_reorder_profile or {}
        self._dns_profile = dns_profile or {}
        self._target_profile = target_profile or {}
        self._target_profiles = target_profiles or []
        self._schedule_profile = schedule_profile or {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._func, name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tid = threading.get_native_id()
        shm = get_shm_writer()
        metrics_token = _capture_metrics_context()

        if self._latency_ms:
            shm.write_latency(tid, self._latency_ms)

        if self._jitter_ms:
            shm.write_jitter(tid, self._jitter_ms)

        if self._packet_loss_ppm is not None:
            shm.write_packet_loss(tid, self._packet_loss_ppm)

        if self._burst_loss_len is not None:
            shm.write_burst_loss(tid, self._burst_loss_len)

        if self._bandwidth_bps:
            shm.write_bandwidth(tid, self._bandwidth_bps)

        if self._timeouts:
            connect_ms, recv_ms = self._timeouts
            shm.write_timeouts(tid, connect_ms, recv_ms)

        if self._uplink_profile:
            shm.write_uplink(
                tid,
                latency_ms=self._uplink_profile.get("latency_ms"),
                jitter_ms=self._uplink_profile.get("jitter_ms"),
                packet_loss_ppm=self._uplink_profile.get("packet_loss_ppm"),
                burst_loss_len=self._uplink_profile.get("burst_loss_len"),
                bandwidth_bps=self._uplink_profile.get("bandwidth_bps"),
            )

        if self._downlink_profile:
            shm.write_downlink(
                tid,
                latency_ms=self._downlink_profile.get("latency_ms"),
                jitter_ms=self._downlink_profile.get("jitter_ms"),
                packet_loss_ppm=self._downlink_profile.get("packet_loss_ppm"),
                burst_loss_len=self._downlink_profile.get("burst_loss_len"),
                bandwidth_bps=self._downlink_profile.get("bandwidth_bps"),
            )

        if self._correlated_loss_profile:
            shm.write_correlated_loss(
                tid,
                enabled=bool(self._correlated_loss_profile.get("enabled", 0)),
                p_good_to_bad_ppm=self._correlated_loss_profile.get("p_good_to_bad_ppm", 0),
                p_bad_to_good_ppm=self._correlated_loss_profile.get("p_bad_to_good_ppm", 0),
                loss_good_ppm=self._correlated_loss_profile.get("loss_good_ppm", 0),
                loss_bad_ppm=self._correlated_loss_profile.get("loss_bad_ppm", 0),
            )

        if self._connection_error_profile:
            shm.write_connection_error(
                tid,
                kind=self._connection_error_profile.get("kind", 0),
                prob_ppm=self._connection_error_profile.get("prob_ppm", 0),
            )

        if self._half_open_profile:
            shm.write_half_open(
                tid,
                after_bytes=self._half_open_profile.get("after_bytes", 0),
                err_kind=self._half_open_profile.get("err_kind", 0),
            )

        if self._packet_duplicate_profile:
            shm.write_packet_duplicate(
                tid,
                prob_ppm=self._packet_duplicate_profile.get("prob_ppm", 0),
                max_extra=self._packet_duplicate_profile.get("max_extra", 1),
            )

        if self._packet_reorder_profile:
            shm.write_packet_reorder(
                tid,
                prob_ppm=self._packet_reorder_profile.get("prob_ppm", 0),
                max_delay_ns=self._packet_reorder_profile.get("max_delay_ns", 0),
                window=self._packet_reorder_profile.get("window", 1),
            )

        if self._dns_profile:
            shm.write_dns(
                tid,
                delay_ms=self._dns_profile.get("delay_ms"),
                timeout_ms=self._dns_profile.get("timeout_ms"),
                nxdomain_ppm=self._dns_profile.get("nxdomain_ppm"),
            )

        if self._target_profiles:
            shm.write_targets(tid, self._target_profiles)
        elif self._target_profile:
            shm.write_target(
                tid,
                enabled=bool(self._target_profile.get("enabled", 0)),
                kind=self._target_profile.get("kind", 0),
                ipv4=self._target_profile.get("ipv4", 0),
                prefix_len=self._target_profile.get("prefix_len", 0),
                port=self._target_profile.get("port", 0),
                protocol=self._target_profile.get("protocol", 0),
            )

        if self._schedule_profile:
            shm.write_schedule(
                tid,
                schedule_type=self._schedule_profile.get("schedule_type", 0),
                param_a_ns=self._schedule_profile.get("param_a_ns", 0),
                param_b_ns=self._schedule_profile.get("param_b_ns", 0),
                param_c_ns=self._schedule_profile.get("param_c_ns", 0),
                started_monotonic_ns=time.monotonic_ns(),
            )

        timeout_ms = self._timeouts[0] if self._timeouts else None

        if timeout_ms and timeout_ms > 0 and not iscoroutinefunction(self._func):
            try:
                return _run_sync_with_timeout(self._func, timeout_ms, args, kwargs)
            finally:
                shm.clear(tid)
                _restore_metrics_context(metrics_token)

        result = self._func(*args, **kwargs)

        if iscoroutine(result):
            _restore_metrics_context(metrics_token)
            return self._run_async(result, shm, tid, timeout_ms)

        try:
            return result
        finally:
            shm.clear(tid)
            _restore_metrics_context(metrics_token)

    async def _run_async(
        self,
        result: Any,
        shm: Any,
        tid: int,
        timeout_ms: int | None,
    ) -> Any:
        metrics_token = _capture_metrics_context()
        try:
            if timeout_ms and timeout_ms > 0:
                try:
                    return await wait_for(result, timeout_ms / 1000)
                except (asyncio.exceptions.TimeoutError, TimeoutError) as exc:
                    raise TimeoutError(f"Function execution exceeded {timeout_ms}ms") from exc
            return await result
        finally:
            shm.clear(tid)
            _restore_metrics_context(metrics_token)

    def __repr__(self):
        return (
            "<FaultWrapper("
            f"latency={self._latency_ms}, "
            f"jitter={self._jitter_ms}, "
            f"packet_loss_ppm={self._packet_loss_ppm}, "
            f"burst_loss_len={self._burst_loss_len}, "
            f"bandwidth={self._bandwidth_bps}, "
            f"timeouts={self._timeouts}, "
            f"uplink={self._uplink_profile}, "
            f"downlink={self._downlink_profile}, "
            f"correlated_loss={self._correlated_loss_profile}, "
            f"connection_error={self._connection_error_profile}, "
            f"half_open={self._half_open_profile}, "
            f"packet_duplicate={self._packet_duplicate_profile}, "
            f"packet_reorder={self._packet_reorder_profile}, "
            f"dns={self._dns_profile}, "
            f"target={self._target_profile}, "
            f"schedule={self._schedule_profile}) for {self._func!r}>"
        )


def latency(latency_ms: int):
    if latency_ms < 0:
        raise ValueError("latency must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, latency_ms=latency_ms)

    return decorator


def jitter(jitter_ms: int):
    if jitter_ms < 0:
        raise ValueError("jitter must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, jitter_ms=jitter_ms)

    return decorator


def timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(timeout_ms, timeout_ms))

    return decorator


def connect_timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("connect_timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(timeout_ms, 0))

    return decorator


def recv_timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("recv_timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(0, timeout_ms))

    return decorator


def rate_limit(rate: str | int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        bps = _parse_rate(rate)
        return FaultWrapper(func, bandwidth_bps=bps)

    return decorator


def packet_loss(loss: str | int | float):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        ppm = _parse_packet_loss(loss)
        return FaultWrapper(func, packet_loss_ppm=ppm)

    return decorator


def burst_loss(length: int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        if length < 0:
            raise ValueError("burst_loss length must be >= 0")
        return FaultWrapper(func, burst_loss_len=int(length))

    return decorator


def uplink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not profile:
        raise ValueError("uplink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, uplink_profile=profile)

    return decorator


def downlink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not profile:
        raise ValueError("downlink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, downlink_profile=profile)

    return decorator


def correlated_loss(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
):
    profile = _build_correlated_loss_profile(
        p_good_to_bad=p_good_to_bad,
        p_bad_to_good=p_bad_to_good,
        loss_good=loss_good,
        loss_bad=loss_bad,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, correlated_loss_profile=profile)

    return decorator


def connection_error(*, kind: str, prob: str | int | float = "100%"):
    profile = _build_connection_error_profile(kind=kind, prob=prob)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, connection_error_profile=profile)

    return decorator


def half_open(*, after_bytes: int, error: str = "reset"):
    profile = _build_half_open_profile(after_bytes=after_bytes, error=error)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, half_open_profile=profile)

    return decorator


def packet_duplicate(*, prob: str | int | float = "100%", max_extra: int = 1):
    profile = _build_packet_duplicate_profile(prob=prob, max_extra=max_extra)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, packet_duplicate_profile=profile)

    return decorator


def packet_reorder(
    *,
    prob: str | int | float = "100%",
    max_delay_ms: int = 0,
    window: int = 1,
):
    profile = _build_packet_reorder_profile(prob=prob, max_delay_ms=max_delay_ms, window=window)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, packet_reorder_profile=profile)

    return decorator


def dns_delay(delay_ms: int):
    profile = _build_dns_profile(delay_ms=delay_ms)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=profile)

    return decorator


def dns_timeout(timeout_ms: int):
    profile = _build_dns_profile(timeout_ms=timeout_ms)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=profile)

    return decorator


def dns_nxdomain(prob: str | int | float = "100%"):
    profile = _build_dns_profile(nxdomain=prob)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=profile)

    return decorator


def for_target(
    target: str | None = None,
    *,
    host: str | None = None,
    cidr: str | None = None,
    port: int | None = None,
    protocol: str | None = None,
):
    profile = _build_target_profile(
        target=target,
        host=host,
        cidr=cidr,
        port=port,
        protocol=protocol,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, target_profile=profile)

    return decorator


def profile(
    kind: str,
    *,
    every_s: int | float | None = None,
    duration_s: int | float | None = None,
    on_s: int | float | None = None,
    off_s: int | float | None = None,
    ramp_s: int | float | None = None,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    schedule_profile = _build_schedule_profile(
        kind=kind,
        every_s=every_s,
        duration_s=duration_s,
        on_s=on_s,
        off_s=off_s,
        ramp_s=ramp_s,
    )
    direction = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(
            func,
            latency_ms=direction.get("latency_ms"),
            jitter_ms=direction.get("jitter_ms"),
            packet_loss_ppm=direction.get("packet_loss_ppm"),
            burst_loss_len=direction.get("burst_loss_len"),
            bandwidth_bps=direction.get("bandwidth_bps"),
            schedule_profile=schedule_profile,
        )

    return decorator


def _parse_rate(rate: str | int | float) -> int:
    def as_non_negative(value: float) -> float:
        if value < 0:
            raise ValueError("rate must be >= 0")
        return value

    if isinstance(rate, (int, float)):
        return int(as_non_negative(float(rate)) * 1_000_000)

    normalized_rate = rate.strip().lower()
    units = {
        "gbps": 1_000_000_000,
        "mbps": 1_000_000,
        "kbps": 1_000,
        "bps": 1,
    }
    for suffix, multiplier in units.items():
        if normalized_rate.endswith(suffix):
            numeric = as_non_negative(float(normalized_rate[: -len(suffix)]))
            return int(numeric * multiplier)

    return int(as_non_negative(float(normalized_rate)))


def _parse_packet_loss(loss: str | int | float) -> int:
    if isinstance(loss, str):
        raw = loss.strip().lower()
        if raw.endswith("%"):
            value = float(raw[:-1])
            if value < 0 or value > 100:
                raise ValueError("packet_loss percentage must be between 0 and 100")
            return int(value * 10_000)
        if raw.endswith("ppm"):
            value = float(raw[:-3])
            if value < 0 or value > 1_000_000:
                raise ValueError("packet_loss ppm must be between 0 and 1000000")
            return int(value)
        value = float(raw)
    else:
        value = float(loss)

    if value < 0:
        raise ValueError("packet_loss must be >= 0")
    if value <= 1:
        return int(value * 1_000_000)
    if value <= 100:
        return int(value * 10_000)
    if value <= 1_000_000:
        return int(value)
    raise ValueError("packet_loss must be <= 100%, <=1.0 ratio, or <=1000000ppm")


def apply_policy(_key: str):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        with _POLICY_LOCK:
            policy = _POLICY_REGISTRY.get(_key)
        if policy is None:
            return FaultWrapper(func)
        return FaultWrapper(
            func,
            latency_ms=policy.get("latency_ms"),
            jitter_ms=policy.get("jitter_ms"),
            packet_loss_ppm=policy.get("packet_loss_ppm"),
            burst_loss_len=policy.get("burst_loss_len"),
            bandwidth_bps=policy.get("bandwidth_bps"),
            timeouts=policy.get("timeouts"),
            uplink_profile=policy.get("uplink_profile"),
            downlink_profile=policy.get("downlink_profile"),
            correlated_loss_profile=policy.get("correlated_loss_profile"),
            connection_error_profile=policy.get("connection_error_profile"),
            half_open_profile=policy.get("half_open_profile"),
            packet_duplicate_profile=policy.get("packet_duplicate_profile"),
            packet_reorder_profile=policy.get("packet_reorder_profile"),
            dns_profile=policy.get("dns_profile"),
            target_profile=policy.get("target_profile"),
            target_profiles=policy.get("target_profiles"),
            schedule_profile=policy.get("schedule_profile"),
        )

    return decorator


def fault(_policy_name: str = "auto"):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        name = _policy_name
        if name == "auto":
            name = get_thread_policy() or ""
        if not name:
            return FaultWrapper(func)
        return apply_policy(name)(func)

    return decorator


def register_policy(
    name: str,
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
    timeout_ms: int | None = None,
    connect_timeout_ms: int | None = None,
    recv_timeout_ms: int | None = None,
    uplink: dict[str, Any] | None = None,
    downlink: dict[str, Any] | None = None,
    correlated_loss: dict[str, Any] | None = None,
    connection_error: dict[str, Any] | None = None,
    half_open: dict[str, Any] | None = None,
    packet_duplicate: dict[str, Any] | None = None,
    packet_reorder: dict[str, Any] | None = None,
    dns_delay_ms: int | None = None,
    dns_timeout_ms: int | None = None,
    dns_nxdomain: str | int | float | None = None,
    target: str | dict[str, Any] | None = None,
    targets: list[str | dict[str, Any]] | None = None,
    schedule: dict[str, Any] | None = None,
) -> None:
    if not name:
        raise ValueError("policy name must be non-empty")

    policy: dict[str, Any] = {}
    if target is not None and targets is not None:
        raise ValueError("target and targets are mutually exclusive")
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        policy["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        policy["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        policy["packet_loss_ppm"] = _parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        policy["burst_loss_len"] = b
    if rate is not None:
        policy["bandwidth_bps"] = _parse_rate(rate)
    if timeout_ms is not None:
        t = int(timeout_ms)
        if t < 0:
            raise ValueError("timeout_ms must be >= 0")
        policy["timeouts"] = (t, t)
    if connect_timeout_ms is not None or recv_timeout_ms is not None:
        connect_ms = int(connect_timeout_ms) if connect_timeout_ms is not None else 0
        recv_ms = int(recv_timeout_ms) if recv_timeout_ms is not None else 0
        if connect_ms < 0 or recv_ms < 0:
            raise ValueError("connect_timeout_ms and recv_timeout_ms must be >= 0")
        policy["timeouts"] = (connect_ms, recv_ms)
    if uplink is not None:
        if not isinstance(uplink, dict):
            raise ValueError("uplink must be a mapping when provided")
        policy["uplink_profile"] = _build_direction_profile(
            latency_ms=uplink.get("latency_ms"),
            jitter_ms=uplink.get("jitter_ms"),
            packet_loss=uplink.get("packet_loss"),
            burst_loss_len=uplink.get("burst_loss_len"),
            rate=uplink.get("rate"),
        )
    if downlink is not None:
        if not isinstance(downlink, dict):
            raise ValueError("downlink must be a mapping when provided")
        policy["downlink_profile"] = _build_direction_profile(
            latency_ms=downlink.get("latency_ms"),
            jitter_ms=downlink.get("jitter_ms"),
            packet_loss=downlink.get("packet_loss"),
            burst_loss_len=downlink.get("burst_loss_len"),
            rate=downlink.get("rate"),
        )
    if correlated_loss is not None:
        if not isinstance(correlated_loss, dict):
            raise ValueError("correlated_loss must be a mapping when provided")
        policy["correlated_loss_profile"] = _build_correlated_loss_profile(
            p_good_to_bad=correlated_loss.get("p_good_to_bad", 0),
            p_bad_to_good=correlated_loss.get("p_bad_to_good", 0),
            loss_good=correlated_loss.get("loss_good", 0),
            loss_bad=correlated_loss.get("loss_bad", 0),
        )
    if connection_error is not None:
        if not isinstance(connection_error, dict):
            raise ValueError("connection_error must be a mapping when provided")
        policy["connection_error_profile"] = _build_connection_error_profile(
            kind=connection_error.get("kind", "reset"),
            prob=connection_error.get("prob", "100%"),
        )
    if half_open is not None:
        if not isinstance(half_open, dict):
            raise ValueError("half_open must be a mapping when provided")
        policy["half_open_profile"] = _build_half_open_profile(
            after_bytes=half_open.get("after_bytes", 0),
            error=half_open.get("error", "reset"),
        )
    if packet_duplicate is not None:
        if not isinstance(packet_duplicate, dict):
            raise ValueError("packet_duplicate must be a mapping when provided")
        policy["packet_duplicate_profile"] = _build_packet_duplicate_profile(
            prob=packet_duplicate.get("prob", "100%"),
            max_extra=packet_duplicate.get("max_extra", 1),
        )
    if packet_reorder is not None:
        if not isinstance(packet_reorder, dict):
            raise ValueError("packet_reorder must be a mapping when provided")
        policy["packet_reorder_profile"] = _build_packet_reorder_profile(
            prob=packet_reorder.get("prob", "100%"),
            max_delay_ms=packet_reorder.get("max_delay_ms", 0),
            window=packet_reorder.get("window", 1),
        )
    dns_profile = _build_dns_profile(
        delay_ms=dns_delay_ms,
        timeout_ms=dns_timeout_ms,
        nxdomain=dns_nxdomain,
    )
    if dns_profile:
        policy["dns_profile"] = dns_profile
    if target is not None:
        if isinstance(target, str):
            policy["target_profile"] = _build_target_profile(target=target)
        elif isinstance(target, dict):
            policy["target_profile"] = _build_target_profile(
                target=target.get("target"),
                host=target.get("host"),
                cidr=target.get("cidr"),
                port=target.get("port"),
                protocol=target.get("protocol"),
            )
        else:
            raise ValueError("target must be a string or mapping when provided")
    if targets is not None:
        if not isinstance(targets, list) or not targets:
            raise ValueError("targets must be a non-empty list when provided")
        built_rules: list[dict[str, int]] = []
        for entry in targets:
            if isinstance(entry, str):
                built_rules.append(_build_target_profile(target=entry))
            elif isinstance(entry, dict):
                built_rules.append(
                    _build_target_profile(
                        target=entry.get("target"),
                        host=entry.get("host"),
                        cidr=entry.get("cidr"),
                        port=entry.get("port"),
                        protocol=entry.get("protocol"),
                        priority=entry.get("priority"),
                    )
                )
            else:
                raise ValueError("each targets entry must be a string or mapping")
        policy["target_profiles"] = sorted(
            built_rules,
            key=lambda profile: profile.get("priority", 100),
            reverse=True,
        )
    if schedule is not None:
        if not isinstance(schedule, dict):
            raise ValueError("schedule must be a mapping when provided")
        policy["schedule_profile"] = _build_schedule_profile(
            kind=schedule.get("kind", ""),
            every_s=schedule.get("every_s"),
            duration_s=schedule.get("duration_s"),
            on_s=schedule.get("on_s"),
            off_s=schedule.get("off_s"),
            ramp_s=schedule.get("ramp_s"),
        )
    with _POLICY_LOCK:
        _POLICY_REGISTRY[name] = policy


def clear_policies() -> None:
    with _POLICY_LOCK:
        _POLICY_REGISTRY.clear()


def list_policies() -> list[str]:
    with _POLICY_LOCK:
        return sorted(_POLICY_REGISTRY.keys())


def get_policy(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        policy = _POLICY_REGISTRY.get(name)
    if policy is None:
        return None
    return dict(policy)


def unregister_policy(name: str) -> bool:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.pop(name, None) is not None


def load_policies(path: str | Path) -> int:
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".json":
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except Exception as exc:
            raise ValueError("YAML support requires PyYAML installed") from exc
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    else:
        raise ValueError("Unsupported policy format; use .json, .yaml or .yml")

    if not isinstance(raw, dict):
        raise ValueError("Policy file must contain an object keyed by policy name")

    loaded = 0
    for name, cfg in raw.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            raise ValueError("Each policy entry must be a mapping")
        register_policy(
            name,
            latency_ms=cfg.get("latency_ms"),
            jitter_ms=cfg.get("jitter_ms"),
            packet_loss=cfg.get("packet_loss"),
            burst_loss_len=cfg.get("burst_loss_len"),
            rate=cfg.get("rate"),
            timeout_ms=cfg.get("timeout_ms"),
            connect_timeout_ms=cfg.get("connect_timeout_ms"),
            recv_timeout_ms=cfg.get("recv_timeout_ms"),
            uplink=cfg.get("uplink"),
            downlink=cfg.get("downlink"),
            correlated_loss=cfg.get("correlated_loss"),
            connection_error=cfg.get("connection_error"),
            half_open=cfg.get("half_open"),
            packet_duplicate=cfg.get("packet_duplicate"),
            packet_reorder=cfg.get("packet_reorder"),
            dns_delay_ms=cfg.get("dns_delay_ms"),
            dns_timeout_ms=cfg.get("dns_timeout_ms"),
            dns_nxdomain=cfg.get("dns_nxdomain"),
            target=cfg.get("target"),
            targets=cfg.get("targets"),
            schedule=cfg.get("schedule"),
        )
        loaded += 1
    return loaded


def set_thread_policy(policy_name: str | None) -> None:
    _THREAD_POLICY.set(policy_name)


def get_thread_policy() -> str | None:
    return _THREAD_POLICY.get()


def _run_sync_with_timeout(
    func: Callable[..., Any],
    timeout_ms: int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer"):
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def handler(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

        signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000)
        try:
            return func(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_handler)

    outcome: dict[str, Any] = {}
    completed = threading.Event()

    def run_target() -> None:
        try:
            outcome["result"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            outcome["error"] = exc
        finally:
            completed.set()

    worker = threading.Thread(target=run_target, daemon=True)
    worker.start()
    if not completed.wait(timeout_ms / 1000):
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")
