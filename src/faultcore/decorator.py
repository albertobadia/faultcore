import functools
import signal
import threading
import time
from asyncio import iscoroutine, wait_for
from collections.abc import Callable
from inspect import iscoroutinefunction
from typing import Any

from faultcore.shm_writer import get_shm_writer


class FaultWrapper:
    def __init__(
        self,
        func: Callable[..., Any],
        latency_ms: int | None = None,
        bandwidth_bps: int | None = None,
        timeouts: tuple[int, int] | None = None,
    ):
        functools.update_wrapper(self, func)
        self._func = func
        self._latency_ms = latency_ms
        self._bandwidth_bps = bandwidth_bps
        self._timeouts = timeouts

    def __getattr__(self, name: str) -> Any:
        return getattr(self._func, name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tid = threading.get_native_id()
        shm = get_shm_writer()

        if self._latency_ms:
            shm.write_latency(tid, self._latency_ms)

        if self._bandwidth_bps:
            shm.write_bandwidth(tid, self._bandwidth_bps)

        if self._timeouts:
            connect_ms, recv_ms = self._timeouts
            shm.write_timeouts(tid, connect_ms, recv_ms)

        timeout_ms = self._timeouts[0] if self._timeouts else None

        if timeout_ms and timeout_ms > 0 and not iscoroutinefunction(self._func):
            try:
                return _run_sync_with_timeout(self._func, timeout_ms, args, kwargs)
            finally:
                shm.clear(tid)

        result = self._func(*args, **kwargs)

        if iscoroutine(result):
            return self._run_async(result, shm, tid, timeout_ms)

        try:
            return result
        finally:
            shm.clear(tid)

    async def _run_async(self, result: Any, shm: Any, tid: int, timeout_ms: int | None) -> Any:
        try:
            if timeout_ms and timeout_ms > 0:
                try:
                    return await wait_for(result, timeout_ms / 1000)
                except TimeoutError as exc:
                    raise TimeoutError(f"Function execution exceeded {timeout_ms}ms") from exc
            return await result
        finally:
            shm.clear(tid)

    def __repr__(self):
        return (
            "<FaultWrapper("
            f"latency={self._latency_ms}, "
            f"bandwidth={self._bandwidth_bps}, "
            f"timeouts={self._timeouts}) for {self._func!r}>"
        )


def latency(latency_ms: int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, latency_ms=latency_ms)

    return decorator


def timeout(timeout_ms: int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(timeout_ms, timeout_ms))

    return decorator


def rate_limit(rate: str | int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
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


def apply_policy(_key: str):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func)

    return decorator


def fault(_policy_name: str = "auto"):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func)

    return decorator


def _run_sync_with_timeout(
    func: Callable[..., Any],
    timeout_ms: int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer"):
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def handler(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

        signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000)
        try:
            return func(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_handler)

    started = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > timeout_ms:
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")
    return result
