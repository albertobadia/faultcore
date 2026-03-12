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


def test_report_command_stub(tmp_path):
    input_path = tmp_path / "run.json"
    input_path.write_text("{}", encoding="utf-8")
    output_path = tmp_path / "report.html"

    result = runner.invoke(cli.app, ["report", "--input", str(input_path), "--output", str(output_path)])
    assert result.exit_code == 2
    assert "not implemented yet" in result.stderr
