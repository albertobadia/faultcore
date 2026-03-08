import asyncio
import functools
import json
import signal
import threading
import time
from asyncio import iscoroutine, wait_for
from collections.abc import Callable
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any

from faultcore.shm_writer import get_shm_writer

_POLICY_REGISTRY: dict[str, dict[str, Any]] = {}
_THREAD_POLICY = threading.local()
_POLICY_LOCK = threading.RLock()


def _build_direction_profile(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        profile["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        profile["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        profile["packet_loss_ppm"] = _parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        profile["burst_loss_len"] = b
    if rate is not None:
        profile["bandwidth_bps"] = _parse_rate(rate)
    return profile


def _build_correlated_loss_profile(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
) -> dict[str, int]:
    profile = {
        "p_good_to_bad_ppm": _parse_packet_loss(p_good_to_bad),
        "p_bad_to_good_ppm": _parse_packet_loss(p_bad_to_good),
        "loss_good_ppm": _parse_packet_loss(loss_good),
        "loss_bad_ppm": _parse_packet_loss(loss_bad),
    }
    profile["enabled"] = 1
    return profile


class FaultWrapper:
    def __init__(
        self,
        func: Callable[..., Any],
        latency_ms: int | None = None,
        jitter_ms: int | None = None,
        packet_loss_ppm: int | None = None,
        burst_loss_len: int | None = None,
        bandwidth_bps: int | None = None,
        timeouts: tuple[int, int] | None = None,
        uplink_profile: dict[str, int] | None = None,
        downlink_profile: dict[str, int] | None = None,
        correlated_loss_profile: dict[str, int] | None = None,
    ):
        functools.update_wrapper(self, func)
        self._func = func
        self._latency_ms = latency_ms
        self._jitter_ms = jitter_ms
        self._packet_loss_ppm = packet_loss_ppm
        self._burst_loss_len = burst_loss_len
        self._bandwidth_bps = bandwidth_bps
        self._timeouts = timeouts
        self._uplink_profile = uplink_profile or {}
        self._downlink_profile = downlink_profile or {}
        self._correlated_loss_profile = correlated_loss_profile or {}

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

        if self._jitter_ms:
            shm.write_jitter(tid, self._jitter_ms)

        if self._packet_loss_ppm is not None:
            shm.write_packet_loss(tid, self._packet_loss_ppm)

        if self._burst_loss_len is not None:
            shm.write_burst_loss(tid, self._burst_loss_len)

        if self._bandwidth_bps:
            shm.write_bandwidth(tid, self._bandwidth_bps)

        if self._timeouts:
            connect_ms, recv_ms = self._timeouts
            shm.write_timeouts(tid, connect_ms, recv_ms)

        if self._uplink_profile:
            shm.write_uplink(
                tid,
                latency_ms=self._uplink_profile.get("latency_ms"),
                jitter_ms=self._uplink_profile.get("jitter_ms"),
                packet_loss_ppm=self._uplink_profile.get("packet_loss_ppm"),
                burst_loss_len=self._uplink_profile.get("burst_loss_len"),
                bandwidth_bps=self._uplink_profile.get("bandwidth_bps"),
            )

        if self._downlink_profile:
            shm.write_downlink(
                tid,
                latency_ms=self._downlink_profile.get("latency_ms"),
                jitter_ms=self._downlink_profile.get("jitter_ms"),
                packet_loss_ppm=self._downlink_profile.get("packet_loss_ppm"),
                burst_loss_len=self._downlink_profile.get("burst_loss_len"),
                bandwidth_bps=self._downlink_profile.get("bandwidth_bps"),
            )

        if self._correlated_loss_profile:
            shm.write_correlated_loss(
                tid,
                enabled=bool(self._correlated_loss_profile.get("enabled", 0)),
                p_good_to_bad_ppm=self._correlated_loss_profile.get("p_good_to_bad_ppm", 0),
                p_bad_to_good_ppm=self._correlated_loss_profile.get("p_bad_to_good_ppm", 0),
                loss_good_ppm=self._correlated_loss_profile.get("loss_good_ppm", 0),
                loss_bad_ppm=self._correlated_loss_profile.get("loss_bad_ppm", 0),
            )

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
                except (asyncio.exceptions.TimeoutError, TimeoutError) as exc:
                    raise TimeoutError(f"Function execution exceeded {timeout_ms}ms") from exc
            return await result
        finally:
            shm.clear(tid)

    def __repr__(self):
        return (
            "<FaultWrapper("
            f"latency={self._latency_ms}, "
            f"jitter={self._jitter_ms}, "
            f"packet_loss_ppm={self._packet_loss_ppm}, "
            f"burst_loss_len={self._burst_loss_len}, "
            f"bandwidth={self._bandwidth_bps}, "
            f"timeouts={self._timeouts}, "
            f"uplink={self._uplink_profile}, "
            f"downlink={self._downlink_profile}, "
            f"correlated_loss={self._correlated_loss_profile}) for {self._func!r}>"
        )


def latency(latency_ms: int):
    if latency_ms < 0:
        raise ValueError("latency must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, latency_ms=latency_ms)

    return decorator


def jitter(jitter_ms: int):
    if jitter_ms < 0:
        raise ValueError("jitter must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, jitter_ms=jitter_ms)

    return decorator


def timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(timeout_ms, timeout_ms))

    return decorator


def connect_timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("connect_timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(timeout_ms, 0))

    return decorator


def recv_timeout(timeout_ms: int):
    if timeout_ms < 0:
        raise ValueError("recv_timeout must be >= 0")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, timeouts=(0, timeout_ms))

    return decorator


def rate_limit(rate: str | int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        bps = _parse_rate(rate)
        return FaultWrapper(func, bandwidth_bps=bps)

    return decorator


def packet_loss(loss: str | int | float):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        ppm = _parse_packet_loss(loss)
        return FaultWrapper(func, packet_loss_ppm=ppm)

    return decorator


def burst_loss(length: int):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        if length < 0:
            raise ValueError("burst_loss length must be >= 0")
        return FaultWrapper(func, burst_loss_len=int(length))

    return decorator


def uplink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not profile:
        raise ValueError("uplink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, uplink_profile=profile)

    return decorator


def downlink(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
):
    profile = _build_direction_profile(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        packet_loss=packet_loss,
        burst_loss_len=burst_loss_len,
        rate=rate,
    )
    if not profile:
        raise ValueError("downlink requires at least one directional field")

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, downlink_profile=profile)

    return decorator


def correlated_loss(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
):
    profile = _build_correlated_loss_profile(
        p_good_to_bad=p_good_to_bad,
        p_bad_to_good=p_bad_to_good,
        loss_good=loss_good,
        loss_bad=loss_bad,
    )

    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        return FaultWrapper(func, correlated_loss_profile=profile)

    return decorator


def _parse_rate(rate: str | int | float) -> int:
    if isinstance(rate, (int, float)):
        if rate < 0:
            raise ValueError("rate must be >= 0")
        return int(rate * 1_000_000)
    r = rate.lower()
    if r.endswith("mbps"):
        value = float(r[:-4])
        if value < 0:
            raise ValueError("rate must be >= 0")
        return int(value * 1_000_000)
    if r.endswith("gbps"):
        value = float(r[:-4])
        if value < 0:
            raise ValueError("rate must be >= 0")
        return int(value * 1_000_000_000)
    if r.endswith("kbps"):
        value = float(r[:-4])
        if value < 0:
            raise ValueError("rate must be >= 0")
        return int(value * 1_000)
    if r.endswith("bps"):
        value = float(r[:-3])
        if value < 0:
            raise ValueError("rate must be >= 0")
        return int(value)
    value = float(r)
    if value < 0:
        raise ValueError("rate must be >= 0")
    return int(value)


def _parse_packet_loss(loss: str | int | float) -> int:
    if isinstance(loss, str):
        raw = loss.strip().lower()
        if raw.endswith("%"):
            value = float(raw[:-1])
            if value < 0 or value > 100:
                raise ValueError("packet_loss percentage must be between 0 and 100")
            return int(value * 10_000)
        if raw.endswith("ppm"):
            value = float(raw[:-3])
            if value < 0 or value > 1_000_000:
                raise ValueError("packet_loss ppm must be between 0 and 1000000")
            return int(value)
        value = float(raw)
    else:
        value = float(loss)

    if value < 0:
        raise ValueError("packet_loss must be >= 0")
    if value <= 1:
        return int(value * 1_000_000)
    if value <= 100:
        return int(value * 10_000)
    if value <= 1_000_000:
        return int(value)
    raise ValueError("packet_loss must be <= 100%, <=1.0 ratio, or <=1000000ppm")


def apply_policy(_key: str):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        with _POLICY_LOCK:
            policy = _POLICY_REGISTRY.get(_key)
        if policy is None:
            return FaultWrapper(func)
        return FaultWrapper(
            func,
            latency_ms=policy.get("latency_ms"),
            jitter_ms=policy.get("jitter_ms"),
            packet_loss_ppm=policy.get("packet_loss_ppm"),
            burst_loss_len=policy.get("burst_loss_len"),
            bandwidth_bps=policy.get("bandwidth_bps"),
            timeouts=policy.get("timeouts"),
            uplink_profile=policy.get("uplink_profile"),
            downlink_profile=policy.get("downlink_profile"),
            correlated_loss_profile=policy.get("correlated_loss_profile"),
        )

    return decorator


def fault(_policy_name: str = "auto"):
    def decorator(func: Callable[..., Any]) -> FaultWrapper:
        name = _policy_name
        if name == "auto":
            name = get_thread_policy() or ""
        if not name:
            return FaultWrapper(func)
        return apply_policy(name)(func)

    return decorator


def register_policy(
    name: str,
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
    timeout_ms: int | None = None,
    connect_timeout_ms: int | None = None,
    recv_timeout_ms: int | None = None,
    uplink: dict[str, Any] | None = None,
    downlink: dict[str, Any] | None = None,
    correlated_loss: dict[str, Any] | None = None,
) -> None:
    if not name:
        raise ValueError("policy name must be non-empty")

    policy: dict[str, Any] = {}
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        policy["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        policy["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        policy["packet_loss_ppm"] = _parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        policy["burst_loss_len"] = b
    if rate is not None:
        policy["bandwidth_bps"] = _parse_rate(rate)
    if timeout_ms is not None:
        t = int(timeout_ms)
        if t < 0:
            raise ValueError("timeout_ms must be >= 0")
        policy["timeouts"] = (t, t)
    if connect_timeout_ms is not None or recv_timeout_ms is not None:
        connect_ms = int(connect_timeout_ms) if connect_timeout_ms is not None else 0
        recv_ms = int(recv_timeout_ms) if recv_timeout_ms is not None else 0
        if connect_ms < 0 or recv_ms < 0:
            raise ValueError("connect_timeout_ms and recv_timeout_ms must be >= 0")
        policy["timeouts"] = (connect_ms, recv_ms)
    if uplink is not None:
        if not isinstance(uplink, dict):
            raise ValueError("uplink must be a mapping when provided")
        policy["uplink_profile"] = _build_direction_profile(
            latency_ms=uplink.get("latency_ms"),
            jitter_ms=uplink.get("jitter_ms"),
            packet_loss=uplink.get("packet_loss"),
            burst_loss_len=uplink.get("burst_loss_len"),
            rate=uplink.get("rate"),
        )
    if downlink is not None:
        if not isinstance(downlink, dict):
            raise ValueError("downlink must be a mapping when provided")
        policy["downlink_profile"] = _build_direction_profile(
            latency_ms=downlink.get("latency_ms"),
            jitter_ms=downlink.get("jitter_ms"),
            packet_loss=downlink.get("packet_loss"),
            burst_loss_len=downlink.get("burst_loss_len"),
            rate=downlink.get("rate"),
        )
    if correlated_loss is not None:
        if not isinstance(correlated_loss, dict):
            raise ValueError("correlated_loss must be a mapping when provided")
        policy["correlated_loss_profile"] = _build_correlated_loss_profile(
            p_good_to_bad=correlated_loss.get("p_good_to_bad", 0),
            p_bad_to_good=correlated_loss.get("p_bad_to_good", 0),
            loss_good=correlated_loss.get("loss_good", 0),
            loss_bad=correlated_loss.get("loss_bad", 0),
        )
    with _POLICY_LOCK:
        _POLICY_REGISTRY[name] = policy


def clear_policies() -> None:
    with _POLICY_LOCK:
        _POLICY_REGISTRY.clear()


def list_policies() -> list[str]:
    with _POLICY_LOCK:
        return sorted(_POLICY_REGISTRY.keys())


def get_policy(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        policy = _POLICY_REGISTRY.get(name)
    if policy is None:
        return None
    return dict(policy)


def unregister_policy(name: str) -> bool:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.pop(name, None) is not None


def load_policies(path: str | Path) -> int:
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".json":
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except Exception as exc:
            raise ValueError("YAML support requires PyYAML installed") from exc
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    else:
        raise ValueError("Unsupported policy format; use .json, .yaml or .yml")

    if not isinstance(raw, dict):
        raise ValueError("Policy file must contain an object keyed by policy name")

    loaded = 0
    for name, cfg in raw.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            raise ValueError("Each policy entry must be a mapping")
        register_policy(
            name,
            latency_ms=cfg.get("latency_ms"),
            jitter_ms=cfg.get("jitter_ms"),
            packet_loss=cfg.get("packet_loss"),
            burst_loss_len=cfg.get("burst_loss_len"),
            rate=cfg.get("rate"),
            timeout_ms=cfg.get("timeout_ms"),
            connect_timeout_ms=cfg.get("connect_timeout_ms"),
            recv_timeout_ms=cfg.get("recv_timeout_ms"),
            uplink=cfg.get("uplink"),
            downlink=cfg.get("downlink"),
            correlated_loss=cfg.get("correlated_loss"),
        )
        loaded += 1
    return loaded


def set_thread_policy(policy_name: str | None) -> None:
    _THREAD_POLICY.name = policy_name


def get_thread_policy() -> str | None:
    return getattr(_THREAD_POLICY, "name", None)


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
