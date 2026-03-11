import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import faultcore
from faultcore.decorator import _parse_packet_loss, get_thread_policy


class TestTimeoutDecorator:
    def test_timeout_decorator_basic(self):
        @faultcore.connect_timeout(1000)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_decorator_zero(self):
        @faultcore.connect_timeout(1)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_passes_args(self):
        @faultcore.connect_timeout(1000)
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_timeout_passes_kwargs(self):
        @faultcore.connect_timeout(1000)
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15

    def test_timeout_passes_mixed_args(self):
        @faultcore.connect_timeout(1000)
        def func_mixed(a, b=10, c=20):
            return a + b + c

        result = func_mixed(5, c=100)
        assert result == 115

    def test_timeout_decorator_with_varargs(self):
        @faultcore.connect_timeout(1000)
        def func_with_varargs(*args):
            return sum(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    def test_timeout_decorator_with_kwargs(self):
        @faultcore.connect_timeout(1000)
        def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 6

    def test_timeout_decorator_with_args_and_kwargs(self):
        @faultcore.connect_timeout(1000)
        def func_mixed(*args, **kwargs):
            return sum(args) + sum(kwargs.values())

        result = func_mixed(1, 2, x=3, y=4)
        assert result == 10


class TestLatencyDecorator:
    def test_latency_decorator_writes_latency_to_shm(self, monkeypatch):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.latency(500)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_latency.assert_called_once_with(12345, 500)
                mock_shm.write_timeouts.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_latency_decorator_preserves_function_name(self):
        @faultcore.latency(100)
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_latency_write_failure_still_clears_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock(side_effect=RuntimeError("write failed"))
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=4242):

                @faultcore.latency(10)
                def my_func():
                    return "ok"

                with pytest.raises(RuntimeError, match="write failed"):
                    my_func()

                mock_shm.clear.assert_called_once_with(4242)


class TestJitterDecorator:
    def test_jitter_decorator_writes_jitter_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=999):

                @faultcore.jitter(25)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_jitter.assert_called_once_with(999, 25)
                mock_shm.clear.assert_called_once_with(999)

    def test_jitter_rejects_negative(self):
        with pytest.raises(ValueError):

            @faultcore.jitter(-1)
            def _bad():
                return "x"


class TestTimeoutDecoratorWritesCorrectFields:
    def test_timeout_writes_network_timeout_fields(self, monkeypatch):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.connect_timeout(2000)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 2000, 0)
                mock_shm.write_latency.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_connect_timeout_writes_connect_only(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12346):

                @faultcore.connect_timeout(1500)
                def my_func():
                    return "ok"

                assert my_func() == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12346, 1500, 0)
                mock_shm.clear.assert_called_once_with(12346)

    def test_recv_timeout_writes_recv_only(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12347):

                @faultcore.recv_timeout(800)
                def my_func():
                    return "ok"

                assert my_func() == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12347, 0, 800)
                mock_shm.clear.assert_called_once_with(12347)

    def test_connect_timeout_rejects_negative(self):
        with pytest.raises(ValueError):

            @faultcore.connect_timeout(-1)
            def _bad():
                return "x"

    def test_recv_timeout_rejects_negative(self):
        with pytest.raises(ValueError):

            @faultcore.recv_timeout(-1)
            def _bad():
                return "x"


