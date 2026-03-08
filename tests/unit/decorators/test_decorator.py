import asyncio
import json
import threading
import time

import pytest

import faultcore


class TestTimeoutDecorator:
    def test_timeout_decorator_basic(self):
        @faultcore.timeout(1000)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_decorator_zero(self):
        @faultcore.timeout(1)
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_timeout_passes_args(self):
        @faultcore.timeout(1000)
        def func_with_args(a, b):
            return a + b

        result = func_with_args(1, 2)
        assert result == 3

    def test_timeout_passes_kwargs(self):
        @faultcore.timeout(1000)
        def func_with_kwargs(a=1, b=2):
            return a + b

        result = func_with_kwargs(a=5, b=10)
        assert result == 15

    def test_timeout_passes_mixed_args(self):
        @faultcore.timeout(1000)
        def func_mixed(a, b=10, c=20):
            return a + b + c

        result = func_mixed(5, c=100)
        assert result == 115

    def test_timeout_decorator_with_varargs(self):
        @faultcore.timeout(1000)
        def func_with_varargs(*args):
            return sum(args)

        result = func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    def test_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(1000)
        def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = func_with_kwargs(a=1, b=2, c=3)
        assert result == 6

    def test_timeout_decorator_with_args_and_kwargs(self):
        @faultcore.timeout(1000)
        def func_mixed(*args, **kwargs):
            return sum(args) + sum(kwargs.values())

        result = func_mixed(1, 2, x=3, y=4)
        assert result == 10


class TestLatencyDecorator:
    def test_latency_decorator_writes_latency_to_shm(self, monkeypatch):
        from unittest.mock import MagicMock, patch

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


class TestJitterDecorator:
    def test_jitter_decorator_writes_jitter_to_shm(self):
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=12345):

                @faultcore.timeout(2000)
                def my_func():
                    return "ok"

                result = my_func()
                assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(12345, 2000, 2000)
                mock_shm.write_latency.assert_not_called()
                mock_shm.clear.assert_called_once_with(12345)

    def test_connect_timeout_writes_connect_only(self):
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

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
        from faultcore.decorator import _parse_packet_loss

        assert _parse_packet_loss(0.5) == 500_000
        assert _parse_packet_loss("0.5") == 500_000
        assert _parse_packet_loss(25) == 250_000
        assert _parse_packet_loss("25%") == 250_000
        assert _parse_packet_loss("250000ppm") == 250_000
        assert _parse_packet_loss(250_000) == 250_000

    def test_parse_packet_loss_rejects_invalid_values(self):
        from faultcore.decorator import _parse_packet_loss

        with pytest.raises(ValueError):
            _parse_packet_loss(-1)
        with pytest.raises(ValueError):
            _parse_packet_loss("101%")
        with pytest.raises(ValueError):
            _parse_packet_loss("2000000ppm")


class TestBurstLossDecorator:
    def test_burst_loss_decorator_writes_burst_len_to_shm(self):
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

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
        from unittest.mock import MagicMock, patch

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


