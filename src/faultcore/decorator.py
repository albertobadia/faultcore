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
    build_session_budget_profile as _build_session_budget_profile,
    build_timeout_profile as _build_timeout_profile,
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
    packet_loss: str | None = None,
    burst_loss_len: int | None = None,
    rate: str | None = None,
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
    latency: str | None = None,
    jitter: str | None = None,
    packet_loss: str | None = None,
    burst_loss: str | None = None,
    rate: str | None = None,
) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    from faultcore.profile_parsers import (
        parse_burst_loss,
        parse_duration,
        parse_packet_loss,
        parse_rate,
    )

    direction_profile: dict[str, Any] = {}

    if latency is not None:
        direction_profile["latency"] = parse_duration(latency)
    if jitter is not None:
        direction_profile["jitter"] = parse_duration(jitter)
    if packet_loss is not None:
        direction_profile["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss is not None:
        direction_profile["burst_loss"] = parse_burst_loss(burst_loss)
    if rate is not None:
        direction_profile["rate"] = parse_rate(rate)

    return _with_wrapper(**{field_name: direction_profile})


_POLICY_WRAPPER_FIELDS = (
    "seed",
    "latency",
    "jitter",
    "packet_loss_ppm",
    "burst_loss",
    "rate",
    "timeouts",
    "uplink_profile",
    "downlink_profile",
    "correlated_loss_profile",
    "connection_error_profile",
    "half_open_profile",
    "packet_duplicate_profile",
    "packet_reorder_profile",
    "dns_profile",
    "target_profiles",
    "schedule_profile",
    "session_budget_profile",
)


def _policy_to_wrapper_kwargs(policy: dict[str, Any]) -> dict[str, Any]:
    return {field: policy.get(field) for field in _POLICY_WRAPPER_FIELDS}


def _resolve_runtime_policy_name(policy_name: str) -> str:
    return policy_name if policy_name != "auto" else (get_thread_policy() or "")


def _require_non_negative(value: int, *, field_name: str) -> int:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


class FaultWrapper:
    def __init__(
        self,
        func: Callable[..., Any],
        policy_name: str | None = None,
        seed: int | None = None,
        latency: int | None = None,
        jitter: int | None = None,
        packet_loss_ppm: int | None = None,
        burst_loss: int | None = None,
        rate: int | None = None,
        timeouts: tuple[int, int] | None = None,
        uplink_profile: dict[str, int] | None = None,
        downlink_profile: dict[str, int] | None = None,
        correlated_loss_profile: dict[str, int] | None = None,
        connection_error_profile: dict[str, int] | None = None,
        half_open_profile: dict[str, int] | None = None,
        packet_duplicate_profile: dict[str, int] | None = None,
        packet_reorder_profile: dict[str, int] | None = None,
        dns_profile: dict[str, int] | None = None,
        target_profiles: list[dict[str, Any]] | None = None,
        schedule_profile: dict[str, int] | None = None,
        session_budget_profile: dict[str, int] | None = None,
    ):
        functools.update_wrapper(self, func)
        self._func = func
        self._policy_name = policy_name
        self._seed = seed
        self._latency = latency
        self._jitter = jitter
        self._packet_loss_ppm = packet_loss_ppm
        self._burst_loss = burst_loss
        self._rate = rate
        self._timeouts = timeouts
        self._uplink_profile = uplink_profile or {}
        self._downlink_profile = downlink_profile or {}
        self._correlated_loss_profile = correlated_loss_profile or {}
        self._connection_error_profile = connection_error_profile or {}
        self._half_open_profile = half_open_profile or {}
        self._packet_duplicate_profile = packet_duplicate_profile or {}
        self._packet_reorder_profile = packet_reorder_profile or {}
        self._dns_profile = dns_profile or {}
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
            if self._policy_name:
                shm.write_policy_name(self._policy_name)
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
            f"latency={self._latency}, "
            f"jitter={self._jitter}, "
            f"packet_loss_ppm={self._packet_loss_ppm}, "
            f"burst_loss={self._burst_loss}, "
            f"rate={self._rate}, "
            f"timeouts={self._timeouts}, "
            f"uplink={self._uplink_profile}, "
            f"downlink={self._downlink_profile}, "
            f"correlated_loss={self._correlated_loss_profile}, "
            f"connection_error={self._connection_error_profile}, "
            f"half_open={self._half_open_profile}, "
            f"packet_duplicate={self._packet_duplicate_profile}, "
            f"packet_reorder={self._packet_reorder_profile}, "
            f"dns={self._dns_profile}, "
            f"targets={self._target_profiles}, "
            f"schedule={self._schedule_profile}, "
            f"session_budget={self._session_budget_profile}) for {self._func!r}>"
        )


