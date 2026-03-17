import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

import faultcore
from faultcore.decorator import _parse_packet_loss
from faultcore.decorator_helpers import apply_fault_profiles


class TestTimeoutDecorator:
    def test_timeout_decorator_basic(self):
        @faultcore.timeout(connect="1s")
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_decorator_zero(self):
        @faultcore.timeout(connect="1ms")
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_passes_args(self):
        @faultcore.timeout(connect="1s")
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_timeout_passes_kwargs(self):
        @faultcore.timeout(connect="1s")
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15

    def test_timeout_passes_mixed_args(self):
        @faultcore.timeout(connect="1s")
        def func_mixed(a, b=10, c=20):
            return a + b + c

        result = func_mixed(5, c=100)
        assert result == 115

    def test_timeout_decorator_with_varargs(self):
        @faultcore.timeout(connect="1s")
        def func_with_varargs(*args):
            return sum(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    def test_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(connect="1s")
        def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 6

    def test_timeout_decorator_with_args_and_kwargs(self):
        @faultcore.timeout(connect="1s")
        def func_mixed(*args, **kwargs):
            return sum(args) + sum(kwargs.values())

        result = func_mixed(1, 2, x=3, y=4)
        assert result == 10

    def test_timeout_recv_only(self):
        @faultcore.timeout(recv="500ms")
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_both_connect_and_recv(self):
        @faultcore.timeout(connect="2s", recv="500ms")
        def my_func():
            return "ok"

        assert my_func() == "ok"


class TestApplyFaultProfiles:
    def test_apply_fault_profiles_writes_explicit_zero_values(self):
        mock_shm = MagicMock()
        wrapper = MagicMock()
        wrapper._seed = None
        wrapper._latency = 0
        wrapper._jitter = 0
        wrapper._packet_loss_ppm = None
        wrapper._burst_loss = None
        wrapper._rate = 0
        wrapper._timeouts = None
        wrapper._uplink_profile = {}
        wrapper._downlink_profile = {}
        wrapper._correlated_loss_profile = {}
        wrapper._connection_error_profile = {}
        wrapper._half_open_profile = {}
        wrapper._packet_duplicate_profile = {}
        wrapper._packet_reorder_profile = {}
        wrapper._dns_profile = {}
        wrapper._target_profiles = []
        wrapper._target_profile = {}
        wrapper._schedule_profile = {}
        wrapper._session_budget_profile = {}

        apply_fault_profiles(mock_shm, 321, wrapper, started_monotonic_ns=1)

        mock_shm.write_latency.assert_called_once_with(321, 0)
        mock_shm.write_jitter.assert_called_once_with(321, 0)
        mock_shm.write_bandwidth.assert_called_once_with(321, 0)


class TestLatencyDecorator:
    def test_latency_decorator_writes_latency_to_shm(self, monkeypatch):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.latency("500ms")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_latency.assert_called_once_with(12345, 500)
                mock_shm.write_timeouts.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_latency_decorator_preserves_function_name(self):
        @faultcore.latency("100ms")
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_latency_write_failure_still_clears_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock(side_effect=RuntimeError("write failed"))
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=4242):

                @faultcore.latency("10ms")
                def my_func():
                    return "ok"

                with pytest.raises(RuntimeError, match="write failed"):
                    my_func()

                mock_shm.clear.assert_called_once_with(4242)

    def test_latency_accepts_seconds(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.latency("1s")
                def my_func():
                    return "ok"

                my_func()
                mock_shm.write_latency.assert_called_once_with(12345, 1000)


class TestJitterDecorator:
    def test_jitter_decorator_writes_jitter_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=999):

                @faultcore.jitter("25ms")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_jitter.assert_called_once_with(999, 25)
                mock_shm.clear.assert_called_once_with(999)

    def test_jitter_rejects_invalid(self):
        with pytest.raises((ValueError, TypeError)):

            @faultcore.jitter("invalid")
            def _bad():
                return "x"

    def test_jitter_accepts_seconds(self):
        mock_shm = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=999):

                @faultcore.jitter("0.5s")
                def my_func():
                    return "ok"

                my_func()
                mock_shm.write_jitter.assert_called_once_with(999, 500)


class TestTimeoutDecoratorWritesCorrectFields:
    def test_timeout_writes_network_timeout_fields(self, monkeypatch):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.timeout(connect="2s", recv="500ms")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 2000, 500)
                mock_shm.write_latency.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_connect_timeout_writes_connect_only(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.timeout(connect="2s")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 2000, 0)
                mock_shm.clear.assert_called_once_with(12345)

    def test_recv_timeout_writes_recv_only(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.timeout(recv="500ms")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 0, 500)
                mock_shm.clear.assert_called_once_with(12345)


