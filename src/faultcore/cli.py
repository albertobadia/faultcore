import os
import platform
import subprocess
import sys
from pathlib import Path

import typer

from faultcore import native

app = typer.Typer(help="Faultcore command-line interface.")
RUN_COMMAND_ARG = typer.Argument(..., help="Command to execute. Use '--' before command args.")
RUN_STRICT_OPT = typer.Option(
    True,
    "--strict/--no-strict",
    help="Fail when interceptor is not active (Linux only).",
)
REPORT_INPUT_OPT = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True)
REPORT_OUTPUT_OPT = typer.Option(..., "--output", dir_okay=False)


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
) -> None:
    if not command:
        raise typer.BadParameter("Missing command to execute.")

    env = _base_env_for_run()
    if _is_linux():
        interceptor_path = native.get_interceptor_path()
        env["LD_PRELOAD"] = _compose_preload(interceptor_path)

        if strict and not _probe_interceptor_active(env):
            typer.echo("error: interceptor probe failed; strict mode requires active interceptor", err=True)
            raise typer.Exit(code=2)

    result = subprocess.run(command, env=env, check=False)
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
) -> None:
    _ = input_path
    _ = output_path
    typer.echo("error: report generation is not implemented yet", err=True)
    raise typer.Exit(code=2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
