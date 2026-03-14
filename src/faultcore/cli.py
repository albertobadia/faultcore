import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import typer

from faultcore import native
from faultcore.reporting import (
    build_record_replay_series,
    build_record_replay_site_metrics,
    build_record_replay_sites,
    build_record_replay_timeline_events,
    build_run_record,
    is_pytest_command,
    load_record_replay_events,
    load_run_json,
    parse_pytest_failures,
    parse_pytest_summary,
    render_report_html,
    summarize_record_replay,
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

_INTERCEPTOR_PROBE_CODE = """import ctypes
import sys
ok = False
try:
    fn = getattr(ctypes.CDLL(None), 'faultcore_interceptor_is_active')
    fn.restype = ctypes.c_bool
    ok = bool(fn())
except Exception:
    ok = False
raise SystemExit(0 if ok else 1)
"""


def _is_linux() -> bool:
    return platform.system() == "Linux"


def _compose_preload(interceptor_path: str) -> str:
    current = os.environ.get("LD_PRELOAD", "").strip()
    return f"{interceptor_path} {current}".strip() if current else interceptor_path


def _probe_interceptor_active(env: dict[str, str]) -> bool:
    result = subprocess.run([sys.executable, "-c", _INTERCEPTOR_PROBE_CODE], env=env, check=False)
    return result.returncode == 0


def _base_env_for_run(*, shm_mode: str = "creator") -> dict[str, str]:
    env = dict(os.environ)
    env["FAULTCORE_SHM_OPEN_MODE"] = shm_mode
    env.setdefault("FAULTCORE_ENABLED", "1")
    return env


def _extract_scenario_metrics_path(command: list[str], env: dict[str, str]) -> Path | None:
    explicit = env.get("FAULTCORE_SCENARIO_METRICS_PATH", "").strip()
    if explicit:
        return Path(explicit)
    for idx, token in enumerate(command):
        if token == "--metrics-out" and idx + 1 < len(command):
            return Path(command[idx + 1])
        key, sep, value = token.partition("=")
        if key == "--metrics-out" and sep and value:
            return Path(value)
    return None


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            return int(float(value))
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _normalize_series_entry(key: str, value: object) -> int:
    if key.endswith("_ms"):
        return int(round(_coerce_float(value, default=0.0) * 1_000_000))
    return _coerce_int(value)


def _load_scenario_metrics(path: Path | None) -> tuple[Path | None, dict[str, object]]:
    if path is None:
        return None, {}
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return resolved, {}
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return resolved, {}
    if not isinstance(raw, dict):
        return resolved, {}
    return resolved, raw


def _merge_scenario_metrics_into_run_record(
    record: dict[str, object],
    *,
    scenario_metrics: dict[str, object],
    ended_at: str,
    scenario_metrics_path: Path | None,
) -> None:
    if not scenario_metrics:
        return

    latency_map = _as_dict(scenario_metrics.get("latency_ms"))
    jitter_map = _as_dict(scenario_metrics.get("jitter_ms"))
    bytes_map = _as_dict(scenario_metrics.get("bytes"))
    throughput_map = _as_dict(scenario_metrics.get("throughput_bps"))
    scenario_map = _as_dict(scenario_metrics.get("scenario"))
    functions_map = _as_dict(scenario_metrics.get("functions"))
    series_map = _as_dict(scenario_metrics.get("series"))

    existing_network_metrics_raw = record.get("network_metrics")
    network_metrics = dict(existing_network_metrics_raw) if isinstance(existing_network_metrics_raw, dict) else {}
    network_metrics.update(
        {
            "scenario_iterations": _coerce_int(scenario_map.get("iterations")),
            "scenario_duration_ms": _coerce_int(scenario_map.get("duration_ms")),
            "tcp_latency_avg_ms": _coerce_float(latency_map.get("tcp_avg")),
            "udp_latency_avg_ms": _coerce_float(latency_map.get("udp_avg")),
            "http_latency_avg_ms": _coerce_float(latency_map.get("http_avg")),
            "tcp_jitter_ms": _coerce_float(jitter_map.get("tcp")),
            "udp_jitter_ms": _coerce_float(jitter_map.get("udp")),
            "http_jitter_ms": _coerce_float(jitter_map.get("http")),
            "tcp_throughput_bps": _coerce_int(throughput_map.get("tcp")),
            "udp_throughput_bps": _coerce_int(throughput_map.get("udp")),
            "http_throughput_bps": _coerce_int(throughput_map.get("http")),
            "total_bytes": _coerce_int(bytes_map.get("total")),
            "total_throughput_bps": _coerce_int(throughput_map.get("total")),
        }
    )
    record["network_metrics"] = network_metrics

    existing_series_raw = record.get("network_series")
    merged_series = dict(existing_series_raw) if isinstance(existing_series_raw, dict) else {}
    for key, values in series_map.items():
        if not (isinstance(key, str) and isinstance(values, list)):
            continue
        normalized = [_normalize_series_entry(key, value) for value in values]
        merged_series[key] = normalized
    record["network_series"] = merged_series

    if functions_map:
        record["function_metrics"] = functions_map

    events_raw = record.get("events")
    events = list(events_raw) if isinstance(events_raw, list) else []
    events.append(
        {
            "ts": ended_at,
            "severity": "info",
            "type": "scenario.metrics",
            "source": "faultcore.cli",
            "name": "multi_protocol_summary",
            "details": {
                "total_throughput_bps": _coerce_int(throughput_map.get("total")),
                "tcp_latency_avg_ms": _coerce_float(latency_map.get("tcp_avg")),
                "udp_latency_avg_ms": _coerce_float(latency_map.get("udp_avg")),
                "http_latency_avg_ms": _coerce_float(latency_map.get("http_avg")),
            },
        }
    )
    record["events"] = events

    if scenario_metrics_path is not None:
        artifacts_raw = record.get("artifacts")
        artifacts = list(artifacts_raw) if isinstance(artifacts_raw, list) else []
        metrics_artifact = {"kind": "scenario_metrics", "path": str(scenario_metrics_path)}
        if metrics_artifact not in artifacts:
            artifacts.append(metrics_artifact)
        record["artifacts"] = artifacts


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
    record_replay_path = ""

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
                        run_json_path=str(run_json),
                    ),
                )
            typer.echo("error: interceptor probe failed; strict mode requires active interceptor", err=True)
            raise typer.Exit(code=2)

    if run_json is not None:
        rr_mode = env.get("FAULTCORE_RECORD_REPLAY_MODE", "").strip().lower()
        if rr_mode in {"", "off"}:
            env["FAULTCORE_RECORD_REPLAY_MODE"] = "record"
            rr_mode = "record"
        if rr_mode in {"record", "replay"}:
            explicit_path = env.get("FAULTCORE_RECORD_REPLAY_PATH", "").strip()
            if explicit_path:
                record_replay_path = explicit_path
            else:
                record_replay_path = str(run_json.with_suffix(".rr.jsonl.gz"))
                env["FAULTCORE_RECORD_REPLAY_PATH"] = record_replay_path

    capture_output = is_pytest_command(command)
    scenario_metrics_path = _extract_scenario_metrics_path(command, env) if run_json is not None else None
    result = subprocess.run(command, env=env, check=False, capture_output=capture_output, text=capture_output)
    stdout_text = ""
    stderr_text = ""
    if capture_output:
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
        if stdout_text:
            typer.echo(stdout_text, nl=False)
        if stderr_text:
            typer.echo(stderr_text, err=True, nl=False)
    combined_output = f"{stdout_text}\n{stderr_text}".strip() if capture_output else ""

    ended_at = utc_now_iso()
    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    summary_override = parse_pytest_summary(combined_output, returncode=result.returncode) if capture_output else None
    additional_events: list[dict[str, object]] = []
    if capture_output and summary_override is not None:
        additional_events.append(
            {
                "ts": ended_at,
                "severity": "info" if result.returncode == 0 else "warning",
                "type": "pytest.summary",
                "source": "faultcore.cli",
                "name": "pytest_summary",
                "details": summary_override,
            }
        )
        for failure_name in parse_pytest_failures(combined_output):
            additional_events.append(
                {
                    "ts": ended_at,
                    "severity": "error",
                    "type": "pytest.failure",
                    "source": "pytest",
                    "name": failure_name,
                    "details": {},
                }
            )
    network_metrics: dict[str, int] | None = None
    network_series: dict[str, list[int]] | None = None
    observed_sites: list[str] | None = None
    site_metrics: dict[str, dict[str, object]] | None = None
    if record_replay_path:
        rr_events = load_record_replay_events(Path(record_replay_path))
        network_metrics = summarize_record_replay(rr_events)
        network_series = build_record_replay_series(rr_events)
        observed_sites = build_record_replay_sites(rr_events)
        site_metrics = build_record_replay_site_metrics(rr_events)
        additional_events.extend(build_record_replay_timeline_events(rr_events, ts=ended_at))
        if summary_override is None:
            summary_override = {}
        summary_override["fault_events_total"] = network_metrics.get("fault_events_total", 0)

    if run_json is not None:
        run_record = build_run_record(
            command=command,
            returncode=result.returncode,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            interceptor_path=interceptor_path,
            ld_preload_effective=ld_preload_effective,
            interceptor_active=interceptor_active,
            summary_override=summary_override,
            run_json_path=str(run_json),
            additional_events=additional_events,
            stdout_excerpt=stdout_text[-4000:],
            stderr_excerpt=stderr_text[-4000:],
            network_metrics=network_metrics,
            network_series=network_series,
            observed_sites=observed_sites,
            site_metrics=site_metrics,
            record_replay_path=record_replay_path,
        )
        resolved_scenario_metrics_path, scenario_metrics = _load_scenario_metrics(scenario_metrics_path)
        _merge_scenario_metrics_into_run_record(
            run_record,
            scenario_metrics=scenario_metrics,
            ended_at=ended_at,
            scenario_metrics_path=resolved_scenario_metrics_path,
        )
        write_run_json(run_json, run_record)
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
