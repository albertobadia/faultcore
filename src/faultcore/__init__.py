import os
from pathlib import Path

from faultcore.decorator import (
    apply_policy,
    burst_loss,
    connect_timeout,
    fault,
    get_thread_policy,
    jitter,
    latency,
    load_policies,
    packet_loss,
    rate_limit,
    recv_timeout,
    register_policy,
    set_thread_policy as _set_thread_policy,
    timeout,
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


class fault_context:
    def __init__(self, policy_name: str | None = None, **_kwargs):
        self.policy_name = policy_name
        self._previous: str | None = None

    def __enter__(self):
        self._previous = get_thread_policy()
        _set_thread_policy(self.policy_name)
        return self

    def __exit__(self, *_args):
        _set_thread_policy(self._previous)


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
    "rate_limit",
    "register_policy",
    "load_policies",
    "apply_policy",
    "fault",
    "fault_context",
    "set_thread_policy",
    "is_interceptor_loaded",
    "get_interceptor_path",
]
