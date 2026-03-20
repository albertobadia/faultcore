import functools
import inspect
import threading
import time
from collections.abc import Callable
from typing import Any

from faultcore.decorator_helpers import apply_fault_profiles
from faultcore.policy_registry import (
    clear_policies,
    get_policy,
    get_policy_for_apply,
    get_thread_policy,
    list_policies,
    load_policies,
    register_policy,
    set_thread_policy,
    unregister_policy,
)
from faultcore.profile_parsers import (
    build_connection_error_profile as _build_connection_error_profile,
    build_correlated_loss_profile as _build_correlated_loss_profile,
    build_dns_profile as _build_dns_profile,
    build_half_open_profile as _build_half_open_profile,
    build_packet_duplicate_profile as _build_packet_duplicate_profile,
    build_packet_reorder_profile as _build_packet_reorder_profile,
    build_payload_mutation_profile as _build_payload_mutation_profile,
    build_session_budget_profile as _build_session_budget_profile,
    build_timeout_profile as _build_timeout_profile,
    parse_burst_loss as _parse_burst_loss,
    parse_duration as _parse_duration,
    parse_packet_loss as _parse_packet_loss,
    parse_rate as _parse_rate,
)
from faultcore.shm_writer import get_shm_writer


def _with_wrapper(**kwargs: Any) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    return lambda func: FaultWrapper(func, **kwargs)


_DIRECTIONAL_PROFILE_PARSERS = {
    "latency": _parse_duration,
    "jitter": _parse_duration,
    "packet_loss": _parse_packet_loss,
    "burst_loss": _parse_burst_loss,
    "rate": _parse_rate,
}


def _with_directional_profile(
    field_name: str, **profiles: str | None
) -> Callable[[Callable[..., Any]], "FaultWrapper"]:
    parsed: dict[str, Any] = {}

    for name, value in profiles.items():
        if value is None:
            continue
        parser = _DIRECTIONAL_PROFILE_PARSERS.get(name)
        if parser is None:
            continue
        key = f"{name}_ppm" if name == "packet_loss" else name
        parsed[key] = parser(value)

    return _with_wrapper(**{field_name: parsed})


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
    "payload_mutation_profile",
)


class FaultWrapper:
    def __init__(self, func: Callable[..., Any], policy_name: str | None = None, **profiles: Any):
        functools.update_wrapper(self, func)
        self._func = func
        self._policy_name = policy_name
        self._profiles = profiles

    def __getattr__(self, name: str) -> Any:
        return getattr(self._func, name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        shm = get_shm_writer()
        tid = threading.get_native_id()

        if self._policy_name:
            shm.write_policy_name(self._policy_name)

        keeps_shm_until_await = False
        try:
            apply_fault_profiles(shm, tid, self._profiles, started_monotonic_ns=time.monotonic_ns())
            result = self._func(*args, **kwargs)
            if inspect.isawaitable(result):
                keeps_shm_until_await = True
                return self._run_async(result, shm, tid)
            return result
        finally:
            if not keeps_shm_until_await:
                shm.clear(tid)

    async def _run_async(self, awaitable: Any, shm: Any, tid: int) -> Any:
        try:
            return await awaitable
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


def payload_mutation(
    *,
    enabled: bool,
    prob: str = "100%",
    type: str,
    target: str = "both",
    truncate_size: str | None = None,
    corrupt_count: int | None = None,
    corrupt_seed: str | int | None = None,
    inject_position: int | None = None,
    inject_data: str | bytes | None = None,
    replace_find: str | bytes | None = None,
    replace_with: str | bytes | None = None,
    swap_pos1: int | None = None,
    swap_pos2: int | None = None,
    min_size: str | None = None,
    max_size: str | None = None,
    every_n_packets: int = 1,
    dry_run: bool = False,
    max_buffer_size: str = "64kb",
) -> Callable[[Callable[..., Any]], FaultWrapper]:
    return _with_wrapper(
        payload_mutation_profile=_build_payload_mutation_profile(
            enabled=enabled,
            prob=prob,
            type=type,
            target=target,
            truncate_size=truncate_size,
            corrupt_count=corrupt_count,
            corrupt_seed=corrupt_seed,
            inject_position=inject_position,
            inject_data=inject_data,
            replace_find=replace_find,
            replace_with=replace_with,
            swap_pos1=swap_pos1,
            swap_pos2=swap_pos2,
            min_size=min_size,
            max_size=max_size,
            every_n_packets=every_n_packets,
            dry_run=dry_run,
            max_buffer_size=max_buffer_size,
        )
    )


def fault(policy_name: str = "auto") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved_policy_name = policy_name if policy_name != "auto" else (get_thread_policy() or "")
            policy = get_policy_for_apply(resolved_policy_name) if resolved_policy_name else None

            if not policy:
                return func(*args, **kwargs)

            profiles = {field: policy[field] for field in _POLICY_FIELDS if field in policy}
            wrapped = FaultWrapper(func, policy_name=resolved_policy_name, **profiles)
            return wrapped(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "burst_loss",
    "clear_policies",
    "connection_error",
    "correlated_loss",
    "dns",
    "downlink",
    "fault",
    "get_policy",
    "get_thread_policy",
    "half_open",
    "jitter",
    "latency",
    "list_policies",
    "load_policies",
    "packet_duplicate",
    "packet_loss",
    "packet_reorder",
    "payload_mutation",
    "rate",
    "register_policy",
    "session_budget",
    "set_thread_policy",
    "timeout",
    "unregister_policy",
    "uplink",
]