class TestRateLimitDecorator:
    def test_rate_limit_decorator_basic(self):
        @faultcore.rate("100mbps")
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_rate_limit_decorator_exceeded(self):
        mock_shm = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.rate("1mbps")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_bandwidth.assert_called_once()
                mock_shm.clear.assert_called_once()

    def test_rate_limit_passes_args(self):
        @faultcore.rate("100kbps")
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_rate_limit_passes_kwargs(self):
        @faultcore.rate("100kbps")
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15

    def test_rate_limit_decorator_with_args(self):
        @faultcore.rate("1000kbps")
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_rate_limit_decorator_with_kwargs(self):
        @faultcore.rate("1000kbps")
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15


class TestPacketLossDecorator:
    def test_packet_loss_decorator_writes_packet_loss_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=91011):

                @faultcore.packet_loss("2.5%")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_packet_loss.assert_called_once_with(91011, 25_000)
                mock_shm.clear.assert_called_once_with(91011)

    def test_parse_packet_loss_variants(self):
        assert _parse_packet_loss("0.5%") == 5_000
        assert _parse_packet_loss("25%") == 250_000
        assert _parse_packet_loss("250000ppm") == 250_000

    def test_parse_packet_loss_rejects_invalid_values(self):
        with pytest.raises(TypeError):
            _parse_packet_loss(0.5)
        with pytest.raises(TypeError):
            _parse_packet_loss(25)
        with pytest.raises(ValueError):
            _parse_packet_loss("101%")
        with pytest.raises(ValueError):
            _parse_packet_loss("2000000ppm")


class TestBurstLossDecorator:
    def test_burst_loss_decorator_writes_burst_len_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_burst_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.burst_loss(5)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_burst_loss.assert_called_once_with(12345, 5)
                mock_shm.clear.assert_called_once_with(12345)


class TestDirectionalDecorators:
    def test_uplink_writes_directional_fields_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_uplink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=11111):

                @faultcore.uplink(latency="100ms", jitter="10ms", packet_loss="1%", burst_loss=3, rate="10mbps")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_uplink.assert_called_once()
                mock_shm.clear.assert_called_once_with(11111)

    def test_downlink_writes_directional_fields_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_downlink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=22222):

                @faultcore.downlink(latency="200ms", jitter="20ms", packet_loss="2%", burst_loss=5, rate="20mbps")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_downlink.assert_called_once()
                mock_shm.clear.assert_called_once_with(22222)


class TestCorrelatedLossDecorator:
    def test_correlated_loss_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_correlated_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=33333):

                @faultcore.correlated_loss(p_good_to_bad="5%", p_bad_to_good="10%", loss_good="0%", loss_bad="50%")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_correlated_loss.assert_called_once()
                mock_shm.clear.assert_called_once_with(33333)


class TestConnectionErrorDecorators:
    def test_connection_error_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_connection_error = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=44444):

                @faultcore.connection_error(kind="reset", prob="100%")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_connection_error.assert_called_once()
                mock_shm.clear.assert_called_once_with(44444)

    def test_half_open_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_half_open = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=55555):

                @faultcore.half_open(after="1kb", error="reset")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_half_open.assert_called_once()
                mock_shm.clear.assert_called_once_with(55555)

    def test_half_open_rejects_invalid_threshold(self):
        with pytest.raises((ValueError, TypeError)):

            @faultcore.half_open(after="invalid", error="reset")
            def _bad():
                return "x"


class TestDuplicateAndReorderDecorators:
    def test_packet_duplicate_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_duplicate = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=66666):

                @faultcore.packet_duplicate(prob="10%", max_extra=2)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_packet_duplicate.assert_called_once()
                mock_shm.clear.assert_called_once_with(66666)

    def test_packet_reorder_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_reorder = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=77777):

                @faultcore.packet_reorder(prob="5%", max_delay="100ms", window=3)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_packet_reorder.assert_called_once()
                mock_shm.clear.assert_called_once_with(77777)

    def test_packet_reorder_writes_extended_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_reorder = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=88888):

                @faultcore.packet_reorder(prob="5%", max_delay="50ms", window=2)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_packet_reorder.assert_called_once()

    def test_packet_duplicate_rejects_invalid_max_extra(self):
        with pytest.raises(ValueError):

            @faultcore.packet_duplicate(prob="100%", max_extra=-1)
            def _bad():
                return "x"

    def test_packet_reorder_rejects_invalid_extended_fields(self):
        with pytest.raises((ValueError, TypeError)):

            @faultcore.packet_reorder(prob="100%", max_delay="invalid", window=1)
            def _bad():
                return "x"


class TestDnsDecorators:
    def test_dns_delay_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=99999):

                @faultcore.dns(delay="500ms")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_dns.assert_called_once()
                mock_shm.clear.assert_called_once_with(99999)

    def test_dns_timeout_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=10101):

                @faultcore.dns(timeout="2s")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_dns.assert_called_once()

    def test_dns_nxdomain_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=20202):

                @faultcore.dns(nxdomain="100%")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_dns.assert_called_once()

    def test_dns_combined_fields(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=30303):

                @faultcore.dns(delay="200ms", timeout="1s", nxdomain="50%")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_dns.assert_called_once()


