import functools
import logging
import uuid

from faultcore._faultcore import get_policy_registry

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_registry():
    return get_policy_registry()


class FaultWrapper:
    def __init__(self, func, policy_name=None, key=None):
        functools.update_wrapper(self, func)
        self._func = func
        self._policy_name = policy_name
        self._key = key
        self._registry = _get_registry()
        self._manager = None

    def __getattr__(self, name):
        return getattr(self._func, name)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args, **kwargs):
        registry = self._registry
        policy_name = self._policy_name

        if self._key:
            if self._manager is None:
                from faultcore._faultcore import get_feature_flag_manager

                self._manager = get_feature_flag_manager()

            if not self._manager.is_enabled(self._key):
                return self._func(*args, **kwargs)

            config = self._manager.get(self._key)
            if config is None:
                return self._func(*args, **kwargs)

            policy_name = self._ensure_policy(config)

        if not policy_name:
            return self._func(*args, **kwargs)

        def call():
            return self._func(*args, **kwargs)

        return registry.execute_policy(policy_name, call)

    def _ensure_policy(self, config: dict) -> str:
        parts = [self._key]
        t = config.get("timeout_ms")
        rl = config.get("rate_limit_rate")

        if t:
            parts.append(f"t{t}")
        if rl:
            parts.append(f"rl{rl}")

        name = "_".join(parts)
        if (t or rl) and not self._registry.get_policy(name):
            if t:
                self._registry.register_timeout_layer(name, t)
            if rl:
                self._registry.register_rate_limit_layer(name, rl)
        return name

    def __repr__(self):
        return f"<FaultWrapper(policy={self._policy_name}, key={self._key}) for {self._func!r}>"


def timeout(timeout_ms: int):
    def decorator(func):
        registry = _get_registry()
        policy_name = f"_timeout_{id(func)}"
        try:
            registry.register_timeout_layer(policy_name, timeout_ms)
        except Exception as e:
            logger.warning("Failed to register timeout for %s: %s", func, e)
            return func
        return FaultWrapper(func, policy_name=policy_name)

    return decorator


def rate_limit(rate: str | int, capacity: int = 100):
    def decorator(func):
        registry = _get_registry()
        policy_name = f"_ratelimit_{id(func)}_{uuid.uuid4().hex[:8]}"
        try:
            rate_bps = _parse_rate(rate)
            registry.register_rate_limit_layer(policy_name, rate_bps)
        except Exception as e:
            logger.warning("Failed to register rate limit for %s: %s", func, e)
            return func
        return FaultWrapper(func, policy_name=policy_name)

    return decorator


def _parse_rate(rate: str | int) -> int:
    if isinstance(rate, int):
        return rate * 1_000_000
    r = rate.lower()
    if r.endswith("mbps"):
        return int(float(r[:-4]) * 1_000_000)
    if r.endswith("gbps"):
        return int(float(r[:-4]) * 1_000_000_000)
    return int(float(r))


def apply_policy(key: str):
    def decorator(func):
        return FaultWrapper(func, key=key)

    return decorator


def fault(policy_name: str = "auto"):
    def decorator(func):
        return FaultWrapper(func, policy_name=policy_name)

    return decorator
