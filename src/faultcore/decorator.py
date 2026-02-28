import functools

from faultcore._faultcore import (
    CircuitBreakerPolicy,
    FallbackPolicy,
    RateLimitPolicy,
    RetryPolicy,
    TimeoutPolicy,
)


def timeout(timeout_ms: int):
    """Decorator that applies a timeout to a function.

    Args:
        timeout_ms: Timeout in milliseconds.

    Example:
        @faultcore.timeout(5000)
        def my_function():
            ...
    """
    policy = TimeoutPolicy(timeout_ms)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return policy(func, args, kwargs)

        wrapper._faultcore_policy = policy
        return wrapper

    return decorator


def retry(max_retries: int = 3, backoff_ms: int = 100, retry_on: list = None):
    """Decorator that retries a function on failure.

    Args:
        max_retries: Maximum number of retries.
        backoff_ms: Backoff time in milliseconds between retries.
        retry_on: List of error classes to retry on.

    Example:
        @faultcore.retry(3, backoff_ms=500)
        def my_function():
            ...
    """
    policy = RetryPolicy(max_retries, backoff_ms, retry_on)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return policy(func, args, kwargs)

        wrapper._faultcore_policy = policy
        return wrapper

    return decorator


def fallback(fallback_func):
    """Decorator that provides a fallback function on failure.

    Args:
        fallback_func: Function to call when the main function fails.

    Example:
        @faultcore.fallback(lambda: "default_value")
        def my_function():
            ...
    """
    policy = FallbackPolicy(fallback_func)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return policy(func, args, kwargs)

        wrapper._faultcore_policy = policy
        return wrapper

    return decorator


def circuit_breaker(failure_threshold: int = 5, success_threshold: int = 2, timeout_ms: int = 30000):
    """Decorator that implements a circuit breaker pattern.

    Args:
        failure_threshold: Number of failures before opening the circuit.
        success_threshold: Number of successes needed to close the circuit from half-open.
        timeout_ms: Time in milliseconds before attempting to close the circuit.

    Example:
        @faultcore.circuit_breaker(failure_threshold=5)
        def my_function():
            ...
    """
    policy = CircuitBreakerPolicy(failure_threshold, success_threshold, timeout_ms)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return policy(func, args, kwargs)

        wrapper._faultcore_policy = policy
        return wrapper

    return decorator


def rate_limit(rate: float, capacity: int):
    """Decorator that applies rate limiting to a function.

    Args:
        rate: Number of requests per second.
        capacity: Maximum burst capacity.

    Example:
        @faultcore.rate_limit(10.0, 100)
        def my_function():
            ...
    """
    policy = RateLimitPolicy(rate, capacity)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return policy(func, args, kwargs)

        wrapper._faultcore_policy = policy
        return wrapper

    return decorator
