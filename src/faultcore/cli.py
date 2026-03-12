import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import typer

from faultcore import native
from faultcore.reporting import (
    build_run_record,
    load_run_json,
    render_report_html,
    utc_now_iso,
    write_report_html,
    write_run_json,
)

app = typer.Typer(help="Faultcore command-line interface.")
RUN_COMMAND_ARG = typer.Argument(..., help="Command to execute. Use '--' before command args.")
RUN_STRICT_OPT = typer.Option(
    True,
    "--strict/--no-strict",
    help="Fail when interceptor is not active (Linux only).",
)
REPORT_INPUT_OPT = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True)
REPORT_OUTPUT_OPT = typer.Option(..., "--output", dir_okay=False)
RUN_JSON_OPT = typer.Option(
    None,
    "--run-json",
    help="Optional output path for run metadata JSON.",
    dir_okay=False,
)
REPORT_MAX_EVENTS_OPT = typer.Option(0, "--max-events", min=0, help="Maximum events to include (0 = all).")
REPORT_REVERSE_EVENTS_OPT = typer.Option(
    False,
    "--reverse-events",
    help="Render events in reverse chronological order.",
)


def _is_linux() -> bool:
    return platform.system() == "Linux"


def _compose_preload(interceptor_path: str) -> str:
    current = os.environ.get("LD_PRELOAD", "").strip()
    return f"{interceptor_path} {current}".strip() if current else interceptor_path


def _probe_interceptor_active(env: dict[str, str]) -> bool:
    probe_code = (
        "import ctypes,sys\n"
        "ok=False\n"
        "try:\n"
        "    fn=getattr(ctypes.CDLL(None), 'faultcore_interceptor_is_active')\n"
        "    fn.restype=ctypes.c_bool\n"
        "    ok=bool(fn())\n"
        "except Exception:\n"
        "    ok=False\n"
        "raise SystemExit(0 if ok else 1)\n"
    )
    result = subprocess.run([sys.executable, "-c", probe_code], env=env, check=False)
    return result.returncode == 0


def _base_env_for_run(*, shm_mode: str = "creator") -> dict[str, str]:
    env = dict(os.environ)
    env["FAULTCORE_SHM_OPEN_MODE"] = shm_mode
    env.setdefault("FAULTCORE_ENABLED", "1")
    return env


@app.command("run")
def run_command(
    command: list[str] = RUN_COMMAND_ARG,
    strict: bool = RUN_STRICT_OPT,
    run_json: Path | None = RUN_JSON_OPT,
) -> None:
    if not command:
        raise typer.BadParameter("Missing command to execute.")

    started_at = utc_now_iso()
    started_perf = time.perf_counter()
    env = _base_env_for_run()
    interceptor_path: str | None = None
    ld_preload_effective = env.get("LD_PRELOAD", "")
    interceptor_active = False

    if _is_linux():
        interceptor_path = native.get_interceptor_path()
        env["LD_PRELOAD"] = _compose_preload(interceptor_path)
        ld_preload_effective = env["LD_PRELOAD"]
        interceptor_active = _probe_interceptor_active(env)

        if strict and not interceptor_active:
            ended_at = utc_now_iso()
            duration_ms = int((time.perf_counter() - started_perf) * 1000)
            if run_json is not None:
                write_run_json(
                    run_json,
                    build_run_record(
                        command=command,
                        returncode=2,
                        started_at=started_at,
                        ended_at=ended_at,
                        duration_ms=duration_ms,
                        interceptor_path=interceptor_path,
                        ld_preload_effective=ld_preload_effective,
                        interceptor_active=False,
                    ),
                )
            typer.echo("error: interceptor probe failed; strict mode requires active interceptor", err=True)
            raise typer.Exit(code=2)

    result = subprocess.run(command, env=env, check=False)
    ended_at = utc_now_iso()
    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    if run_json is not None:
        write_run_json(
            run_json,
            build_run_record(
                command=command,
                returncode=result.returncode,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                interceptor_path=interceptor_path,
                ld_preload_effective=ld_preload_effective,
                interceptor_active=interceptor_active,
            ),
        )
    raise typer.Exit(code=result.returncode)


@app.command("doctor")
def doctor_command() -> None:
    typer.echo("faultcore doctor")
    typer.echo(f"platform: {platform.system().lower()} {platform.machine().lower()}")

    if not _is_linux():
        typer.echo("interceptor: unsupported platform (Linux required)")
        raise typer.Exit(code=1)

    interceptor_path = Path(native.get_interceptor_path())
    extension_path = Path(native.get_extension_path())
    typer.echo(f"interceptor_path: {interceptor_path}")
    typer.echo(f"extension_path: {extension_path}")

    env = _base_env_for_run(shm_mode="consumer")
    env["LD_PRELOAD"] = _compose_preload(str(interceptor_path))
    active = _probe_interceptor_active(env)
    typer.echo(f"interceptor_active_probe: {'ok' if active else 'failed'}")
    raise typer.Exit(code=0 if active else 1)


@app.command("report")
def report_command(
    input_path: Path = REPORT_INPUT_OPT,
    output_path: Path = REPORT_OUTPUT_OPT,
    max_events: int = REPORT_MAX_EVENTS_OPT,
    reverse_events: bool = REPORT_REVERSE_EVENTS_OPT,
) -> None:
    run_data = load_run_json(input_path)
    html_text = render_report_html(run_data, max_events=max_events, reverse_events=reverse_events)
    write_report_html(output_path, html_text)
    typer.echo(f"report written: {output_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
