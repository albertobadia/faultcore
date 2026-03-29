import os
import socket
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_IT_PROFILE_CASES: dict[str, dict[str, list[int | float]]] = {
    "smoke": {
        "probe_timeout_ms": [500],
        "probe_timeout_sec": [1.0],
        "probe_count": [3],
        "probe_data_size": [512],
        "probe_duration_sec": [1.0],
        "probe_num_messages": [10],
    },
    "full": {
        "probe_timeout_ms": [250, 1000],
        "probe_timeout_sec": [1.0, 2.0],
        "probe_count": [3, 5],
        "probe_data_size": [512, 1024],
        "probe_duration_sec": [1.0, 2.0],
        "probe_num_messages": [10, 20],
    },
}


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return monkeypatch


@pytest.fixture
def temp_shm_dir(tmp_path: Path) -> Path:
    shm_dir = tmp_path / "shm"
    shm_dir.mkdir()
    return shm_dir


@pytest.fixture
def mock_interceptor() -> MagicMock:
    mock = MagicMock()
    mock.is_active.return_value = True
    return mock


@pytest.fixture
def sample_policy_config() -> dict[str, int | float]:
    return {
        "connect_timeout_ms": 1000,
        "recv_timeout_ms": 1000,
        "rate_limit_mbps": 10.0,
        "latency_injection_ms": 0,
    }


@pytest.fixture(autouse=True)
def cleanup_env() -> Iterator[None]:
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "integration_network: marks network integration tests")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("faultcore-integration")
    group.addoption(
        "--it-host",
        action="store",
        default=os.getenv("FAULTCORE_IT_HOST", "127.0.0.1"),
        help="Host for network integration probes",
    )
    group.addoption(
        "--it-port",
        action="store",
        type=int,
        default=int(os.getenv("FAULTCORE_IT_PORT", "9000")),
        help="Port for network integration probes",
    )
    group.addoption(
        "--it-connect-timeout",
        action="store",
        type=float,
        default=float(os.getenv("FAULTCORE_IT_CONNECT_TIMEOUT", "0.35")),
        help="Timeout (seconds) for test endpoint reachability check",
    )
    group.addoption(
        "--it-profile",
        action="store",
        choices=tuple(_IT_PROFILE_CASES.keys()),
        default=os.getenv("FAULTCORE_IT_PROFILE", "smoke"),
        help="Network integration scenario profile",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    profile = metafunc.config.getoption("--it-profile")
    cases = _IT_PROFILE_CASES[profile]
    for arg_name, values in cases.items():
        if arg_name in metafunc.fixturenames:
            ids = [f"{arg_name}={value}" for value in values]
            metafunc.parametrize(arg_name, values, ids=ids)


@pytest.fixture
def host(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--it-host"))


@pytest.fixture
def port(pytestconfig: pytest.Config) -> int:
    return int(pytestconfig.getoption("--it-port"))


@pytest.fixture
def message() -> str:
    return "Hello FaultCore"


@pytest.fixture
def reachable_endpoint(host: str, port: int, pytestconfig: pytest.Config) -> tuple[str, int]:
    timeout = float(pytestconfig.getoption("--it-connect-timeout"))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((host, port)) != 0:
                pytest.skip(
                    f"integration endpoint {host}:{port} unreachable; "
                    "set --it-host/--it-port (or FAULTCORE_IT_HOST/FAULTCORE_IT_PORT)"
                )
    except OSError as exc:
        pytest.skip(f"socket setup not available in this environment: {exc}")
    return host, port
