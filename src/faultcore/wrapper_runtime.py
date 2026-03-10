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
    import ctypes

    libc = ctypes.CDLL(None)
    fork_fn = libc.fork
    fork_fn.argtypes = []
    fork_fn.restype = ctypes.c_int
    pid = int(fork_fn())
    if pid == 0:
        os_module.close(read_fd)
        payload: bytes
        try:
            result = func(*args, **kwargs)
            payload = pickle_module.dumps(("result", result), protocol=pickle_module.HIGHEST_PROTOCOL)
        except BaseException as exc:  # noqa: BLE001
            payload = pickle_module.dumps(("error", exc), protocol=pickle_module.HIGHEST_PROTOCOL)
        try:
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
    startup_grace_ms = min(10, max(2, timeout_ms // 5))
    timeout_s = (timeout_ms + startup_grace_ms) / 1000
    ready, _, _ = select_module.select([read_fd], [], [], timeout_s)
    if not ready:
        try:
            os_module.kill(pid, signal_module.SIGKILL)
        except ProcessLookupError:
            pass
        os_module.waitpid(pid, 0)
        os_module.close(read_fd)
        raise TimeoutError(f"Function execution exceeded {timeout_ms}ms")

    data = b""
    while True:
        chunk = os_module.read(read_fd, 65536)
        if not chunk:
            break
        data += chunk
    os_module.close(read_fd)
    os_module.waitpid(pid, 0)

    kind, value = pickle_module.loads(data)
    if kind == "error":
        raise value
    return value