class TestRateLimitDecorator:
    def test_rate_limit_decorator_basic(self):
        @faultcore.rate_limit(10.0)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_rate_limit_decorator_exceeded(self):
        @faultcore.rate_limit(1.0)
        def my_func():
            return "ok"

        assert my_func() == "ok"

        try:
            my_func()
        except Exception as e:
            assert "rate limit" in str(e).lower() or "resource" in str(e).lower()

    def test_rate_limit_passes_args(self):
        @faultcore.rate_limit(100.0)
        def func_with_args(a, b):
            return a**b

        result = func_with_args(2, 3)
        assert result == 8

    def test_rate_limit_passes_kwargs(self):
        @faultcore.rate_limit(100.0)
        def func_with_kwargs(base=1, exp=1):
            return base**exp

        result = func_with_kwargs(base=3, exp=4)
        assert result == 81

    def test_rate_limit_decorator_with_args(self):
        @faultcore.rate_limit(100.0)
        def func_with_varargs(*args):
            return len(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 5

    def test_rate_limit_decorator_with_kwargs(self):
        @faultcore.rate_limit(100.0)
        def func_with_kwargs(**kwargs):
            return len(kwargs)

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 3


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
        assert _parse_packet_loss(0.5) == 500_000
        assert _parse_packet_loss("0.5") == 500_000
        assert _parse_packet_loss(25) == 250_000
        assert _parse_packet_loss("25%") == 250_000
        assert _parse_packet_loss("250000ppm") == 250_000
        assert _parse_packet_loss(250_000) == 250_000

    def test_parse_packet_loss_rejects_invalid_values(self):
        with pytest.raises(ValueError):
            _parse_packet_loss(-1)
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
            with patch("faultcore.decorator.threading.get_native_id", return_value=91012):

                @faultcore.burst_loss(4)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_burst_loss.assert_called_once_with(91012, 4)
                mock_shm.clear.assert_called_once_with(91012)

    def test_burst_loss_rejects_negative(self):
        with pytest.raises(ValueError):

            @faultcore.burst_loss(-1)
            def _bad():
                return "x"


class TestDirectionalDecorators:
    def test_uplink_writes_directional_fields_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_uplink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=731):

                @faultcore.uplink(latency_ms=15, jitter_ms=3, packet_loss="0.5%", burst_loss_len=2, rate="2mbps")
                def my_func():
                    return "ok"

                assert my_func() == "ok"
                mock_shm.write_uplink.assert_called_once_with(
                    731,
                    latency_ms=15,
                    jitter_ms=3,
                    packet_loss_ppm=5_000,
                    burst_loss_len=2,
                    bandwidth_bps=2_000_000,
                )
                mock_shm.clear.assert_called_once_with(731)

    def test_downlink_writes_directional_fields_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_downlink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=732):

                @faultcore.downlink(latency_ms=25, rate="1mbps")
                def my_func():
                    return "ok"

                assert my_func() == "ok"
                mock_shm.write_downlink.assert_called_once_with(
                    732,
                    latency_ms=25,
                    jitter_ms=None,
                    packet_loss_ppm=None,
                    burst_loss_len=None,
                    bandwidth_bps=1_000_000,
                )
                mock_shm.clear.assert_called_once_with(732)

    def test_uplink_requires_at_least_one_field(self):
        with pytest.raises(ValueError):
            faultcore.uplink()

    def test_downlink_requires_at_least_one_field(self):
        with pytest.raises(ValueError):
            faultcore.downlink()


class TestCorrelatedLossDecorator:
    def test_correlated_loss_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_correlated_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=975):

                @faultcore.correlated_loss(
                    p_good_to_bad="1%",
                    p_bad_to_good="20%",
                    loss_good="0.1%",
                    loss_bad="15%",
                )
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_correlated_loss.assert_called_once_with(
                    975,
                    enabled=True,
                    p_good_to_bad_ppm=10_000,
                    p_bad_to_good_ppm=200_000,
                    loss_good_ppm=1_000,
                    loss_bad_ppm=150_000,
                )
                mock_shm.clear.assert_called_once_with(975)


class TestConnectionErrorDecorators:
    def test_connection_error_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_connection_error = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=976):

                @faultcore.connection_error(kind="refused", prob="2.5%")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_connection_error.assert_called_once_with(
                    976,
                    kind=2,
                    prob_ppm=25_000,
                )
                mock_shm.clear.assert_called_once_with(976)

    def test_half_open_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_half_open = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=977):

                @faultcore.half_open(after_bytes=4096, error="reset")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_half_open.assert_called_once_with(
                    977,
                    after_bytes=4096,
                    err_kind=1,
                )
                mock_shm.clear.assert_called_once_with(977)

    def test_half_open_rejects_invalid_threshold(self):
        with pytest.raises(ValueError):
            faultcore.half_open(after_bytes=0)