class TestDecoratorMetadata:
    def test_decorator_preserves_function_name(self):
        @faultcore.latency("100ms")
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_decorator_preserves_function_docstring(self):
        @faultcore.latency("100ms")
        def my_function():
            """This is my docstring."""
            return "ok"

        assert my_function.__doc__ == "This is my docstring."

    def test_decorator_preserves_function_module(self):
        @faultcore.latency("100ms")
        def my_function():
            return "ok"

        assert my_function.__module__ is not None


class TestSessionBudgetDecorator:
    def test_session_budget_decorator_basic(self):
        @faultcore.session_budget(max_bytes_tx=1024, max_bytes_rx=2048)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_session_budget_with_action_drop(self):
        mock_shm = MagicMock()
        mock_shm.write_session_budget = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=40404):

                @faultcore.session_budget(max_ops=100, action="drop")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_session_budget.assert_called_once()
                mock_shm.clear.assert_called_once_with(40404)

    def test_session_budget_with_action_timeout(self):
        mock_shm = MagicMock()
        mock_shm.write_session_budget = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=50505):

                @faultcore.session_budget(max_ops=100, action="timeout", budget_timeout="5s")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_session_budget.assert_called_once()

    def test_session_budget_with_action_connection_error(self):
        mock_shm = MagicMock()
        mock_shm.write_session_budget = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=60606):

                @faultcore.session_budget(max_ops=100, action="connection_error", error="reset")
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_session_budget.assert_called_once()


class TestAsyncTimeoutDecorator:
    async def test_async_timeout_passes_args(self):
        @faultcore.timeout(connect="1s")
        async def func_with_args(a, b):
            return a + b

        result = await func_with_args(1, 2)
        assert result == 3

    async def test_async_timeout_passes_kwargs(self):
        @faultcore.timeout(connect="1s")
        async def func_with_kwargs(a=1, b=2):
            return a + b

        result = await func_with_kwargs(a=5, b=10)
        assert result == 15

    async def test_async_timeout_decorator_with_args(self):
        @faultcore.timeout(connect="1s")
        async def func_with_args(a, b):
            return a + b

        result = await func_with_args(1, 2)
        assert result == 3

    async def test_async_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(connect="1s")
        async def func_with_kwargs(a=1, b=2):
            return a + b

        result = await func_with_kwargs(a=5, b=10)
        assert result == 15


class TestTimeoutContract:
    def test_timeout_does_not_enforce_application_deadline(self):
        @faultcore.timeout(connect="100ms")
        def long_running_func():
            time.sleep(0.05)
            return "done"

        result = long_running_func()
        assert result == "done"

    def test_timeout_in_worker_thread_does_not_interrupt_execution(self):
        @faultcore.timeout(connect="1s")
        def func_with_sleep():
            time.sleep(0.01)
            return "completed"

        result = func_with_sleep()
        assert result == "completed"

    def test_timeout_in_worker_thread_allows_function_side_effects(self):
        results = []

        @faultcore.timeout(connect="1s")
        def func_with_side_effect():
            results.append("side_effect")
            return "done"

        func_with_side_effect()
        assert results == ["side_effect"]

    def test_timeout_worker_thread_runs_without_application_timeout_runtime(self):
        @faultcore.timeout(connect="1s")
        def my_func():
            return "ok"

        result = my_func()
        assert result == "ok"

    def test_timeout_worker_thread_handles_large_payload(self):
        @faultcore.timeout(connect="1s")
        def func_with_large_return():
            return "x" * 10000

        result = func_with_large_return()
        assert len(result) == 10000


class TestTimeoutShmLifecycle:
    def test_sync_timeout_clears_shm_on_success(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=70707):

                @faultcore.timeout(connect="1s")
                def my_func():
                    return "ok"

                my_func()
                mock_shm.clear.assert_called_once_with(70707)

    def test_sync_timeout_clears_shm_on_function_exception(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=80808):

                @faultcore.timeout(connect="1s")
                def my_func():
                    raise ValueError("test error")

                with pytest.raises(ValueError):
                    my_func()

                mock_shm.clear.assert_called_once_with(80808)


class TestAsyncShmLifecycle:
    async def test_async_decorator_keeps_policy_until_coroutine_finishes(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=90909):

                @faultcore.latency("100ms")
                async def my_func():
                    await asyncio.sleep(0.01)
                    return "ok"

                result = await my_func()
                assert result == "ok"
                mock_shm.clear.assert_called_once_with(90909)

    async def test_async_fault_context_is_isolated_per_task(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=11111):

                @faultcore.latency("50ms")
                async def task_func():
                    return "ok"

                result = await task_func()
                assert result == "ok"


class TestAwaitableLifecycle:
    async def test_non_coroutine_awaitable_keeps_shm_until_await(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.clear = MagicMock()

        class AwaitableValue:
            def __await__(self):
                yield
                return "result"

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12121):

                @faultcore.latency("50ms")
                def func_returning_awaitable():
                    return AwaitableValue()

                result = await func_returning_awaitable()
                assert result == "result"
