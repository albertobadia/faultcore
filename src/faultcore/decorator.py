import asyncio
import functools
import inspect

from faultcore._faultcore import (
    CircuitBreakerPolicy,
    FallbackPolicy,
    NetworkQueuePolicy,
    RateLimitPolicy,
    RetryPolicy,
    TimeoutPolicy,
)


def _is_async(func):
    return inspect.iscoroutinefunction(func)


def _wrap_sync(policy, func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return policy(func, args, kwargs)

    wrapper._faultcore_policy = policy
    return wrapper


def _wrap_retry_async(max_retries, backoff_ms, retry_on, func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if retry_on is not None:
                    should_retry = any(isinstance(last_error, type_to_check) for type_to_check in retry_on)
                else:
                    should_retry = True

                if not should_retry or attempt == max_retries:
                    raise last_error from last_error

                await asyncio.sleep(backoff_ms / 1000.0)

        raise last_error

    wrapper._faultcore_policy = None
    return wrapper


def _wrap_async(policy, func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await policy(func, args, kwargs)

    wrapper._faultcore_policy = policy
    return wrapper


def _make_wrapper(policy, func, retry_max_retries=None, retry_backoff_ms=None, retry_retry_on=None):
    if _is_async(func):
        if retry_max_retries is not None:
            return _wrap_retry_async(retry_max_retries, retry_backoff_ms, retry_retry_on, func)
        return _wrap_async(policy, func)
    return _wrap_sync(policy, func)


def timeout(timeout_ms: int):
    policy = TimeoutPolicy(timeout_ms)
    return lambda func: _make_wrapper(policy, func)


def retry(max_retries: int = 3, backoff_ms: int = 100, retry_on: list = None):
    if retry_on:
        retry_on_tuple = tuple(retry_on)
    else:
        retry_on_tuple = None

    policy = RetryPolicy(max_retries, backoff_ms, retry_on)
    return lambda func: _make_wrapper(policy, func, max_retries, backoff_ms, retry_on_tuple)


def fallback(fallback_func):
    policy = FallbackPolicy(fallback_func)
    return lambda func: _make_wrapper(policy, func)


def circuit_breaker(failure_threshold: int = 5, success_threshold: int = 2, timeout_ms: int = 30000):
    policy = CircuitBreakerPolicy(failure_threshold, success_threshold, timeout_ms)
    return lambda func: _make_wrapper(policy, func)


def rate_limit(rate: float, capacity: int):
    policy = RateLimitPolicy(rate, capacity)
    return lambda func: _make_wrapper(policy, func)


def network_queue(
    rate: float = 100.0,
    capacity: int = 100,
    max_queue_size: int = 1000,
    latency_min_ms: int = 0,
    latency_max_ms: int = 100,
    packet_loss_rate: float = 0.0,
    strategy: str = "wait",
    fd_limit: int = 1024,
):
    policy = NetworkQueuePolicy(
        rate,
        capacity,
        max_queue_size,
        latency_min_ms,
        latency_max_ms,
        packet_loss_rate,
        strategy,
        fd_limit,
    )
    return lambda func: _make_wrapper(policy, func)
