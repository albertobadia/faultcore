import asyncio
import functools
import os
import pickle
import select
import signal
import threading
import time
from asyncio import iscoroutine, wait_for
from collections.abc import Callable
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any

from faultcore import metrics_runtime as _metrics_runtime, policy_registry as _policy_registry
from faultcore.metrics_runtime import (
    capture_metrics_context as _capture_metrics_context,
    restore_metrics_context as _restore_metrics_context,
)
from faultcore.policy_registry import (
    get_policy_for_apply,
)
from faultcore.profile_parsers import (
    build_connection_error_profile as _build_connection_error_profile,
    build_correlated_loss_profile as _build_correlated_loss_profile,
    build_direction_profile as _build_direction_profile,
    build_dns_profile as _build_dns_profile,
    build_half_open_profile as _build_half_open_profile,
    build_packet_duplicate_profile as _build_packet_duplicate_profile,
    build_packet_reorder_profile as _build_packet_reorder_profile,
    build_schedule_profile as _build_schedule_profile,
    build_target_profile as _build_target_profile,
    parse_packet_loss as _parse_packet_loss,
    parse_rate as _parse_rate,
)
from faultcore.shm_writer import get_shm_writer
from faultcore.wrapper_runtime import run_sync_with_timeout as _run_sync_with_timeout


def _read_fault_metrics_snapshot() -> dict[str, Any] | None:
    return _metrics_runtime.read_fault_metrics_snapshot()


def _get_metrics_context_baseline() -> dict[str, Any] | None:
    return _metrics_runtime.get_metrics_context_baseline()


def register_policy(*args: Any, **kwargs: Any) -> None:
    _policy_registry.register_policy(*args, **kwargs)


def clear_policies() -> None:
    _policy_registry.clear_policies()


def list_policies() -> list[str]:
    return _policy_registry.list_policies()


def get_policy(name: str) -> dict[str, Any] | None:
    return _policy_registry.get_policy(name)


def unregister_policy(name: str) -> bool:
    return _policy_registry.unregister_policy(name)


def load_policies(path: str | Path) -> int:
    return _policy_registry.load_policies(path)


def set_thread_policy(policy_name: str | None) -> None:
    _policy_registry.set_thread_policy(policy_name)


def get_thread_policy() -> str | None:
    return _policy_registry.get_thread_policy()


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
        target_profile: dict[str, Any] | None = None,
        target_profiles: list[dict[str, Any]] | None = None,
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
        async_handoff = False
        try:
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
                    address_family=self._target_profile.get("address_family", 0),
                    addr=self._target_profile.get("addr"),
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
                return _run_sync_with_timeout(
                    self._func,
                    timeout_ms,
                    args,
                    kwargs,
                    os_module=os,
                    signal_module=signal,
                    select_module=select,
                    pickle_module=pickle,
                )

            result = self._func(*args, **kwargs)

            if iscoroutine(result):
                async_handoff = True
                _restore_metrics_context(metrics_token)
                return self._run_async(result, shm, tid, timeout_ms)

            return result
        finally:
            if not async_handoff:
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
    direction_profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not direction_profile:
        raise ValueError("uplink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, uplink_profile=direction_profile)

    return decorator


def downlink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    direction_profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not direction_profile:
        raise ValueError("downlink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, downlink_profile=direction_profile)

    return decorator


def correlated_loss(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
):
    correlated_profile = _build_correlated_loss_profile(
        p_good_to_bad=p_good_to_bad,
        p_bad_to_good=p_bad_to_good,
        loss_good=loss_good,
        loss_bad=loss_bad,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, correlated_loss_profile=correlated_profile)

    return decorator


def connection_error(*, kind: str, prob: str | int | float = "100%"):
    connection_error_profile = _build_connection_error_profile(kind=kind, prob=prob)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, connection_error_profile=connection_error_profile)

    return decorator


def half_open(*, after_bytes: int, error: str = "reset"):
    half_open_profile = _build_half_open_profile(after_bytes=after_bytes, error=error)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, half_open_profile=half_open_profile)

    return decorator


def packet_duplicate(*, prob: str | int | float = "100%", max_extra: int = 1):
    duplicate_profile = _build_packet_duplicate_profile(prob=prob, max_extra=max_extra)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, packet_duplicate_profile=duplicate_profile)

    return decorator


def packet_reorder(
    *,
    prob: str | int | float = "100%",
    max_delay_ms: int = 0,
    window: int = 1,
):
    reorder_profile = _build_packet_reorder_profile(prob=prob, max_delay_ms=max_delay_ms, window=window)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, packet_reorder_profile=reorder_profile)

    return decorator


def dns_delay(delay_ms: int):
    dns_profile = _build_dns_profile(delay_ms=delay_ms)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=dns_profile)

    return decorator


def dns_timeout(timeout_ms: int):
    dns_profile = _build_dns_profile(timeout_ms=timeout_ms)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=dns_profile)

    return decorator


def dns_nxdomain(prob: str | int | float = "100%"):
    dns_profile = _build_dns_profile(nxdomain=prob)

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, dns_profile=dns_profile)

    return decorator


def for_target(
    target: str | None = None,
    *,
    host: str | None = None,
    cidr: str | None = None,
    port: int | None = None,
    protocol: str | None = None,
):
    target_profile = _build_target_profile(
        target=target,
        host=host,
        cidr=cidr,
        port=port,
        protocol=protocol,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, target_profile=target_profile)

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


def apply_policy(_key: str):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        policy = get_policy_for_apply(_key)
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
