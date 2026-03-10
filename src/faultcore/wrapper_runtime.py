import ctypes
import os
import pickle
import select
import signal
import threading
import time
from collections.abc import Callable
from typing import Any

_STARTUP_TIMEOUT_S = 0.25


def _terminate_worker_process(os_module: Any, signal_module: Any, pid: int) -> None:
    try:
        os_module.kill(pid, signal_module.SIGKILL)
    except ProcessLookupError:
        pass
    os_module.waitpid(pid, 0)


def _terminate_and_close(
    os_module: Any,
    signal_module: Any,
    pid: int,
    signal_read_fd: int,
    read_fd: int,
) -> None:
    _terminate_worker_process(os_module, signal_module, pid)
    os_module.close(signal_read_fd)
    os_module.close(read_fd)


def run_sync_with_timeout(
    func: Callable[..., Any],
    timeout_ms: int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    os_module: Any = os,
    signal_module: Any = signal,
    select_module: Any = select,
    pickle_module: Any = pickle,
) -> Any:
    if threading.current_thread() is threading.main_thread() and hasattr(signal_module, "setitimer"):
        previous_handler = signal_module.getsignal(signal_module.SIGALRM)
        previous_timer = signal_module.getitimer(signal_module.ITIMER_REAL)

        def handler(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

        signal_module.signal(signal_module.SIGALRM, handler)
        signal_module.setitimer(signal_module.ITIMER_REAL, timeout_ms / 1000)
        try:
            return func(*args, **kwargs)
        finally:
            signal_module.setitimer(signal_module.ITIMER_REAL, *previous_timer)
            signal_module.signal(signal_module.SIGALRM, previous_handler)

    read_fd, write_fd = os_module.pipe()
    signal_read_fd, signal_write_fd = os_module.pipe()

    libc = ctypes.CDLL(None)
    fork_fn = libc.fork
    fork_fn.argtypes = []
    fork_fn.restype = ctypes.c_int
    pid = int(fork_fn())
    if pid == 0:
        os_module.close(read_fd)
        os_module.close(signal_read_fd)
        os_module.write(signal_write_fd, b"S")
        kind: str
        value: Any
        try:
            value = func(*args, **kwargs)
            kind = "result"
        except BaseException as exc:  # noqa: BLE001
            value = exc
            kind = "error"
        try:
            os_module.write(signal_write_fd, b"D")
            os_module.close(signal_write_fd)
            payload = pickle_module.dumps((kind, value), protocol=pickle_module.HIGHEST_PROTOCOL)
            offset = 0
            total = len(payload)
            while offset < total:
                written = os_module.write(write_fd, payload[offset:])
                if written <= 0:
                    break
                offset += written
        finally:
            os_module.close(write_fd)
        os_module._exit(0)

    os_module.close(write_fd)
    os_module.close(signal_write_fd)
    startup_ready, _, _ = select_module.select([signal_read_fd], [], [], _STARTUP_TIMEOUT_S)
    if not startup_ready:
        _terminate_and_close(os_module, signal_module, pid, signal_read_fd, read_fd)
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

    started = os_module.read(signal_read_fd, 1)
    if started != b"S":
        _terminate_and_close(os_module, signal_module, pid, signal_read_fd, read_fd)
        raise RuntimeError("Worker process failed before execution handshake")

    deadline_ns = time.monotonic_ns() + (timeout_ms * 1_000_000)
    remaining_ns = deadline_ns - time.monotonic_ns()
    timeout_s = 0.0 if remaining_ns <= 0 else remaining_ns / 1_000_000_000
    ready, _, _ = select_module.select([signal_read_fd], [], [], timeout_s)
    if not ready:
        _terminate_and_close(os_module, signal_module, pid, signal_read_fd, read_fd)
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

    finished = os_module.read(signal_read_fd, 1)
    if finished != b"D":
        _terminate_and_close(os_module, signal_module, pid, signal_read_fd, read_fd)
        raise RuntimeError("Worker process failed before completion handshake")

    os_module.close(signal_read_fd)

    chunks: list[bytes] = []
    while True:
        chunk = os_module.read(read_fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    os_module.close(read_fd)
    os_module.waitpid(pid, 0)

    data = b"".join(chunks)
    if not data:
        raise RuntimeError("Worker process exited without returning a payload")

    kind, value = pickle_module.loads(data)
    if kind == "error":
        raise value
    return value
