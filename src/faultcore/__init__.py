import os
from pathlib import Path

from faultcore._faultcore import (
    CircuitBreakerPolicy as CircuitBreaker,
    ContextManager,
    FallbackPolicy as Fallback,
    NetworkQueuePolicy as NetworkQueue,
    RateLimitPolicy as RateLimit,
    RetryPolicy as Retry,
    TimeoutPolicy as Timeout,
    add_keys,
    classify_exception,
    clear_keys,
    get_keys,
    remove_key,
)
from faultcore.decorator import (
    circuit_breaker,
    fallback,
    network_queue,
    rate_limit,
    retry,
    timeout,
)


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


__all__ = [
    "Timeout",
    "Retry",
    "Fallback",
    "CircuitBreaker",
    "RateLimit",
    "NetworkQueue",
    "ContextManager",
    "classify_exception",
    "add_keys",
    "get_keys",
    "remove_key",
    "clear_keys",
    "timeout",
    "retry",
    "fallback",
    "circuit_breaker",
    "rate_limit",
    "network_queue",
    "is_interceptor_loaded",
]
