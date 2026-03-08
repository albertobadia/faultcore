import contextvars
import os
from pathlib import Path

from faultcore._faultcore import (
    CallContext,
    ContextManager,
    FeatureFlagManager,
    PolicyRegistry,
    RateLimitPolicy as RateLimit,
    TimeoutPolicy as Timeout,
    add_keys,
    clear_keys,
    get_feature_flag_manager as _get_feature_flag_manager,
    get_keys,
    get_policy_registry,
    remove_key,
    set_thread_policy as _set_thread_policy,
)
from faultcore.decorator import (
    apply_policy,
    fault,
    rate_limit,
    timeout,
)

_FAULTCORE_CONTEXT_KEYS = contextvars.ContextVar("faultcore_context_keys", default=None)
_FAULTCORE_THREAD_POLICY = contextvars.ContextVar("faultcore_thread_policy", default=None)

_cached_feature_flag_manager: FeatureFlagManager | None = None


def get_feature_flag_manager() -> FeatureFlagManager:
    global _cached_feature_flag_manager
    if _cached_feature_flag_manager is None:
        _cached_feature_flag_manager = _get_feature_flag_manager()
    return _cached_feature_flag_manager


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


def register_policy_bundle(
    key: str,
    timeout_ms: int | None = None,
    rate_limit_rate: int | None = None,
    rate_limit_capacity: int | None = None,
) -> None:
    get_feature_flag_manager().register(key, timeout_ms, rate_limit_rate, rate_limit_capacity)


def update_policy_bundle(
    key: str,
    timeout_ms: int | None = None,
    rate_limit_rate: int | None = None,
    rate_limit_capacity: int | None = None,
) -> bool:
    return get_feature_flag_manager().update(key, timeout_ms, rate_limit_rate, rate_limit_capacity)


class fault_context:
    def __init__(self, policy_name: str | None = None, **_kwargs):
        self.policy_name = policy_name
        self._token = None

    def __enter__(self):
        self._token = _FAULTCORE_THREAD_POLICY.set(self.policy_name)
        try:
            _set_thread_policy(self.policy_name)
        except Exception:
            _FAULTCORE_THREAD_POLICY.reset(self._token)
            self._token = None
            raise
        return self

    def __exit__(self, *_args):
        if self._token:
            _FAULTCORE_THREAD_POLICY.reset(self._token)
            _set_thread_policy(None)


def set_thread_policy(policy_name: str | None):
    _set_thread_policy(policy_name)


__all__ = [
    "Timeout",
    "RateLimit",
    "CallContext",
    "ContextManager",
    "FeatureFlagManager",
    "PolicyRegistry",
    "get_policy_registry",
    "add_keys",
    "get_keys",
    "remove_key",
    "clear_keys",
    "get_feature_flag_manager",
    "register_policy_bundle",
    "update_policy_bundle",
    "timeout",
    "rate_limit",
    "apply_policy",
    "fault",
    "fault_context",
    "set_thread_policy",
    "is_interceptor_loaded",
]