def latency(t: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    from faultcore.profile_parsers import parse_duration

    return _with_wrapper(latency=parse_duration(t))


def jitter(t: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    from faultcore.profile_parsers import parse_duration

    return _with_wrapper(jitter=parse_duration(t))


def packet_loss(p: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_loss_ppm=_parse_packet_loss(p))


def burst_loss(n: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    from faultcore.profile_parsers import parse_burst_loss

    return _with_wrapper(burst_loss=parse_burst_loss(n))


def rate(r: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(rate=_parse_rate(r))


def timeout(
    *,
    connect: str | None = None,
    recv: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(timeouts=_build_timeout_profile(connect=connect, recv=recv))


def dns(
    *,
    delay: str | None = None,
    timeout: str | None = None,
    nxdomain: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(dns_profile=_build_dns_profile(delay=delay, timeout=timeout, nxdomain=nxdomain))


def session_budget(
    *,
    max_tx: str | None = None,
    max_rx: str | None = None,
    max_ops: int | None = None,
    max_duration: str | None = None,
    action: str = "drop",
    budget_timeout: str | None = None,
    error: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        session_budget_profile=_build_session_budget_profile(
            max_tx=max_tx,
            max_rx=max_rx,
            max_ops=max_ops,
            max_duration=max_duration,
            action=action,
            budget_timeout=budget_timeout,
            error=error,
        )
    )


def uplink(
    *,
    latency: str | None = None,
    jitter: str | None = None,
    packet_loss: str | None = None,
    burst_loss: str | None = None,
    rate: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_directional_profile(
        field_name="uplink_profile",
        direction_name="uplink",
        latency=latency,
        jitter=jitter,
        packet_loss=packet_loss,
        burst_loss=burst_loss,
        rate=rate,
    )


def downlink(
    *,
    latency: str | None = None,
    jitter: str | None = None,
    packet_loss: str | None = None,
    burst_loss: str | None = None,
    rate: str | None = None,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_directional_profile(
        field_name="downlink_profile",
        direction_name="downlink",
        latency=latency,
        jitter=jitter,
        packet_loss=packet_loss,
        burst_loss=burst_loss,
        rate=rate,
    )


def correlated_loss(
    *,
    p_good_to_bad: str,
    p_bad_to_good: str,
    loss_good: str,
    loss_bad: str,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        correlated_loss_profile=_build_correlated_loss_profile(
            p_good_to_bad=p_good_to_bad,
            p_bad_to_good=p_bad_to_good,
            loss_good=loss_good,
            loss_bad=loss_bad,
        )
    )


def connection_error(*, kind: str, prob: str = "100%") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(connection_error_profile=_build_connection_error_profile(kind=kind, prob=prob))


def half_open(*, after: str, error: str = "reset") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(half_open_profile=_build_half_open_profile(after=after, error=error))


def packet_duplicate(
    *,
    prob: str = "100%",
    max_extra: int = 1,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_duplicate_profile=_build_packet_duplicate_profile(prob=prob, max_extra=max_extra))


def packet_reorder(
    *,
    prob: str = "100%",
    max_delay: str = "0ms",
    window: int = 1,
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        packet_reorder_profile=_build_packet_reorder_profile(
            prob=prob,
            max_delay=max_delay,
            window=window,
        )
    )


def fault(policy_name: str = "auto") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def runtime_dispatch(*args: Any, **kwargs: Any) -> Any:
            name = _resolve_runtime_policy_name(policy_name)
            policy = get_policy_for_apply(name) if name else None
            if policy is None:
                return func(*args, **kwargs)
            kwargs_wrapper = _policy_to_wrapper_kwargs(policy)
            return FaultWrapper(func, policy_name=name, **kwargs_wrapper)(*args, **kwargs)

        return runtime_dispatch

    return decorator