class TestDuplicateAndReorderDecorators:
    def test_packet_duplicate_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_duplicate = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=978):

                @faultcore.packet_duplicate(prob="2%", max_extra=3)
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_duplicate.assert_called_once_with(
                    978,
                    prob_ppm=20_000,
                    max_extra=3,
                )
                mock_shm.clear.assert_called_once_with(978)

    def test_packet_reorder_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_reorder = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=979):

                @faultcore.packet_reorder(prob="1.5%")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_reorder.assert_called_once_with(
                    979,
                    prob_ppm=15_000,
                    max_delay_ns=0,
                    window=1,
                )
                mock_shm.clear.assert_called_once_with(979)

    def test_packet_reorder_writes_extended_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_packet_reorder = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=983):

                @faultcore.packet_reorder(prob="2%", max_delay_ms=75, window=4)
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_reorder.assert_called_once_with(
                    983,
                    prob_ppm=20_000,
                    max_delay_ns=75_000_000,
                    window=4,
                )
                mock_shm.clear.assert_called_once_with(983)

    def test_packet_duplicate_rejects_invalid_max_extra(self):
        with pytest.raises(ValueError):
            faultcore.packet_duplicate(max_extra=0)

    def test_packet_reorder_rejects_invalid_extended_fields(self):
        with pytest.raises(ValueError):
            faultcore.packet_reorder(max_delay_ms=-1)
        with pytest.raises(ValueError):
            faultcore.packet_reorder(window=0)


class TestDnsDecorators:
    def test_dns_delay_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=980):

                @faultcore.dns_delay(250)
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_dns.assert_called_once_with(
                    980,
                    delay_ms=250,
                    timeout_ms=None,
                    nxdomain_ppm=None,
                )
                mock_shm.clear.assert_called_once_with(980)

    def test_dns_timeout_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=981):

                @faultcore.dns_timeout(1000)
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_dns.assert_called_once_with(
                    981,
                    delay_ms=None,
                    timeout_ms=1000,
                    nxdomain_ppm=None,
                )
                mock_shm.clear.assert_called_once_with(981)

    def test_dns_nxdomain_writes_profile_to_shm(self):
        mock_shm = MagicMock()
        mock_shm.write_dns = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=982):

                @faultcore.dns_nxdomain("12.5%")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_dns.assert_called_once_with(
                    982,
                    delay_ms=None,
                    timeout_ms=None,
                    nxdomain_ppm=125_000,
                )
                mock_shm.clear.assert_called_once_with(982)


class TestDecoratorMetadata:
    def test_decorator_preserves_function_name(self):
        @faultcore.connect_timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_decorator_preserves_function_docstring(self):
        @faultcore.connect_timeout(1000)
        def my_function():
            """This is my docstring."""
            return "ok"

        assert my_function.__doc__ == "This is my docstring."

    def test_decorator_preserves_function_module(self):
        @faultcore.connect_timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__module__ is not None


class TestAsyncTimeoutDecorator:
    async def test_async_timeout_passes_args(self):
        @faultcore.connect_timeout(1000)
        async def async_func(a, b):
            return a + b

        result = await async_func(10, 20)
        assert result == 30

    async def test_async_timeout_passes_kwargs(self):
        @faultcore.connect_timeout(1000)
        async def async_func(a=0, b=0):
            return a + b

        result = await async_func(a=100, b=200)
        assert result == 300

    async def test_async_timeout_decorator_with_args(self):
        @faultcore.connect_timeout(1000)
        async def func_with_varargs(*args):
            return sum(args)

        result = await func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    async def test_async_timeout_decorator_with_kwargs(self):
        @faultcore.connect_timeout(1000)
        async def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = await func_with_kwargs(a=1, b=2, c=3)
        assert result == 6


