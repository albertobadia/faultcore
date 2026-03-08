import functools
import logging
import os
import threading

from faultcore.shm_writer import get_shm_writer

logger = logging.getLogger(__name__)

_fault_wrapper_mode = os.environ.get("FAULTCORE_WRAPPER_MODE", "shm")


class FaultWrapper:
    def __init__(self, func, latency_ms=None, rate_limit=None, bandwidth_bps=None, timeouts=None):
        functools.update_wrapper(self, func)
        self._func = func
        self._latency_ms = latency_ms
        self._rate_limit = rate_limit
        self._bandwidth_bps = bandwidth_bps
        self._timeouts = timeouts

    def __getattr__(self, name):
        return getattr(self._func, name)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args, **kwargs):
        tid = threading.get_native_id()
        shm = get_shm_writer()

        if self._latency_ms:
            shm.write_latency(tid, self._latency_ms)

        if self._bandwidth_bps:
            shm.write_bandwidth(tid, self._bandwidth_bps)

        if self._timeouts:
            connect_ms, recv_ms = self._timeouts
            shm.write_timeouts(tid, connect_ms, recv_ms)

        try:
            return self._func(*args, **kwargs)
        finally:
            shm.clear(tid)

    def __repr__(self):
        return (
            f"<FaultWrapper(latency={self._latency_ms}, "
            f"bandwidth={self._bandwidth_bps}, timeouts={self._timeouts}) "
            f"for {self._func!r}>"
        )


def timeout(timeout_ms: int):
    def decorator(func):
        return FaultWrapper(func, latency_ms=timeout_ms)

    return decorator


def rate_limit(rate: str | int):
    def decorator(func):
        bps = _parse_rate(rate)
        return FaultWrapper(func, bandwidth_bps=bps)

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
    return lambda func: FaultWrapper(func)


def fault(policy_name: str = "auto"):
    return lambda func: FaultWrapper(func)
