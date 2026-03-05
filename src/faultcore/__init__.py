import contextvars
import os
from pathlib import Path

from faultcore._faultcore import (
    CallContext,
    CircuitBreakerPolicy as CircuitBreaker,
    ContextManager,
    FallbackPolicy as Fallback,
    FeatureFlagManager,
    NetworkQueuePolicy as NetworkQueue,
    PolicyRegistry,
    RateLimitPolicy as RateLimit,
    RetryPolicy as Retry,
    TimeoutPolicy as Timeout,
    add_keys,
    classify_exception,
    clear_keys,
    get_feature_flag_manager as _get_feature_flag_manager,
    get_keys,
    get_policy_registry,
    remove_key,
    set_thread_policy as _set_thread_policy,
)
from faultcore.decorator import (
    apply_policy,
    circuit_breaker,
    fallback,
    fault,
    network_queue,
    rate_limit,
    retry,
    timeout,
)

_FAULTCORE_CONTEXT_KEYS = contextvars.ContextVar("faultcore_context_keys", default=None)

_cached_feature_flag_manager: FeatureFlagManager | None = None


def get_feature_flag_manager() -> FeatureFlagManager:
    global _cached_feature_flag_manager
    if _cached_feature_flag_manager is None:
        _cached_feature_flag_manager = _get_feature_flag_manager()
    return _cached_feature_flag_manager


def is_interceptor_loaded() -> bool:
    return "LD_PRELOAD" in os.environ


def get_interceptor_path() -> str | None:
    filename = "libfaultcore_interceptor.so"

    for base in [Path.cwd(), Path(__file__).parent.parent]:
        for subpath in ["", "target/release/", "target/debug/"]:
            path = base / subpath / filename
            if path.exists():
                return str(path)
    return None


def register_policy_bundle(
    key: str,
    timeout_ms: int | None = None,
    retry_max_retries: int | None = None,
    retry_backoff_ms: int | None = None,
    retry_on: list[str] | None = None,
    circuit_breaker_failure_threshold: int | None = None,
    circuit_breaker_success_threshold: int | None = None,
    circuit_breaker_timeout_ms: int | None = None,
    rate_limit_rate: float | None = None,
    rate_limit_capacity: int | None = None,
) -> None:
    manager = get_feature_flag_manager()
    manager.register(
        key,
        timeout_ms,
        retry_max_retries,
        retry_backoff_ms,
        retry_on,
        circuit_breaker_failure_threshold,
        circuit_breaker_success_threshold,
        circuit_breaker_timeout_ms,
        rate_limit_rate,
        rate_limit_capacity,
    )


def update_policy_bundle(
    key: str,
    timeout_ms: int | None = None,
    retry_max_retries: int | None = None,
    retry_backoff_ms: int | None = None,
    retry_on: list[str] | None = None,
    circuit_breaker_failure_threshold: int | None = None,
    circuit_breaker_success_threshold: int | None = None,
    circuit_breaker_timeout_ms: int | None = None,
    rate_limit_rate: float | None = None,
    rate_limit_capacity: int | None = None,
) -> bool:
    manager = get_feature_flag_manager()
    return manager.update(
        key,
        timeout_ms,
        retry_max_retries,
        retry_backoff_ms,
        retry_on,
        circuit_breaker_failure_threshold,
        circuit_breaker_success_threshold,
        circuit_breaker_timeout_ms,
        rate_limit_rate,
        rate_limit_capacity,
    )


class fault_context:
    """Context manager to set the call context and optionally override the policy."""

    def __init__(
        self,
        policy_name: str | None = None,
        host: str | None = None,
        path: str | None = None,
        method: str | None = None,
        headers: dict | None = None,
    ):
        self.policy_name = policy_name
        self.host = host
        self.path = path
        self.method = method
        self.headers = headers
        self._prev_policy = None
        self._prev_ctx = None

    def __enter__(self):
        registry = get_policy_registry()
        self._prev_policy = registry.get_thread_policy()
        if self.policy_name is not None:
            registry.set_thread_policy(self.policy_name)

        # In a real implementation, we would also set the host/path/headers in a thread-local or contextvar
        # For now, we'll focus on the policy override as that's what's currently supported in the Rust side.
        # Phase 2 rule matching will use the CallContext passed to execute_policy.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        registry = get_policy_registry()
        registry.set_thread_policy(self._prev_policy)


def set_thread_policy(policy_name: str | None):
    """Set the policy override for the current thread."""
    _set_thread_policy(policy_name)


__all__ = [
    "Timeout",
    "Retry",
    "Fallback",
    "CircuitBreaker",
    "RateLimit",
    "NetworkQueue",
    "CallContext",
    "ContextManager",
    "FeatureFlagManager",
    "PolicyRegistry",
    "classify_exception",
    "add_keys",
    "get_keys",
    "remove_key",
    "clear_keys",
    "get_feature_flag_manager",
    "register_policy_bundle",
    "update_policy_bundle",
    "timeout",
    "retry",
    "fallback",
    "circuit_breaker",
    "rate_limit",
    "network_queue",
    "apply_policy",
    "fault",
    "fault_context",
    "set_thread_policy",
    "is_interceptor_loaded",
]