class TestTimeoutContract:
    def test_timeout_does_not_enforce_application_deadline(self):
        @faultcore.connect_timeout(5)
        def slow_operation():
            time.sleep(0.02)
            return "done"

        assert slow_operation() == "done"

    def test_timeout_in_worker_thread_does_not_interrupt_execution(self):
        @faultcore.connect_timeout(5)
        def slow_operation():
            time.sleep(0.05)
            return "done"

        outcome: dict[str, object] = {}

        def worker() -> None:
            try:
                outcome["result"] = slow_operation()
                outcome["error"] = None
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert outcome["error"] is None
        assert outcome["result"] == "done"

    def test_timeout_in_worker_thread_allows_function_side_effects(self):
        side_effect = threading.Event()

        @faultcore.connect_timeout(5)
        def slow_operation():
            time.sleep(0.05)
            side_effect.set()

        outcome: dict[str, object] = {}

        def worker() -> None:
            try:
                slow_operation()
                outcome["error"] = None
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert outcome["error"] is None
        assert side_effect.is_set() is True

    def test_timeout_worker_thread_runs_without_application_timeout_runtime(self):
        @faultcore.connect_timeout(50)
        def fast_operation():
            return "ok"

        outcome: dict[str, object] = {}

        def worker() -> None:
            try:
                outcome["result"] = fast_operation()
                outcome["error"] = None
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert outcome["error"] is None
        assert outcome["result"] == "ok"

    def test_timeout_worker_thread_handles_large_payload(self):
        @faultcore.connect_timeout(100)
        def produce_large_payload():
            return "x" * 200_000

        outcome: dict[str, object] = {}

        def worker() -> None:
            try:
                outcome["result"] = produce_large_payload()
                outcome["error"] = None
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert outcome["error"] is None
        assert len(outcome["result"]) == 200_000


class TestTimeoutShmLifecycle:
    def test_sync_timeout_clears_shm_on_success(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=777):

                @faultcore.connect_timeout(5)
                def slow_operation():
                    return "ok"

                assert slow_operation() == "ok"

                mock_shm.write_timeouts.assert_called_once_with(777, 5, 0)
                mock_shm.clear.assert_called_once_with(777)

    def test_sync_timeout_clears_shm_on_function_exception(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=778):

                @faultcore.connect_timeout(100)
                def failing_operation():
                    raise RuntimeError("boom")

                with pytest.raises(RuntimeError, match="boom"):
                    failing_operation()

                mock_shm.write_timeouts.assert_called_once_with(778, 100, 0)
                mock_shm.clear.assert_called_once_with(778)

    async def test_async_timeout_clears_shm_on_success(self):
        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=779):

                @faultcore.connect_timeout(10)
                async def slow_async():
                    await asyncio.sleep(0.001)
                    return "ok"

                assert await slow_async() == "ok"

                mock_shm.write_timeouts.assert_called_once_with(779, 10, 0)
                mock_shm.clear.assert_called_once_with(779)


class TestAsyncShmLifecycle:
    async def test_async_decorator_keeps_policy_until_coroutine_finishes(self):
        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=321):

                @faultcore.connect_timeout(100)
                async def async_op():
                    return "ok"

                pending = async_op()
                try:
                    assert mock_shm.clear.call_count == 0
                finally:
                    result = await pending
                    assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(321, 100, 0)
                mock_shm.clear.assert_called_once_with(321)

    async def test_async_fault_context_is_isolated_per_task(self):

        started = asyncio.Event()
        release = asyncio.Event()
        observed: list[str | None] = []

        async def holder() -> None:
            async with faultcore.fault_context("inner"):
                started.set()
                await release.wait()

        async def observer() -> None:
            await started.wait()
            observed.append(get_thread_policy())
            release.set()

        faultcore.set_thread_policy("outer")
        try:
            await asyncio.gather(holder(), observer())
            assert observed == ["outer"]
        finally:
            faultcore.set_thread_policy(None)
