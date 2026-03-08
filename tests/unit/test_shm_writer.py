import os

from faultcore.shm_writer import (
    CONFIG_SIZE,
    MAX_FDS,
    MAX_TIDS,
    SHMWriter,
)


def create_test_shm(name: str) -> int:
    fd = os.open(f"/dev/shm/{name}", os.O_CREAT | os.O_RDWR, mode=0o666)
    size = (MAX_FDS + MAX_TIDS) * CONFIG_SIZE
    os.ftruncate(fd, size)
    return fd


def cleanup_test_shm(name: str) -> None:
    try:
        os.unlink(f"/dev/shm/{name}")
    except FileNotFoundError:
        pass


class TestSHMWriterGracefulDegradation:
    def test_no_shm_returns_empty(self):
        writer = SHMWriter("nonexistent_shm_12345")
        assert writer._mmap is None
        assert writer._fd is None

    def test_write_latency_no_shm_no_error(self, monkeypatch):
        monkeypatch.setenv("FAULTCORE_CONFIG_SHM", "nonexistent_shm_12345")
        writer = SHMWriter()
        writer.write_latency(1234, 100)
        assert writer._mmap is None


class TestDecoratorIntegration:
    def test_timeout_decorator_no_shm_no_error(self):
        from faultcore import timeout

        @timeout(100)
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"

    def test_rate_limit_decorator_no_shm_no_error(self):
        from faultcore import rate_limit

        @rate_limit("1mbps")
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"


class TestExports:
    def test_timeout_is_exported(self):
        from faultcore import timeout

        assert callable(timeout)

    def test_rate_limit_is_exported(self):
        from faultcore import rate_limit

        assert callable(rate_limit)

    def test_packet_loss_is_exported(self):
        from faultcore import packet_loss

        assert callable(packet_loss)

    def test_apply_policy_is_exported(self):
        from faultcore import apply_policy

        assert callable(apply_policy)

    def test_register_policy_is_exported(self):
        from faultcore import register_policy

        assert callable(register_policy)

    def test_fault_is_exported(self):
        from faultcore import fault

        assert callable(fault)

    def test_fault_context_is_exported(self):
        from faultcore import fault_context

        assert fault_context is not None

    def test_is_interceptor_loaded_is_exported(self):
        from faultcore import is_interceptor_loaded

        assert callable(is_interceptor_loaded)
