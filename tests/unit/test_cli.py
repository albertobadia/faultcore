import json
from types import SimpleNamespace

from typer.testing import CliRunner

from faultcore import cli

runner = CliRunner()


def test_compose_preload_without_existing_value(monkeypatch) -> None:
    monkeypatch.delenv("LD_PRELOAD", raising=False)
    assert cli._compose_preload("/faultcore/libfaultcore_interceptor.so") == "/faultcore/libfaultcore_interceptor.so"


def test_compose_preload_appends_existing_value(monkeypatch) -> None:
    monkeypatch.setenv("LD_PRELOAD", "/already.so")
    assert cli._compose_preload("/faultcore/libfaultcore_interceptor.so") == (
        "/faultcore/libfaultcore_interceptor.so /already.so"
    )


def test_run_command_linux_strict_fails_when_probe_fails(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: False)

    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["run", "--", "python", "-V"])
    assert result.exit_code == 2
    assert "strict mode requires active interceptor" in result.stderr
    assert calls == []


def test_run_command_linux_strict_success_executes_with_ld_preload(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: True)
    monkeypatch.setenv("LD_PRELOAD", "/existing.so")

    calls = []

    def fake_run(args, *, env, check, capture_output, text):
        calls.append((args, env, check, capture_output, text))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["run", "--", "python", "-V"])
    assert result.exit_code == 7
    assert len(calls) == 1
    args, env, check, capture_output, text = calls[0]
    assert args == ["python", "-V"]
    assert check is False
    assert capture_output is False
    assert text is False
    assert env["LD_PRELOAD"] == "/faultcore/interceptor.so /existing.so"
    assert env["FAULTCORE_SHM_OPEN_MODE"] == "creator"


def test_run_command_writes_run_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_run_record",
        lambda **kwargs: {
            "status": "passed",
            "tool": {"command": kwargs["command"]},
            "process": {"exit_code": kwargs["returncode"]},
        },
    )

    def fake_run(args, **_kwargs):
        assert args == ["python", "-V"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    run_json = tmp_path / "run.json"
    result = runner.invoke(cli.app, ["run", "--run-json", str(run_json), "--", "python", "-V"])
    assert result.exit_code == 0
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["status"] == "passed"
    assert data["tool"]["command"] == ["python", "-V"]
    assert data["process"]["exit_code"] == 0


def test_run_command_python_script_uses_current_interpreter(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)

    calls = []

    def fake_run(args, *, env, check, capture_output, text):
        calls.append((args, env, check, capture_output, text))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["run", "main.py"])
    assert result.exit_code == 0
    assert len(calls) == 1
    args, env, check, capture_output, text = calls[0]
    assert args == [cli.sys.executable, "main.py"]
    assert env["FAULTCORE_SHM_OPEN_MODE"] == "creator"
    assert check is False
    assert capture_output is False
    assert text is False


def test_run_command_strict_failure_writes_run_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: False)
    monkeypatch.setattr(
        cli,
        "build_run_record",
        lambda **kwargs: {
            "status": "failed",
            "tool": {"command": kwargs["command"]},
            "process": {"exit_code": kwargs["returncode"]},
        },
    )

    run_json = tmp_path / "run_fail.json"
    result = runner.invoke(cli.app, ["run", "--run-json", str(run_json), "--", "python", "-V"])
    assert result.exit_code == 2
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["process"]["exit_code"] == 2


def test_run_command_pytest_populates_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)

    def fake_run(args, **kwargs):
        if args == ["pytest", "-q"]:
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True
            return SimpleNamespace(
                returncode=1,
                stdout="=================== 3 passed, 1 failed in 0.42s ===================\n",
                stderr="",
            )
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    run_json = tmp_path / "run_pytest.json"
    result = runner.invoke(cli.app, ["run", "--run-json", str(run_json), "--", "pytest", "-q"])
    assert result.exit_code == 1
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["summary"]["tests_total"] == 4
    assert data["summary"]["tests_passed"] == 3
    assert data["summary"]["tests_failed"] == 1
    assert data["summary"]["errors"] == 0
    assert any(event["type"] == "pytest.summary" for event in data["events"])
    assert data["logs"]["stdout_tail"]


