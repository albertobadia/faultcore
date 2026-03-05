import asyncio
import functools
import inspect
import time
import uuid

from faultcore._faultcore import classify_exception, get_policy_registry


def _is_async(func):
    if inspect.iscoroutinefunction(func):
        return True
    if callable(func):
        return inspect.iscoroutinefunction(func.__call__)
    return False


def _get_registry():
    return get_policy_registry()


def _create_sync_wrapper(func, policy):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return policy(func, args, kwargs)

    return wrapper


def _create_simple_async_wrapper(func):
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        return await async_wrapper._wrapped_func(*args, **kwargs)

    async_wrapper._wrapped_func = func
    async_wrapper.__name__ = func.__name__
    async_wrapper.__doc__ = getattr(func, "__doc__", None)
    return async_wrapper


def _attach_faultcore_attributes(wrapper, async_wrapper, func, policy):
    return async_wrapper if _is_async(func) else wrapper


def _decorate_func(func, policy, async_wrapper_generator=None):
    wrapper = _create_sync_wrapper(func, policy)
    if async_wrapper_generator:
        async_wrapper = async_wrapper_generator(func)
    else:
        async_wrapper = _create_simple_async_wrapper(func)
    return _attach_faultcore_attributes(wrapper, async_wrapper, func, policy)


def _should_retry(exception, retry_on):
    if retry_on is None:
        return True
    if isinstance(retry_on, list) and len(retry_on) == 0:
        return False
    exception_type = type(exception).__name__
    classified = classify_exception(exception)
    retry_on_lower = [r.lower() for r in retry_on]
    return exception_type.lower() in retry_on_lower or classified.lower() in retry_on_lower


def timeout(timeout_ms: int):
    def decorator(func):
        registry = _get_registry()
        func_id = id(func)
        policy_name = f"_timeout_{func_id}"
        registry.register_timeout_layer(policy_name, timeout_ms)
        if _is_async(func):
            return _FaultAsyncWrapper(func, policy_name, registry)
        return _FaultSyncWrapper(func, policy_name, registry)

    return decorator


def retry(max_retries: int = 3, backoff_ms: int = 100, retry_on: list = None):
    def decorator(func):
        registry = _get_registry()
        func_id = id(func)
        policy_name = f"_retry_{func_id}"
        retry_on_list = list(retry_on) if retry_on is not None else None
        registry.register_retry_layer(policy_name, max_retries, backoff_ms, retry_on_list)
        if _is_async(func):
            return _FaultAsyncWrapper(func, policy_name, registry, max_retries, backoff_ms, retry_on_list)
        return _FaultSyncWrapper(func, policy_name, registry, max_retries, backoff_ms, retry_on_list)

    return decorator


def fallback(fallback_func):
    def decorator(func):
        from faultcore._faultcore import FallbackPolicy

        policy = FallbackPolicy(fallback_func)
        return _decorate_func(func, policy)

    return decorator


def circuit_breaker(failure_threshold: int = 5, success_threshold: int = 2, timeout_ms: int = 30000):
    def decorator(func):
        from faultcore._faultcore import CircuitBreakerPolicy

        policy = CircuitBreakerPolicy(failure_threshold, success_threshold, timeout_ms)
        return _decorate_func(func, policy)

    return decorator


def rate_limit(rate: float, capacity: int):
    unique_id = uuid.uuid4().hex

    def decorator(func):
        registry = _get_registry()
        func_id = id(func)
        policy_name = f"_ratelimit_{func_id}_{unique_id}"
        registry.register_rate_limit_layer(policy_name, rate, capacity)
        return _FaultSyncWrapper(func, policy_name, registry)

    return decorator


def network_queue(
    rate: str = "1gbps",
    capacity: str = "10mb",
    max_queue_size: int = 1000,
    packet_loss: float = 0.0,
    latency_ms: int = 0,
):
    def decorator(func):
        from faultcore._faultcore import NetworkQueuePolicy

        policy = NetworkQueuePolicy(
            rate=rate, capacity=capacity, max_queue_size=max_queue_size, packet_loss=packet_loss, latency_ms=latency_ms
        )

        wrapper = _create_sync_wrapper(func, policy)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            ticket_info = policy._prepare_async_ticket()

            if isinstance(ticket_info, Exception):
                raise ticket_info

            latency_ms_val = ticket_info.get("latency_ms", 0)

            policy._enter_thread_context()

            try:
                result = await func(*args, **kwargs)

                if latency_ms_val > 0:
                    await asyncio.sleep(latency_ms_val / 1000.0)

                return result
            finally:
                policy._exit_thread_context()

        async_wrapper._wrapped_func = func
        async_wrapper.__name__ = func.__name__
        async_wrapper.__doc__ = getattr(func, "__doc__", None)

        return _attach_faultcore_attributes(wrapper, async_wrapper, func, policy)

    return decorator


