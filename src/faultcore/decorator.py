import asyncio
import functools
import inspect
import sys

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
    retry_types = None
    if retry_on is not None:
        retry_types = []
        builtins = sys.modules.get("builtins")
        for type_or_str in retry_on:
            if isinstance(type_or_str, str):
                if builtins is not None and hasattr(builtins, type_or_str):
                    retry_types.append(getattr(builtins, type_or_str))
            else:
                retry_types.append(type_or_str)

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if retry_types is not None:
                    should_retry = any(isinstance(last_error, t) for t in retry_types)
                else:
                    should_retry = True

                if not should_retry or attempt == max_retries:
                    raise last_error from last_error

                await asyncio.sleep(backoff_ms / 1000.0)

        raise last_error

    wrapper._faultcore_policy = None
    return wrapper


class AsyncChaosWrapper:
    def __init__(self, coro, policy):
        self.coro = coro
        self.policy = policy
        self._entered = False
        self._has_context = hasattr(policy, "_enter_thread_context") and hasattr(policy, "_exit_thread_context")

    def __await__(self):
        return self

    def __iter__(self):
        return self

    def __next__(self):
        return self.send(None)

    def _enter_context(self):
        if self._has_context and not self._entered:
            self.policy._enter_thread_context()
            self._entered = True

    def _exit_context(self):
        if self._has_context and self._entered:
            self.policy._exit_thread_context()
            self._entered = False

    def send(self, value):
        self._enter_context()
        try:
            result = self.coro.send(value)
            self._exit_context()
            return result
        except StopIteration:
            self._exit_context()
            raise
        except BaseException:
            self._exit_context()
            raise

    def throw(self, typ, val=None, tb=None):
        self._enter_context()
        try:
            result = self.coro.throw(typ, val, tb)
            self._exit_context()
            return result
        except StopIteration:
            self._exit_context()
            raise
        except BaseException:
            self._exit_context()
            raise

    def close(self):
        self._exit_context()
        return self.coro.close()


def _wrap_async(policy, func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        coro = func(*args, **kwargs)
        return await AsyncChaosWrapper(coro, policy)

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
    rate: str = "1gbps",
    capacity: str = "10mb",
    max_queue_size: int = 1000,
    packet_loss: float = 0.0,
    latency_ms: int = 0,
):
    policy = NetworkQueuePolicy(
        rate=rate, capacity=capacity, max_queue_size=max_queue_size, packet_loss=packet_loss, latency_ms=latency_ms
    )
    return lambda func: _make_wrapper(policy, func)
