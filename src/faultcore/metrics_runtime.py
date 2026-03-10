import contextvars
from typing import Any

_METRICS_CONTEXT_BASELINE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "faultcore_metrics_context_baseline",
    default=None,
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


def read_fault_metrics_snapshot() -> dict[str, Any] | None:
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
            ("reload_applied_count", ctypes.c_uint64),
            ("reload_retry_count", ctypes.c_uint64),
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
    for idx in range(min(int(snapshot.len), 7)):
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
    return {
        "layers": layers,
        "totals": totals,
        "reload_applied": int(snapshot.reload_applied_count),
        "reload_retry": int(snapshot.reload_retry_count),
    }


def capture_metrics_context() -> contextvars.Token[dict[str, Any] | None] | None:
    snapshot = read_fault_metrics_snapshot()
    if snapshot is None:
        return None
    return _METRICS_CONTEXT_BASELINE.set(snapshot)


def restore_metrics_context(token: contextvars.Token[dict[str, Any] | None] | None) -> None:
    if token is None:
        return
    _METRICS_CONTEXT_BASELINE.reset(token)


def get_metrics_context_baseline() -> dict[str, Any] | None:
    return _METRICS_CONTEXT_BASELINE.get()
