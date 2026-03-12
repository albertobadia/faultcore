import html
import json
import os
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

UTC_TZ = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def utc_now_iso() -> str:
    return datetime.now(tz=UTC_TZ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def status_from_returncode(returncode: int) -> str:
    if returncode == 0:
        return "passed"
    if returncode > 0:
        return "failed"
    return "error"


def _git_value(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def build_run_record(
    *,
    command: list[str],
    returncode: int,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    interceptor_path: str | None,
    ld_preload_effective: str,
    interceptor_active: bool,
) -> dict[str, Any]:
    mode = "ld_preload" if interceptor_path else "none"
    try:
        tool_version = version("faultcore")
    except PackageNotFoundError:
        tool_version = ""
    ci_provider = ""
    for key in ("GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CI"):
        if os.environ.get(key):
            ci_provider = key.lower()
            break
    return {
        "run_id": str(uuid.uuid4()),
        "status": status_from_returncode(returncode),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": max(0, int(duration_ms)),
        "tool": {
            "name": "faultcore",
            "version": tool_version,
            "command": command,
        },
        "process": {
            "exit_code": returncode,
        },
        "environment": {
            "os": platform.system().lower(),
            "arch": platform.machine().lower(),
            "python_version": platform.python_version(),
            "ci": bool(ci_provider),
            "ci_provider": ci_provider,
            "git_commit": _git_value(["git", "rev-parse", "--short", "HEAD"]),
            "git_branch": _git_value(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        },
        "interceptor": {
            "mode": mode,
            "active": interceptor_active,
            "path": interceptor_path or "",
            "ld_preload_effective": ld_preload_effective,
        },
        "faultcore": {
            "seed": int(os.environ.get("FAULTCORE_SEED", "0")),
            "shm_name": os.environ.get("FAULTCORE_CONFIG_SHM", ""),
            "shm_open_mode": os.environ.get("FAULTCORE_SHM_OPEN_MODE", ""),
            "record_replay_mode": os.environ.get("FAULTCORE_RECORD_REPLAY_MODE", "off"),
            "policy_sources": [],
        },
        "summary": {
            "tests_total": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": 0 if returncode == 0 else 1,
            "fault_events_total": 0,
        },
        "scenarios": [],
        "events": [],
        "artifacts": [],
    }


def apply_event_view(
    events: list[dict[str, Any]],
    *,
    max_events: int,
    reverse_events: bool,
) -> tuple[list[dict[str, Any]], bool, int, str]:
    ordered = list(events)
    if reverse_events:
        ordered.reverse()
    original_count = len(ordered)
    truncated = False
    if max_events > 0 and len(ordered) > max_events:
        head_count = max_events // 2
        tail_count = max_events - head_count
        ordered = ordered[:head_count] + ordered[-tail_count:]
        truncated = True
    return ordered, truncated, original_count, "desc" if reverse_events else "asc"


def _safe(value: Any) -> str:
    return html.escape(str(value))


def _render_event_rows(events: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for event in events:
        details = event.get("details", {})
        details_str = json.dumps(details, ensure_ascii=True) if isinstance(details, dict) else str(details)
        rows.append(
            "<tr>"
            f"<td>{_safe(event.get('ts', ''))}</td>"
            f"<td>{_safe(event.get('severity', ''))}</td>"
            f"<td>{_safe(event.get('type', ''))}</td>"
            f"<td>{_safe(event.get('source', ''))}</td>"
            f"<td>{_safe(event.get('name', ''))}</td>"
            f"<td><code>{_safe(details_str)}</code></td>"
            "</tr>"
        )
    return "\n".join(rows) or "<tr><td colspan='6'>No events</td></tr>"


def render_report_html(
    run_data: dict[str, Any],
    *,
    max_events: int = 0,
    reverse_events: bool = False,
) -> str:
    events = run_data.get("events", [])
    if not isinstance(events, list):
        events = []

    viewed_events, truncated, original_count, order = apply_event_view(
        events,
        max_events=max_events,
        reverse_events=reverse_events,
    )
    run_data["events"] = viewed_events
    run_data["events_truncated"] = truncated
    run_data["events_total_original"] = original_count
    run_data["events_included"] = len(viewed_events)
    run_data["events_order"] = order

    status = run_data.get("status", "unknown")
    tool = run_data.get("tool", {})
    environment = run_data.get("environment", {})
    interceptor = run_data.get("interceptor", {})
    summary = run_data.get("summary", {})
    faultcore = run_data.get("faultcore", {})
    scenarios = run_data.get("scenarios", [])
    artifacts = run_data.get("artifacts", [])
    failures = [
        event
        for event in viewed_events
        if str(event.get("severity", "")).lower() == "error" or "fail" in str(event.get("type", "")).lower()
    ]
    run_data_json = json.dumps(run_data, ensure_ascii=True, indent=2)

    scenario_items = "".join(
        "<li>"
        f"{_safe(item.get('name', 'default'))}: {_safe(item.get('status', 'unknown'))}"
        f" ({_safe(item.get('duration_ms', 0))}ms)"
        "</li>"
        for item in scenarios
    ) or "<li>No scenarios</li>"
    artifact_items = "".join(
        "<li>"
        f"{_safe(item.get('kind', 'artifact'))}: <code>{_safe(item.get('path', ''))}</code>"
        "</li>"
        for item in artifacts
    ) or "<li>No artifacts</li>"
    failure_items = "".join(
        "<li>"
        f"{_safe(item.get('ts', ''))} {_safe(item.get('type', ''))}: {_safe(item.get('name', ''))}"
        "</li>"
        for item in failures
    ) or "<li>No failures/errors in current view</li>"

    duration_ms = _safe(run_data.get("duration_ms", 0))
    events_meta = (
        f"events_included={len(viewed_events)} | "
        f"events_total_original={original_count} | "
        f"events_order={order} | "
        f"events_truncated={str(truncated).lower()}"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>faultcore report - {_safe(run_data.get("run_id", ""))}</title>
  <style>
    :root {{
      --bg: #12110d;
      --panel: #1f1c14;
      --text: #f2e7c9;
      --muted: #b8aa88;
      --ok: #6bc46d;
      --bad: #de6f6f;
      --warn: #d2b35a;
      --info: #68a7db;
      --border: #463e2c;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      position: sticky;
      top: 0;
      background: rgba(18, 17, 13, 0.95);
      border-bottom: 1px solid var(--border);
      padding: 14px 20px;
    }}
    main {{ display: grid; grid-template-columns: 240px 1fr; gap: 16px; padding: 16px; }}
    nav {{
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 12px;
      height: max-content;
      position: sticky;
      top: 76px;
    }}
    nav a {{ display: block; color: var(--muted); text-decoration: none; margin: 6px 0; }}
    section {{ background: var(--panel); border: 1px solid var(--border); padding: 14px; margin-bottom: 14px; }}
    .status {{ font-weight: 700; color: { "var(--ok)" if status == "passed" else "var(--bad)" }; }}
    .muted {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border: 1px solid var(--border); padding: 6px; text-align: left; vertical-align: top; }}
    code {{ font-family: "JetBrains Mono", "Cascadia Mono", monospace; color: #f6ddb2; }}
    @media (max-width: 900px) {{
      main {{ grid-template-columns: 1fr; }}
      nav {{ position: static; }}
    }}
  </style>
</head>
<body>
  <header>
    <div><strong>faultcore report</strong></div>
    <div class="muted">
      run_id={_safe(run_data.get("run_id", ""))} |
      status=<span class="status">{_safe(status)}</span> |
      duration={duration_ms}ms
    </div>
  </header>
  <main>
    <nav aria-label="Table of contents">
      <a href="#overview">Overview</a>
      <a href="#context">Execution Context</a>
      <a href="#summary">Fault Summary</a>
      <a href="#scenarios">Scenarios</a>
      <a href="#timeline">Decisions Timeline</a>
      <a href="#failures">Failures/Errors</a>
      <a href="#artifacts">Artifacts</a>
    </nav>
    <div>
      <section id="overview">
        <h2>Overview</h2>
        <p>started_at={_safe(run_data.get("started_at", ""))}</p>
        <p>ended_at={_safe(run_data.get("ended_at", ""))}</p>
        <p>seed={_safe(faultcore.get("seed", 0))}</p>
      </section>
      <section id="context">
        <h2>Execution Context</h2>
        <p>command=<code>{_safe(" ".join(tool.get("command", [])))}</code></p>
        <p>os/arch={_safe(environment.get("os", ""))}/{_safe(environment.get("arch", ""))}</p>
        <p>python={_safe(environment.get("python_version", ""))}</p>
        <p>interceptor_active={_safe(interceptor.get("active", False))}</p>
        <p>interceptor_path=<code>{_safe(interceptor.get("path", ""))}</code></p>
      </section>
      <section id="summary">
        <h2>Fault Summary</h2>
        <p>tests_total={_safe(summary.get("tests_total", 0))}</p>
        <p>tests_passed={_safe(summary.get("tests_passed", 0))}</p>
        <p>tests_failed={_safe(summary.get("tests_failed", 0))}</p>
        <p>errors={_safe(summary.get("errors", 0))}</p>
        <p>fault_events_total={_safe(summary.get("fault_events_total", 0))}</p>
      </section>
      <section id="scenarios">
        <h2>Scenarios</h2>
        <ul>{scenario_items}</ul>
      </section>
      <section id="timeline">
        <h2>Decisions Timeline</h2>
        <p class="muted">{events_meta}</p>
        <table>
          <thead><tr><th>ts</th><th>severity</th><th>type</th><th>source</th><th>name</th><th>details</th></tr></thead>
          <tbody>
            {_render_event_rows(viewed_events)}
          </tbody>
        </table>
      </section>
      <section id="failures">
        <h2>Failures/Errors</h2>
        <ul>{failure_items}</ul>
      </section>
      <section id="artifacts">
        <h2>Artifacts</h2>
        <ul>{artifact_items}</ul>
      </section>
      <section>
        <h2>Embedded Data</h2>
        <script type="application/json" id="run-data">{html.escape(run_data_json)}</script>
      </section>
    </div>
  </main>
</body>
</html>
"""


def write_run_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_run_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_report_html(path: Path, html_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