def apply_policy(key: str):
    from faultcore._faultcore import get_feature_flag_manager

    manager = get_feature_flag_manager()

    def decorator(func):
        return _DynamicPolicyWrapper(func, key, manager)

    return decorator


class _DynamicPolicyWrapper:
    def __init__(self, func, key, manager):
        self._func = func
        self._key = key
        self._manager = manager

    def __call__(self, *args, **kwargs):
        if not self._manager.is_enabled(self._key):
            return self._func(*args, **kwargs)

        config = self._manager.get(self._key)
        if config is None:
            return self._func(*args, **kwargs)

        registry = _get_registry()

        policy_parts = [self._key]
        if config.get("timeout_ms"):
            policy_parts.append(f"t{config['timeout_ms']}")
        if config.get("retry_max_retries") is not None:
            policy_parts.append(f"r{config['retry_max_retries']}")
        if config.get("circuit_breaker_failure_threshold") is not None:
            policy_parts.append(f"cb{config['circuit_breaker_failure_threshold']}")
        if config.get("rate_limit_rate") is not None:
            policy_parts.append(f"rl{config['rate_limit_rate']}")

        policy_name = "_".join(policy_parts)

        if config.get("timeout_ms") and not registry.get_policy(policy_name):
            registry.register_timeout_layer(policy_name, config["timeout_ms"])
        if config.get("retry_max_retries") is not None and not registry.get_policy(policy_name):
            registry.register_retry_layer(policy_name, config["retry_max_retries"], config.get("retry_backoff_ms", 100))
        if config.get("rate_limit_rate") is not None and not registry.get_policy(policy_name):
            registry.register_rate_limit_layer(
                policy_name, config["rate_limit_rate"], config.get("rate_limit_capacity", 100)
            )

        def func_to_call():
            return self._func(*args, **kwargs)

        return registry.execute_policy(policy_name, func_to_call)

    def __get__(self, obj, objtype=None):
        return self


def fault(policy_name: str):
    registry = _get_registry()

    def decorator(func):
        if _is_async(func):
            return _FaultAsyncWrapper(func, policy_name, registry)
        return _FaultSyncWrapper(func, policy_name, registry)

    return decorator


class _FaultSyncWrapper:
    def __init__(self, func, policy_name, registry, max_retries=None, backoff_ms=None, retry_on=None):
        self._func = func
        self._policy_name = policy_name
        self._registry = registry
        self._max_retries = max_retries
        self._backoff_ms = backoff_ms
        self._retry_on = retry_on
        self.__name__ = func.__name__
        self.__doc__ = getattr(func, "__doc__", None)

    def __call__(self, *args, **kwargs):
        if not self._registry.is_policy_enabled(self._policy_name):
            return self._func(*args, **kwargs)

        if self._max_retries is not None:
            last_exception = None
            for attempt in range(self._max_retries + 1):
                try:
                    return self._func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if not _should_retry(e, self._retry_on):
                        raise
                    if attempt < self._max_retries:
                        delay = self._backoff_ms * (2**attempt) / 1000.0
                        time.sleep(delay)
            raise last_exception
        else:

            def func_to_call():
                return self._func(*args, **kwargs)

            return self._registry.execute_policy(self._policy_name, func_to_call)

    def __repr__(self):
        return f"<FaultSyncWrapper({self._policy_name}) for {self._func}>"


class _FaultAsyncWrapper:
    def __init__(self, func, policy_name, registry, max_retries=None, backoff_ms=None, retry_on=None):
        self._func = func
        self._policy_name = policy_name
        self._registry = registry
        self._max_retries = max_retries
        self._backoff_ms = backoff_ms
        self._retry_on = retry_on
        self.__name__ = func.__name__
        self.__doc__ = getattr(func, "__doc__", None)

    async def __call__(self, *args, **kwargs):
        if not self._registry.is_policy_enabled(self._policy_name):
            return await self._func(*args, **kwargs)

        if self._max_retries is not None:
            last_exception = None
            for attempt in range(self._max_retries + 1):
                try:
                    return await self._func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if not _should_retry(e, self._retry_on):
                        raise
                    if attempt < self._max_retries:
                        delay = self._backoff_ms * (2**attempt) / 1000.0
                        await asyncio.sleep(delay)
            raise last_exception
        else:
            return await self._func(*args, **kwargs)

    def __repr__(self):
        return f"<FaultAsyncWrapper({self._policy_name}) for {self._func}>"
