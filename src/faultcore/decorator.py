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
    build_dns_profile as _build_dns_profile,
    build_half_open_profile as _build_half_open_profile,
    build_packet_duplicate_profile as _build_packet_duplicate_profile,
    build_packet_reorder_profile as _build_packet_reorder_profile,
    build_session_budget_profile as _build_session_budget_profile,
    build_timeout_profile as _build_timeout_profile,
    parse_burst_loss as _parse_burst_loss,
    parse_duration as _parse_duration,
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
    direction_profile: dict[str, Any] = {}

    if latency is not None:
        direction_profile["latency"] = _parse_duration(latency)
    if jitter is not None:
        direction_profile["jitter"] = _parse_duration(jitter)
    if packet_loss is not None:
        direction_profile["packet_loss_ppm"] = _parse_packet_loss(packet_loss)
    if burst_loss is not None:
        direction_profile["burst_loss"] = _parse_burst_loss(burst_loss)
    if rate is not None:
        direction_profile["rate"] = _parse_rate(rate)
    return _with_wrapper(**{field_name: direction_profile})


_POLICY_FIELDS = (
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
    return {f: policy.get(f) for f in _POLICY_FIELDS if f in policy}


def _resolve_runtime_policy_name(policy_name: str) -> str:
    return policy_name if policy_name != "auto" else (get_thread_policy() or "")


def _require_non_negative(value: int, *, field_name: str) -> int:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


class FaultWrapper:
    """Wrapper that applies fault profiles from shared memory before calling the function."""

    def __init__(self, func: Callable[..., Any], policy_name: str | None = None, **profiles: Any):
        functools.update_wrapper(self, func)
        self._func = func
        self._policy_name = policy_name
        self._profiles = profiles

    def __getattr__(self, name: str) -> Any:
        return getattr(self._func, name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        # Support instance methods
        return self if obj is None else functools.partial(self.__call__, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tid = threading.get_native_id()
        shm = get_shm_writer()
        async_handoff = False
        try:
            if self._policy_name:
                shm.write_policy_name(self._policy_name)

            apply_fault_profiles(shm, tid, self._profiles, started_monotonic_ns=time.monotonic_ns())

            result = self._func(*args, **kwargs)

            if not inspect.isawaitable(result):
                return result

            async_handoff = True
            return self._run_async(result, shm, tid)
        finally:
            if not async_handoff:
                shm.clear(tid)

    async def _run_async(self, awaitable_result: Any, shm: Any, tid: int) -> Any:
        try:
            return await awaitable_result
        finally:
            shm.clear(tid)

    def __repr__(self) -> str:
        profiles_str = ", ".join(f"{k}={v}" for k, v in self._profiles.items() if v)
        return f"<FaultWrapper({profiles_str}) for {self._func!r}>"


def latency(t: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(latency=_parse_duration(t))


def jitter(t: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(jitter=_parse_duration(t))


def packet_loss(p: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_loss_ppm=_parse_packet_loss(p))


def burst_loss(n: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(burst_loss=_parse_burst_loss(n))


def rate(r: str, /) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(rate=_parse_rate(r))


def timeout(*, connect: str | None = None, recv: str | None = None) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(timeouts=_build_timeout_profile(connect=connect, recv=recv))


def dns(
    *, delay: str | None = None, timeout: str | None = None, nxdomain: str | None = None
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
    *, p_good_to_bad: str, p_bad_to_good: str, loss_good: str, loss_bad: str
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        correlated_loss_profile=_build_correlated_loss_profile(
            p_good_to_bad=p_good_to_bad, p_bad_to_good=p_bad_to_good, loss_good=loss_good, loss_bad=loss_bad
        )
    )


def connection_error(*, kind: str, prob: str = "100%") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(connection_error_profile=_build_connection_error_profile(kind=kind, prob=prob))


def half_open(*, after: str, error: str = "reset") -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(half_open_profile=_build_half_open_profile(after=after, error=error))


def packet_duplicate(*, prob: str = "100%", max_extra: int = 1) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(packet_duplicate_profile=_build_packet_duplicate_profile(prob=prob, max_extra=max_extra))


def packet_reorder(
    *, prob: str = "100%", max_delay: str = "0ms", window: int = 1
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        packet_reorder_profile=_build_packet_reorder_profile(prob=prob, max_delay=max_delay, window=window)
    )


def fault(policy_name: str = "auto") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Universal decorator to apply a policy by name (or from thread context)."""

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
