import functools
import logging
import uuid

from faultcore._faultcore import get_feature_flag_manager, get_policy_registry

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

    def __getattr__(self, name):
        return getattr(self._func, name)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args, **kwargs):
        policy_name = self._policy_name

        if self._key:
            manager = get_feature_flag_manager()

            if not manager.is_enabled(self._key):
                return self._func(*args, **kwargs)

            config = manager.get(self._key)
            if config:
                policy_name = self._ensure_policy(config)

        if not policy_name:
            return self._func(*args, **kwargs)

        return self._registry.execute_policy(policy_name, lambda: self._func(*args, **kwargs))

    def _ensure_policy(self, config: dict) -> str:
        t = config.get("timeout_ms")
        rl = config.get("rate_limit_rate")
        if not (t or rl):
            return self._key

        # Generate a unique policy name based on parameters
        parts = [self._key]
        if t:
            parts.append(f"t{t}")
        if rl:
            parts.append(f"rl{rl}")

        name = "_".join(parts)

        if not self._registry.get_policy(name):
            if t:
                self._registry.register_timeout_layer(name, t)
            if rl:
                self._registry.register_rate_limit_layer(name, rl)
        return name

    def __repr__(self):
        return f"<FaultWrapper(policy={self._policy_name}, key={self._key}) for {self._func!r}>"


def timeout(timeout_ms: int):
    def decorator(func):
        policy_name = f"_timeout_{id(func)}_{uuid.uuid4().hex[:8]}"
        _get_registry().register_timeout_layer(policy_name, timeout_ms)
        return FaultWrapper(func, policy_name=policy_name)

    return decorator


def rate_limit(rate: str | int):
    def decorator(func):
        policy_name = f"_ratelimit_{id(func)}_{uuid.uuid4().hex[:8]}"
        _get_registry().register_rate_limit_layer(policy_name, _parse_rate(rate))
        return FaultWrapper(func, policy_name=policy_name)

    return decorator


def _parse_rate(rate: str | int | float) -> int:
    if isinstance(rate, (int, float)):
        return int(rate * 1_000_000)
    r = rate.lower()
    if r.endswith("mbps"):
        return int(float(r[:-4]) * 1_000_000)
    if r.endswith("gbps"):
        return int(float(r[:-4]) * 1_000_000_000)
    if r.endswith("kbps"):
        return int(float(r[:-4]) * 1_000)
    if r.endswith("bps"):
        return int(float(r[:-3]))
    return int(float(r))


def apply_policy(key: str):
    return lambda func: FaultWrapper(func, key=key)


def fault(policy_name: str = "auto"):
    return lambda func: FaultWrapper(func, policy_name=policy_name)
