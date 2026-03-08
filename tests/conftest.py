import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_env(monkeypatch):
    return monkeypatch


@pytest.fixture
def temp_shm_dir(tmp_path):
    shm_dir = tmp_path / "shm"
    shm_dir.mkdir()
    return shm_dir


@pytest.fixture
def mock_interceptor():
    mock = MagicMock()
    mock.is_active.return_value = True
    return mock


@pytest.fixture
def sample_policy_config():
    return {
        "timeout_ms": 1000,
        "rate_limit_mbps": 10.0,
        "latency_injection_ms": 0,
    }


@pytest.fixture(autouse=True)
def cleanup_env():
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
