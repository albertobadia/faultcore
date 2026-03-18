import asyncio
from unittest.mock import MagicMock, patch

import pytest

import faultcore


@pytest.fixture
def mock_shm():
    tid = 12345
    with (
        patch("faultcore.decorator.get_shm_writer") as mock_get_shm,
        patch("faultcore.decorator.threading.get_native_id", return_value=tid),
    ):
        mock = MagicMock()
        mock_get_shm.return_value = mock
        yield mock, tid


class TestScalarDecorators:
    @pytest.mark.parametrize(
        "decorator,value,writer_method,expected_shm_val",
        [
            (faultcore.latency, "500ms", "write_latency", 500),
            (faultcore.jitter, "25ms", "write_jitter", 25),
            (faultcore.rate, "1mbps", "write_bandwidth", 1_000_000),
            (faultcore.packet_loss, "2.5%", "write_packet_loss", 25_000),
            (faultcore.burst_loss, "5", "write_burst_loss", 5),
        ],
    )
    def test_scalar_writes_to_shm(self, mock_shm, decorator, value, writer_method, expected_shm_val):
        mock, tid = mock_shm

        @decorator(value)
        def my_func():
            return "ok"

        assert my_func() == "ok"
        getattr(mock, writer_method).assert_called_once_with(tid, expected_shm_val)
        mock.clear.assert_called_once_with(tid)

    def test_metadata_preservation(self):
        @faultcore.latency("100ms")
        def my_function():
            """Docstring."""
            return "ok"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."

    def test_error_clears_shm(self, mock_shm):
        mock, tid = mock_shm
        mock.write_latency.side_effect = RuntimeError("failed")

        @faultcore.latency("10ms")
        def my_func():
            return "ok"

        with pytest.raises(RuntimeError, match="failed"):
            my_func()

        mock.clear.assert_called_once_with(tid)


class TestComplexDecorators:
    def test_timeout_writes(self, mock_shm):
        mock, tid = mock_shm

        @faultcore.timeout(connect="2s", recv="500ms")
        def my_func():
            return "ok"

        assert my_func() == "ok"
        mock.write_timeouts.assert_called_once_with(tid, 2000, 500)

    @pytest.mark.parametrize(
        "decorator_call,writer_method",
        [
            (lambda: faultcore.uplink(latency="100ms"), "write_uplink"),
            (lambda: faultcore.downlink(latency="200ms"), "write_downlink"),
            (
                lambda: faultcore.correlated_loss(
                    p_good_to_bad="5%", p_bad_to_good="10%", loss_good="0%", loss_bad="50%"
                ),
                "write_correlated_loss",
            ),
            (lambda: faultcore.connection_error(kind="reset"), "write_connection_error"),
            (lambda: faultcore.half_open(after="1kb"), "write_half_open"),
            (lambda: faultcore.packet_duplicate(prob="10%"), "write_packet_duplicate"),
            (lambda: faultcore.packet_reorder(prob="5%"), "write_packet_reorder"),
            (lambda: faultcore.dns(delay="500ms"), "write_dns"),
            (lambda: faultcore.session_budget(max_tx="1kb"), "write_session_budget"),
        ],
    )
    def test_profile_writes(self, mock_shm, decorator_call, writer_method):
        mock, tid = mock_shm

        @decorator_call()
        def my_func():
            return "ok"

        assert my_func() == "ok"
        getattr(mock, writer_method).assert_called_once()
        mock.clear.assert_called_once_with(tid)


class TestAsync:
    @pytest.mark.asyncio
    async def test_async_lifecycle(self, mock_shm):
        mock, tid = mock_shm

        @faultcore.latency("100ms")
        async def my_func():
            await asyncio.sleep(0.01)
            return "ok"

        assert await my_func() == "ok"
        mock.clear.assert_called_once_with(tid)

    @pytest.mark.asyncio
    async def test_awaitable_keeps_shm(self, mock_shm):
        mock, tid = mock_shm

        class AwaitableValue:
            def __await__(self):
                yield
                return "result"

        @faultcore.latency("50ms")
        def func_returning_awaitable():
            return AwaitableValue()

        result = func_returning_awaitable()
        assert await result == "result"
        mock.clear.assert_called_once_with(tid)