class TestPolicyRegistry:
    def test_apply_policy_uses_registered_policy(self):
        from unittest.mock import MagicMock, patch

        faultcore.register_policy(
            "slow_link",
            latency_ms=50,
            jitter_ms=10,
            packet_loss="1%",
            burst_loss_len=3,
            rate="2mbps",
            timeout_ms=20,
        )

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.write_burst_loss = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=5150):

                @faultcore.apply_policy("slow_link")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(5150, 50)
                mock_shm.write_jitter.assert_called_once_with(5150, 10)
                mock_shm.write_packet_loss.assert_called_once_with(5150, 10_000)
                mock_shm.write_burst_loss.assert_called_once_with(5150, 3)
                mock_shm.write_bandwidth.assert_called_once_with(5150, 2_000_000)
                mock_shm.write_timeouts.assert_called_once_with(5150, 20, 20)
                mock_shm.clear.assert_called_once_with(5150)

    def test_fault_auto_reads_thread_policy(self):
        from unittest.mock import MagicMock, patch

        faultcore.register_policy("auto_policy", packet_loss="0.1%")
        faultcore.set_thread_policy("auto_policy")

        mock_shm = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=5151):

                @faultcore.fault()
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_packet_loss.assert_called_once_with(5151, 1_000)
                mock_shm.clear.assert_called_once_with(5151)

        faultcore.set_thread_policy(None)

    def test_fault_context_sets_and_restores_thread_policy(self):
        faultcore.set_thread_policy("outer")
        with faultcore.fault_context("inner"):
            from faultcore.decorator import get_thread_policy

            assert get_thread_policy() == "inner"
        from faultcore.decorator import get_thread_policy

        assert get_thread_policy() == "outer"
        faultcore.set_thread_policy(None)

    def test_register_policy_with_split_timeouts(self):
        from unittest.mock import MagicMock, patch

        faultcore.register_policy("split_timeouts", connect_timeout_ms=321, recv_timeout_ms=654)

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=612):

                @faultcore.apply_policy("split_timeouts")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_timeouts.assert_called_once_with(612, 321, 654)
                mock_shm.clear.assert_called_once_with(612)

    def test_register_policy_with_uplink_and_downlink_profiles(self):
        from unittest.mock import MagicMock, patch

        faultcore.register_policy(
            "directional",
            uplink={"latency_ms": 10, "rate": "5mbps"},
            downlink={"packet_loss": "1.5%", "jitter_ms": 4},
        )

        mock_shm = MagicMock()
        mock_shm.write_uplink = MagicMock()
        mock_shm.write_downlink = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=890):

                @faultcore.apply_policy("directional")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_uplink.assert_called_once_with(
                    890,
                    latency_ms=10,
                    jitter_ms=None,
                    packet_loss_ppm=None,
                    burst_loss_len=None,
                    bandwidth_bps=5_000_000,
                )
                mock_shm.write_downlink.assert_called_once_with(
                    890,
                    latency_ms=None,
                    jitter_ms=4,
                    packet_loss_ppm=15_000,
                    burst_loss_len=None,
                    bandwidth_bps=None,
                )
                mock_shm.clear.assert_called_once_with(890)

    def test_register_policy_with_correlated_loss_profile(self):
        from unittest.mock import MagicMock, patch

        faultcore.register_policy(
            "ge_policy",
            correlated_loss={
                "p_good_to_bad": "2%",
                "p_bad_to_good": "40%",
                "loss_good": "0.2%",
                "loss_bad": "18%",
            },
        )

        mock_shm = MagicMock()
        mock_shm.write_correlated_loss = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=891):

                @faultcore.apply_policy("ge_policy")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_correlated_loss.assert_called_once_with(
                    891,
                    enabled=True,
                    p_good_to_bad_ppm=20_000,
                    p_bad_to_good_ppm=400_000,
                    loss_good_ppm=2_000,
                    loss_bad_ppm=180_000,
                )
                mock_shm.clear.assert_called_once_with(891)

    def test_register_policy_rejects_invalid_values(self):
        with pytest.raises(ValueError):
            faultcore.register_policy("", latency_ms=1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad1", latency_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad2", jitter_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad3", timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad4", connect_timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad5", recv_timeout_ms=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad6", rate=-1)
        with pytest.raises(ValueError):
            faultcore.register_policy("bad7", uplink="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad8", downlink="invalid")
        with pytest.raises(ValueError):
            faultcore.register_policy("bad9", correlated_loss="invalid")

    def test_registry_introspection_and_unregister(self):
        from faultcore.decorator import clear_policies

        clear_policies()
        faultcore.register_policy("b_policy", latency_ms=2)
        faultcore.register_policy("a_policy", latency_ms=1)

        assert faultcore.list_policies() == ["a_policy", "b_policy"]
        assert faultcore.get_policy("a_policy") == {"latency_ms": 1}
        assert faultcore.get_policy("missing") is None

        assert faultcore.unregister_policy("a_policy") is True
        assert faultcore.unregister_policy("a_policy") is False
        assert faultcore.list_policies() == ["b_policy"]

    def test_registry_thread_safety_under_parallel_updates(self):
        from faultcore.decorator import clear_policies

        clear_policies()

        def worker(idx: int) -> None:
            name = f"p{idx}"
            faultcore.register_policy(name, latency_ms=idx)
            assert faultcore.get_policy(name) is not None
            assert faultcore.unregister_policy(name) is True

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert faultcore.list_policies() == []

    def test_load_policies_from_json(self, tmp_path):
        file_path = tmp_path / "policies.json"
        file_path.write_text(
            json.dumps(
                {
                    "from_file": {
                        "latency_ms": 7,
                        "jitter_ms": 3,
                        "packet_loss": "0.2%",
                        "burst_loss_len": 2,
                        "rate": "1mbps",
                        "timeout_ms": 9,
                    }
                }
            )
        )

        loaded = faultcore.load_policies(file_path)
        assert loaded == 1

        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_jitter = MagicMock()
        mock_shm.write_packet_loss = MagicMock()
        mock_shm.write_burst_loss = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=611):

                @faultcore.apply_policy("from_file")
                def op():
                    return "ok"

                assert op() == "ok"
                mock_shm.write_latency.assert_called_once_with(611, 7)
                mock_shm.write_jitter.assert_called_once_with(611, 3)
                mock_shm.write_packet_loss.assert_called_once_with(611, 2_000)
                mock_shm.write_burst_loss.assert_called_once_with(611, 2)
                mock_shm.write_bandwidth.assert_called_once_with(611, 1_000_000)
                mock_shm.write_timeouts.assert_called_once_with(611, 9, 9)


