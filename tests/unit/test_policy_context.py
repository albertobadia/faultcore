from unittest.mock import MagicMock, patch

import pytest

import faultcore
from faultcore.decorator import clear_policies, get_thread_policy, list_policies


@pytest.fixture(autouse=True)
def _cleanup_policies_and_context():
    clear_policies()
    faultcore.set_thread_policy(None)
    yield
    clear_policies()
    faultcore.set_thread_policy(None)


def test_policy_context_sets_and_restores_thread_policy():
    faultcore.set_thread_policy("outer")
    with faultcore.policy_context("inner"):
        assert get_thread_policy() == "inner"
    assert get_thread_policy() == "outer"


def test_policy_context_can_create_temporary_policy_from_kwargs():
    before = set(list_policies())
    with faultcore.policy_context(latency_ms=20):
        active = get_thread_policy()
        assert active is not None
        assert active.startswith("__faultcore_temp_")
        assert faultcore.get_policy(active) is not None
    after = set(list_policies())
    assert before == after


def test_policy_context_rejects_name_and_kwargs_together():
    with pytest.raises(ValueError, match="either policy_name or policy kwargs"):
        faultcore.policy_context("slow_link", latency_ms=20)


def test_temporary_policy_context_applies_with_fault_auto():
    mock_shm = MagicMock()
    mock_shm.write_latency = MagicMock()
    mock_shm.clear = MagicMock()

    with patch("faultcore.decorator.get_shm_writer", return_value=mock_shm):
        with patch("faultcore.decorator.threading.get_native_id", return_value=5154):

            @faultcore.fault()
            def op():
                return "ok"

            with faultcore.policy_context(latency_ms=25):
                assert op() == "ok"

    mock_shm.write_latency.assert_called_once_with(5154, 25)
    mock_shm.clear.assert_called_once_with(5154)

