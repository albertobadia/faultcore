import functools
import inspect
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faultcore import policy_registry as _policy_registry
from faultcore.decorator_helpers import apply_fault_profiles
from faultcore.policy_registry import get_policy_for_apply
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


def _with_wrapper(**wrapper_kwargs: Any) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, **wrapper_kwargs)

    return decorator


def _build_directional_profile_or_raise(
    direction_name: str,
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> dict[str, int]:
    profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not profile:
        raise ValueError(f"{direction_name} requires at least one directional field")
    return profile


def _with_directional_profile(
    *,
    field_name: str,
    direction_name: str,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    direction_profile = _build_directional_profile_or_raise(
        direction_name,
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    return _with_wrapper(**{field_name: direction_profile})


_POLICY_WRAPPER_FIELDS = (
    "seed",
    "latency_ms",
    "jitter_ms",
    "packet_loss_ppm",
    "burst_loss_len",
    "bandwidth_bps",
    "timeouts",
    "uplink_profile",
    "downlink_profile",
    "correlated_loss_profile",
    "connection_error_profile",
    "half_open_profile",
    "packet_duplicate_profile",
    "packet_reorder_profile",
    "dns_profile",
    "target_profile",
    "target_profiles",
    "schedule_profile",
    "session_budget_profile",
)


def _policy_to_wrapper_kwargs(policy: dict[str, Any]) -> dict[str, Any]:
    return {field: policy.get(field) for field in _POLICY_WRAPPER_FIELDS}


def _resolve_runtime_policy_name(policy_name: str) -> str:
    return policy_name if policy_name != "auto" else (get_thread_policy() or "")


def _with_dns_profile(**dns_kwargs: int | str | float) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    return _with_wrapper(dns_profile=_build_dns_profile(**dns_kwargs))


def _require_non_negative(value: int, *, field_name: str) -> int:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


class FaultWrapper:
    def __init__(
        self,
        func: Callable[..., Any],
        seed: int | None = None,
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
        session_budget_profile: dict[str, int] | None = None,
    ):
        functools.update_wrapper(self, func)
        self._func = func
        self._seed = seed
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
        self._session_budget_profile = session_budget_profile or {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._func, name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        return self if obj is None else functools.partial(self.__call__, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tid = threading.get_native_id()
        shm = get_shm_writer()
        async_handoff = False
        try:
            apply_fault_profiles(shm, tid, self, started_monotonic_ns=time.monotonic_ns())

            result = self._func(*args, **kwargs)

            if not inspect.isawaitable(result):
                return result

            async_handoff = True
            return self._run_async(result, shm, tid)
        finally:
            if not async_handoff:
                shm.clear(tid)

    async def _run_async(
        self,
        awaitable_result: Any,
        shm: Any,
        tid: int,
    ) -> Any:
        try:
            return await awaitable_result
        finally:
            shm.clear(tid)

    def __repr__(self) -> str:
        return (
            "<FaultWrapper("
            f"seed={self._seed}, "
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
            f"schedule={self._schedule_profile}, "
            f"session_budget={self._session_budget_profile}) for {self._func!r}>"
        )


def latency(latency_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(latency_ms=_require_non_negative(latency_ms, field_name="latency"))


def jitter(jitter_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(jitter_ms=_require_non_negative(jitter_ms, field_name="jitter"))


def connect_timeout(timeout_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(timeouts=(_require_non_negative(timeout_ms, field_name="connect_timeout"), 0))


def recv_timeout(timeout_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(timeouts=(0, _require_non_negative(timeout_ms, field_name="recv_timeout")))


def rate_limit(rate: str | int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(bandwidth_bps=_parse_rate(rate))


def packet_loss(loss: str | int | float) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_loss_ppm=_parse_packet_loss(loss))


def burst_loss(length: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(burst_loss_len=_require_non_negative(int(length), field_name="burst_loss length"))


def uplink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_directional_profile(
        field_name="uplink_profile",
        direction_name="uplink",
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )


def downlink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_directional_profile(
        field_name="downlink_profile",
        direction_name="downlink",
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )


def correlated_loss(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        correlated_loss_profile=_build_correlated_loss_profile(
            p_good_to_bad=p_good_to_bad,
            p_bad_to_good=p_bad_to_good,
            loss_good=loss_good,
            loss_bad=loss_bad,
        )
    )


def connection_error(*, kind: str, prob: str | int | float = "100%") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(connection_error_profile=_build_connection_error_profile(kind=kind, prob=prob))


def half_open(*, after_bytes: int, error: str = "reset") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(half_open_profile=_build_half_open_profile(after_bytes=after_bytes, error=error))


def packet_duplicate(
    *,
    prob: str | int | float = "100%",
    max_extra: int = 1,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_duplicate_profile=_build_packet_duplicate_profile(prob=prob, max_extra=max_extra))


def packet_reorder(
    *,
    prob: str | int | float = "100%",
    max_delay_ms: int = 0,
    window: int = 1,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        packet_reorder_profile=_build_packet_reorder_profile(
            prob=prob,
            max_delay_ms=max_delay_ms,
            window=window,
        )
    )


def dns_delay(delay_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_dns_profile(delay_ms=delay_ms)


def dns_timeout(timeout_ms: int) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_dns_profile(timeout_ms=timeout_ms)


def dns_nxdomain(prob: str | int | float = "100%") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_dns_profile(nxdomain=prob)


def for_target(
    target: str | None = None,
    *,
    host: str | None = None,
    cidr: str | None = None,
    hostname: str | None = None,
    sni: str | None = None,
    port: int | None = None,
    port_start: int | None = None,
    port_end: int | None = None,
    protocol: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        target_profile=_build_target_profile(
            target=target,
            host=host,
            cidr=cidr,
            hostname=hostname,
            sni=sni,
            port=port,
            port_start=port_start,
            port_end=port_end,
            protocol=protocol,
        )
    )


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
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    schedule_profile = _build_schedule_profile(
        kind=kind,
        every_s=every_s,
        duration_s=duration_s,
        on_s=on_s,
        off_s=off_s,
        ramp_s=ramp_s,
    )
    direction_profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    return _with_wrapper(
        latency_ms=direction_profile.get("latency_ms"),
        jitter_ms=direction_profile.get("jitter_ms"),
        packet_loss_ppm=direction_profile.get("packet_loss_ppm"),
        burst_loss_len=direction_profile.get("burst_loss_len"),
        bandwidth_bps=direction_profile.get("bandwidth_bps"),
        schedule_profile=schedule_profile,
    )


def apply_policy(policy_name: str) -> Callable[[Callable[..., Any]], FaultWrapper]:
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        policy = get_policy_for_apply(policy_name)
        return FaultWrapper(func, **_policy_to_wrapper_kwargs(policy)) if policy else FaultWrapper(func)

    return decorator


def fault(policy_name: str = "auto") -> Callable[[Callable[..., Any]], FaultWrapper]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def runtime_dispatch(*args: Any, **kwargs: Any) -> Any:
            name = _resolve_runtime_policy_name(policy_name)
            policy = get_policy_for_apply(name) if name else None
            if policy is None:
                return func(*args, **kwargs)
            return FaultWrapper(func, **_policy_to_wrapper_kwargs(policy))(*args, **kwargs)

        return runtime_dispatch

    return decorator