def test_run_command_replay_mode_populates_metrics_from_record_replay(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)
    rr_path = tmp_path / "shared.rr.jsonl.gz"
    rr_path.write_bytes(b"placeholder")
    monkeypatch.setenv("FAULTCORE_RECORD_REPLAY_MODE", "replay")
    monkeypatch.setenv("FAULTCORE_RECORD_REPLAY_PATH", str(rr_path))

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli,
        "load_record_replay_events",
        lambda path: [{"decision": "delay_ns", "value": 100, "site": "x"}] if path == rr_path else [],
    )
    monkeypatch.setattr(
        cli,
        "summarize_record_replay",
        lambda _events: {"recorded_events_total": 1, "fault_events_total": 1, "delay_count": 1},
    )
    monkeypatch.setattr(cli, "build_record_replay_series", lambda _events: {"delay_ns": [100]})
    monkeypatch.setattr(cli, "build_record_replay_sites", lambda _events: ["x"])
    monkeypatch.setattr(
        cli,
        "build_record_replay_site_metrics",
        lambda _events: {
            "x": {
                "total_events": 1,
                "fault_events": 1,
                "fault_rate_pct": 100.0,
                "decision_counts": {"delay_ns": 1},
                "latency_p50_ns": 100,
                "latency_p95_ns": 100,
                "latency_p99_ns": 100,
                "delay_series_ns": [100],
                "inferred_config": {"delay_active": True},
            }
        },
    )
    monkeypatch.setattr(
        cli,
        "build_record_replay_timeline_events",
        lambda _events, ts: [
            {
                "ts": ts,
                "severity": "warning",
                "type": "network.delay_ns",
                "source": "record_replay",
                "name": "x",
                "details": {"value": 100},
            }
        ],
    )

    run_json = tmp_path / "run_replay.json"
    result = runner.invoke(cli.app, ["run", "--run-json", str(run_json), "--", "python", "-V"])
    assert result.exit_code == 1
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["faultcore"]["record_replay_path"] == str(rr_path)
    assert data["summary"]["fault_events_total"] == 1
    assert data["network_metrics"]["recorded_events_total"] == 1
    assert any(event["type"] == "network.delay_ns" for event in data["events"])


def test_run_command_merges_metrics_out_json_into_run_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)

    metrics_path = tmp_path / "network_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "scenario": {"iterations": 3, "duration_ms": 999},
                "latency_ms": {"tcp_avg": 10.5, "udp_avg": 2.25, "http_avg": 15.75},
                "jitter_ms": {"tcp": 1.5, "udp": 0.5, "http": 2.5},
                "bytes": {"tcp_total": 10, "udp_total": 20, "http_total": 30, "total": 60},
                "throughput_bps": {"tcp": 100, "udp": 200, "http": 300, "total": 600},
                "series": {"tcp_latency_ms": [1.0, 2.0], "udp_latency_ms": [0.5, 1.5]},
                "functions": {"tcp_roundtrip": {"throughput_bps": 100, "series_latency_ms": [1.0, 2.0]}},
            }
        ),
        encoding="utf-8",
    )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    run_json = tmp_path / "run_metrics.json"
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--run-json",
            str(run_json),
            "--",
            "python",
            "scenario.py",
            "--metrics-out",
            str(metrics_path),
        ],
    )
    assert result.exit_code == 0
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["network_metrics"]["scenario_iterations"] == 3
    assert data["network_metrics"]["tcp_latency_avg_ms"] == 10.5
    assert data["network_metrics"]["total_bytes"] == 60
    assert data["network_series"]["tcp_latency_ms"] == [1_000_000, 2_000_000]
    assert data["function_metrics"]["tcp_roundtrip"]["throughput_bps"] == 100
    assert any(event["type"] == "scenario.metrics" for event in data["events"])
    assert {"kind": "scenario_metrics", "path": str(metrics_path.resolve())} in data["artifacts"]


def test_doctor_non_linux_fails(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: False)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "unsupported platform" in result.stdout


def test_doctor_linux_probe_ok(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: True)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "interceptor_active_probe: ok" in result.stdout


def test_doctor_linux_probe_ok_without_extension_lookup(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")

    def _fail_if_called() -> str:
        raise AssertionError("get_extension_path should not be called by doctor")

    monkeypatch.setattr(cli.native, "get_extension_path", _fail_if_called)
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: True)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "interceptor_active_probe: ok" in result.stdout


def test_report_command_generates_html(tmp_path) -> None:
    input_path = tmp_path / "run.json"
    input_path.write_text(
        json.dumps(
            {
                "run_id": "run-123",
                "status": "passed",
                "started_at": "2026-03-12T00:00:00.000Z",
                "ended_at": "2026-03-12T00:00:01.000Z",
                "duration_ms": 1000,
                "tool": {"name": "faultcore", "version": "2026.3.8", "command": ["pytest", "-q"]},
                "environment": {"os": "linux", "arch": "x86_64", "python_version": "3.13.2"},
                "interceptor": {"active": True, "path": "/tmp/libfaultcore.so"},
                "faultcore": {"seed": 0},
                "summary": {
                    "tests_total": 1,
                    "tests_passed": 1,
                    "tests_failed": 0,
                    "errors": 0,
                    "fault_events_total": 1,
                },
                "events": [
                    {
                        "ts": "2026-03-12T00:00:00.500Z",
                        "severity": "info",
                        "type": "fault",
                        "source": "policy",
                        "name": "latency",
                        "details": {"ms": 10},
                    }
                ],
                "scenarios": [],
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.html"

    result = runner.invoke(
        cli.app,
        ["report", "--input", str(input_path), "--output", str(output_path), "--max-events", "1", "--reverse-events"],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "faultcore report" in html
