import pytest

import faultcore


def test_removed_utility_symbols_are_not_exported() -> None:
    with pytest.raises(AttributeError):
        _ = faultcore.is_interceptor_loaded
    with pytest.raises(AttributeError):
        _ = faultcore.get_interceptor_path
    with pytest.raises(AttributeError):
        _ = faultcore.get_fault_metrics


def test_register_policy_rejects_timeout_ms_keyword() -> None:
    with pytest.raises(TypeError):
        faultcore.register_policy("bad_timeout_alias", timeout_ms=10)  # type: ignore[call-arg]
