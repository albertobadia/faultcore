import os
import pickle
import select
import signal
import threading
from collections.abc import Callable
from typing import Any


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
    import ctypes

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
    startup_timeout_ms = min(50, max(10, timeout_ms // 2))
    startup_ready, _, _ = select_module.select([signal_read_fd], [], [], startup_timeout_ms / 1000)
    if not startup_ready:
        try:
            os_module.kill(pid, signal_module.SIGKILL)
        except ProcessLookupError:
            pass
        os_module.waitpid(pid, 0)
        os_module.close(signal_read_fd)
        os_module.close(read_fd)
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

    started = os_module.read(signal_read_fd, 1)
    if started != b"S":
        try:
            os_module.kill(pid, signal_module.SIGKILL)
        except ProcessLookupError:
            pass
        os_module.waitpid(pid, 0)
        os_module.close(signal_read_fd)
        os_module.close(read_fd)
        raise RuntimeError("Worker process failed before execution handshake")

    ready, _, _ = select_module.select([signal_read_fd], [], [], timeout_ms / 1000)
    if not ready:
        try:
            os_module.kill(pid, signal_module.SIGKILL)
        except ProcessLookupError:
            pass
        os_module.waitpid(pid, 0)
        os_module.close(signal_read_fd)
        os_module.close(read_fd)
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

    finished = os_module.read(signal_read_fd, 1)
    if finished != b"D":
        try:
            os_module.kill(pid, signal_module.SIGKILL)
        except ProcessLookupError:
            pass
        os_module.waitpid(pid, 0)
        os_module.close(signal_read_fd)
        os_module.close(read_fd)
        raise RuntimeError("Worker process failed before completion handshake")

    os_module.close(signal_read_fd)

    data = b""
    while True:
        chunk = os_module.read(read_fd, 65536)
        if not chunk:
            break
        data += chunk
    os_module.close(read_fd)
    os_module.waitpid(pid, 0)

    if not data:
        raise RuntimeError("Worker process exited without returning a payload")

    kind, value = pickle_module.loads(data)
    if kind == "error":
        raise value
    return value
