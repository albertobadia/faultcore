import os
from pathlib import Path
from typing import Any

from faultcore.decorator import (
    _capture_metrics_context as _capture_metrics_context_baseline,
    _get_metrics_context_baseline as _get_metrics_context_baseline,
    _read_fault_metrics_snapshot as _read_fault_metrics_snapshot,
    _restore_metrics_context as _restore_metrics_context_baseline,
    apply_policy,
    burst_loss,
    connect_timeout,
    connection_error,
    correlated_loss,
    dns_delay,
    dns_nxdomain,
    dns_timeout,
    downlink,
    fault,
    for_target,
    get_policy,
    get_thread_policy,
    half_open,
    jitter,
    latency,
    list_policies,
    load_policies,
    packet_duplicate,
    packet_loss,
    packet_reorder,
    profile,
    rate_limit,
    recv_timeout,
    register_policy,
    set_thread_policy as _set_thread_policy,
    timeout,
    unregister_policy,
    uplink,
)

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


def is_interceptor_loaded() -> bool:
    try:
        import ctypes

        return hasattr(ctypes.CDLL(None), "faultcore_interceptor_is_active")
    except Exception:
        return "LD_PRELOAD" in os.environ


def get_interceptor_path() -> str | None:
    lib_name = "libfaultcore_interceptor.so"
    search_dirs = [Path.cwd(), Path(__file__).parent.parent]
    sub_dirs = ["", "target/release", "target/debug"]

    for base in search_dirs:
        for sub in sub_dirs:
            path = base / sub / lib_name
            if path.exists():
                return str(path)
    return None


def _metrics_diff(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    base_by_stage = {item["stage"]: item for item in baseline.get("layers", [])}
    layers: list[dict[str, Any]] = []
    for current_layer in current.get("layers", []):
        stage = current_layer["stage"]
        base_layer = base_by_stage.get(stage, {})
        layer = {"stage": stage}
        for field in _METRICS_FIELDS:
            layer[field] = max(0, int(current_layer.get(field, 0)) - int(base_layer.get(field, 0)))
        layers.append(layer)
    totals = {field: sum(item[field] for item in layers) for field in _METRICS_FIELDS}
    return {
        "layers": layers,
        "totals": totals,
        "reload_applied": max(
            0,
            int(current.get("reload_applied", 0)) - int(baseline.get("reload_applied", 0)),
        ),
        "reload_retry": max(
            0,
            int(current.get("reload_retry", 0)) - int(baseline.get("reload_retry", 0)),
        ),
    }


def get_fault_metrics(*, reset: bool = False, scope: str = "global") -> dict[str, Any]:
    if scope not in {"global", "context"}:
        raise ValueError("scope must be 'global' or 'context'")

    snapshot = _read_fault_metrics_snapshot()
    if snapshot is None:
        raise RuntimeError("faultcore_metrics_snapshot is not available; preload the interceptor first")

    if scope == "context":
        baseline = _get_metrics_context_baseline()
        if baseline is None:
            raise RuntimeError("no active fault metrics context for current task/thread")
        snapshot = _metrics_diff(snapshot, baseline)

    if reset:
        import ctypes

        lib = ctypes.CDLL(None)
        if not hasattr(lib, "faultcore_metrics_reset"):
            raise RuntimeError("faultcore_metrics_reset is not available; preload the interceptor first")
        lib.faultcore_metrics_reset()

    return snapshot


class fault_context:
    def __init__(self, policy_name: str | None = None, **_kwargs):
        self.policy_name = policy_name
        self._previous: str | None = None
        self._metrics_token = None

    def __enter__(self):
        self._previous = get_thread_policy()
        self._metrics_token = _capture_metrics_context_baseline()
        _set_thread_policy(self.policy_name)
        return self

    def __exit__(self, *_args):
        _set_thread_policy(self._previous)
        _restore_metrics_context_baseline(self._metrics_token)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)


def set_thread_policy(policy_name: str | None):
    _set_thread_policy(policy_name)


__all__ = [
    "timeout",
    "connect_timeout",
    "recv_timeout",
    "latency",
    "jitter",
    "packet_loss",
    "burst_loss",
    "correlated_loss",
    "connection_error",
    "half_open",
    "dns_delay",
    "dns_timeout",
    "dns_nxdomain",
    "for_target",
    "packet_duplicate",
    "packet_reorder",
    "profile",
    "uplink",
    "downlink",
    "rate_limit",
    "register_policy",
    "list_policies",
    "get_policy",
    "unregister_policy",
    "load_policies",
    "apply_policy",
    "fault",
    "fault_context",
    "set_thread_policy",
    "is_interceptor_loaded",
    "get_interceptor_path",
    "get_fault_metrics",
]