class TestDecoratorMetadata:
    def test_decorator_preserves_function_name(self):
        @faultcore.timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_decorator_preserves_function_docstring(self):
        @faultcore.timeout(1000)
        def my_function():
            """This is my docstring."""
            return "ok"

        assert my_function.__doc__ == "This is my docstring."

    def test_decorator_preserves_function_module(self):
        @faultcore.timeout(1000)
        def my_function():
            return "ok"

        assert my_function.__module__ is not None


class TestAsyncTimeoutDecorator:
    async def test_async_timeout_passes_args(self):
        @faultcore.timeout(1000)
        async def async_func(a, b):
            return a + b

        result = await async_func(10, 20)
        assert result == 30

    async def test_async_timeout_passes_kwargs(self):
        @faultcore.timeout(1000)
        async def async_func(a=0, b=0):
            return a + b

        result = await async_func(a=100, b=200)
        assert result == 300

    async def test_async_timeout_decorator_with_args(self):
        @faultcore.timeout(1000)
        async def func_with_varargs(*args):
            return sum(args)

        result = await func_with_varargs(1, 2, 3, 4, 5)
        assert result == 15

    async def test_async_timeout_decorator_with_kwargs(self):
        @faultcore.timeout(1000)
        async def func_with_kwargs(**kwargs):
            return sum(kwargs.values())

        result = await func_with_kwargs(a=1, b=2, c=3)
        assert result == 6


class TestTimeoutContract:
    def test_timeout_enforces_function_execution_deadline(self):
        @faultcore.timeout(5)
        def slow_operation():
            time.sleep(0.02)
            return "done"

        with pytest.raises(TimeoutError):
            slow_operation()


class TestTimeoutShmLifecycle:
    def test_sync_timeout_clears_shm_on_timeout_error(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=777):

                @faultcore.timeout(5)
                def slow_operation():
                    time.sleep(0.02)

                with pytest.raises(TimeoutError):
                    slow_operation()

                mock_shm.write_timeouts.assert_called_once_with(777, 5, 5)
                mock_shm.clear.assert_called_once_with(777)

    def test_sync_timeout_clears_shm_on_function_exception(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=778):

                @faultcore.timeout(100)
                def failing_operation():
                    raise RuntimeError("boom")

                with pytest.raises(RuntimeError, match="boom"):
                    failing_operation()

                mock_shm.write_timeouts.assert_called_once_with(778, 100, 100)
                mock_shm.clear.assert_called_once_with(778)

    async def test_async_timeout_clears_shm_on_timeout_error(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=779):

                @faultcore.timeout(10)
                async def slow_async():
                    await asyncio.sleep(0.05)

                with pytest.raises(TimeoutError):
                    await slow_async()

                mock_shm.write_timeouts.assert_called_once_with(779, 10, 10)
                mock_shm.clear.assert_called_once_with(779)


class TestAsyncShmLifecycle:
    async def test_async_decorator_keeps_policy_until_coroutine_finishes(self):
        from unittest.mock import MagicMock, patch

        mock_shm = MagicMock()
        mock_shm.write_latency = MagicMock()
        mock_shm.write_timeouts = MagicMock()
        mock_shm.write_bandwidth = MagicMock()
        mock_shm.clear = MagicMock()

        with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
            with patch("faultcore.decorator.threading.get_native_id", return_value=321):

                @faultcore.timeout(100)
                async def async_op():
                    return "ok"

                pending = async_op()
                try:
                    assert mock_shm.clear.call_count == 0
                finally:
                    result = await pending
                    assert result == "ok"
                mock_shm.write_timeouts.assert_called_once_with(321, 100, 100)
                mock_shm.clear.assert_called_once_with(321)
