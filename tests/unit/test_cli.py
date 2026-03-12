import json
from types import SimpleNamespace

from typer.testing import CliRunner

from faultcore import cli

runner = CliRunner()


def test_compose_preload_without_existing_value(monkeypatch):
    monkeypatch.delenv("LD_PRELOAD", raising=False)
    assert cli._compose_preload("/faultcore/libfaultcore_interceptor.so") == "/faultcore/libfaultcore_interceptor.so"


def test_compose_preload_appends_existing_value(monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/already.so")
    assert cli._compose_preload("/faultcore/libfaultcore_interceptor.so") == (
        "/faultcore/libfaultcore_interceptor.so /already.so"
    )


def test_run_command_linux_strict_fails_when_probe_fails(monkeypatch):
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


def test_run_command_linux_strict_success_executes_with_ld_preload(monkeypatch):
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: True)
    monkeypatch.setenv("LD_PRELOAD", "/existing.so")

    calls = []

    def fake_run(args, *, env, check):
        calls.append((args, env, check))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["run", "--", "python", "-V"])
    assert result.exit_code == 7
    assert len(calls) == 1
    args, env, check = calls[0]
    assert args == ["python", "-V"]
    assert check is False
    assert env["LD_PRELOAD"] == "/faultcore/interceptor.so /existing.so"
    assert env["FAULTCORE_SHM_OPEN_MODE"] == "creator"


def test_run_command_writes_run_json(tmp_path, monkeypatch):
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

    def fake_run(args, *, env, check):
        _ = env
        _ = check
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


def test_run_command_strict_failure_writes_run_json(tmp_path, monkeypatch):
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


def test_doctor_non_linux_fails(monkeypatch):
    monkeypatch.setattr(cli, "_is_linux", lambda: False)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "unsupported platform" in result.stdout


def test_doctor_linux_probe_ok(monkeypatch):
    monkeypatch.setattr(cli, "_is_linux", lambda: True)
    monkeypatch.setattr(cli.native, "get_interceptor_path", lambda: "/faultcore/interceptor.so")
    monkeypatch.setattr(cli.native, "get_extension_path", lambda: "/faultcore/_faultcore.abi3.so")
    monkeypatch.setattr(cli, "_probe_interceptor_active", lambda _env: True)

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "interceptor_active_probe: ok" in result.stdout


def test_report_command_generates_html(tmp_path):
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
    assert "events_order=desc" in html
