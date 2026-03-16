import gzip
import json
import os
import platform
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

UTC_TZ = timezone(timedelta(0))
_PYTEST_SUMMARY_TIME_RE = re.compile(r"\bin [0-9]+(?:\.[0-9]+)?s\b")
_PYTEST_TOKEN_RE = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed|error|errors)\b", re.IGNORECASE)
_PYTEST_NO_TESTS_RE = re.compile(r"no tests ran", re.IGNORECASE)
_PYTEST_FAILED_LINE_RE = re.compile(r"^(FAILED|ERROR)\s+(.+)$")
_CI_PROVIDER_KEYS = ("GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CI")


def _errors_from_returncode(returncode: int) -> int:
    return 0 if returncode == 0 else 1


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


def is_pytest_command(command: list[str]) -> bool:
    if not command:
        return False
    command0 = Path(command[0]).name.lower()
    return command0 in {"pytest", "py.test"} or (
        len(command) >= 3 and command0.startswith("python") and command[1] == "-m" and command[2] == "pytest"
    )


def parse_pytest_summary(output_text: str, *, returncode: int) -> dict[str, int] | None:
    def is_summary_line(line: str) -> bool:
        return _PYTEST_NO_TESTS_RE.search(line) is not None or (
            _PYTEST_SUMMARY_TIME_RE.search(line) is not None and _PYTEST_TOKEN_RE.search(line) is not None
        )

    summary_line = next((line for line in reversed(output_text.splitlines()) if is_summary_line(line)), None)
    if summary_line is None:
        return None

    counts = {"passed": 0, "failed": 0, "errors": 0}
    for match in _PYTEST_TOKEN_RE.finditer(summary_line):
        count = int(match.group("count"))
        label = match.group("label").lower()
        if label in {"error", "errors"}:
            counts["errors"] += count
        elif label in counts:
            counts[label] += count

    passed = counts["passed"]
    failed = counts["failed"]
    errors = counts["errors"]

    if passed == 0 and failed == 0 and errors == 0 and _PYTEST_NO_TESTS_RE.search(summary_line):
        return {
            "tests_total": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": _errors_from_returncode(returncode),
        }

    derived_errors = errors
    if returncode != 0 and failed == 0 and errors == 0:
        derived_errors = 1
    return {
        "tests_total": passed + failed + errors,
        "tests_passed": passed,
        "tests_failed": failed,
        "errors": derived_errors,
    }


def parse_pytest_failures(output_text: str, *, max_items: int = 20) -> list[str]:
    failures: list[str] = []
    for raw_line in output_text.splitlines():
        line = raw_line.strip()
        if not (match := _PYTEST_FAILED_LINE_RE.match(line)):
            continue
        failures.append(match.group(2))
        if len(failures) >= max_items:
            break
    return failures


def _detect_ci_provider() -> str:
    return next((key.lower() for key in _CI_PROVIDER_KEYS if os.environ.get(key)), "")


def _default_summary(returncode: int) -> dict[str, int]:
    return {
        "tests_total": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "errors": _errors_from_returncode(returncode),
        "fault_events_total": 0,
    }


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    rank_index = max(0, min((len(sorted_values) * percentile + 99) // 100 - 1, len(sorted_values) - 1))
    return int(sorted_values[rank_index])


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_record_replay_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                events.append(item)
    except OSError:
        return []
    return events


def summarize_record_replay(events: list[dict[str, Any]]) -> dict[str, int]:
    decision_counts: dict[str, int] = {}
    delay_values: list[int] = []
    for event in events:
        decision = str(event.get("decision", ""))
        if not decision:
            continue
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        if decision == "delay_ns":
            delay_values.append(_to_int(event.get("value", 0)))
    fault_events_total = sum(decision_counts.values()) - decision_counts.get("continue", 0)
    return {
        "recorded_events_total": len(events),
        "fault_events_total": fault_events_total,
        "continue_count": decision_counts.get("continue", 0),
        "delay_count": decision_counts.get("delay_ns", 0),
        "drop_count": decision_counts.get("drop", 0),
        "timeout_count": decision_counts.get("timeout_ms", 0),
        "error_count": decision_counts.get("error", 0),
        "connection_error_count": decision_counts.get("connection_error_kind", 0),
        "reorder_count": decision_counts.get("stage_reorder", 0),
        "duplicate_count": decision_counts.get("duplicate", 0),
        "nxdomain_count": decision_counts.get("nxdomain", 0),
        "latency_p50_ns": _percentile(delay_values, 50),
        "latency_p95_ns": _percentile(delay_values, 95),
        "latency_p99_ns": _percentile(delay_values, 99),
    }


def extract_policy_sources(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    policy_names: set[str] = set()
    for event in events:
        policy_name = event.get("policy_name")
        if policy_name:
            policy_names.add(policy_name)
    return [{"kind": "record_replay", "name": name} for name in sorted(policy_names)]


def build_record_replay_series(events: list[dict[str, Any]], *, max_points: int = 400) -> dict[str, list[int]]:
    delay_series: list[int] = []
    cumulative_fault_events: list[int] = []
    faults_per_bucket: list[int] = []
    total_faults = 0
    limited_events = events[:max_points]
    bucket_size = max(1, len(limited_events) // 40)
    bucket_faults = 0
    bucket_seen = 0
    for item in limited_events:
        decision = str(item.get("decision", ""))
        value = item.get("value", 0)
        delay_value = _to_int(value) if decision == "delay_ns" else 0
        delay_series.append(delay_value)
        if decision and decision != "continue":
            total_faults += 1
            bucket_faults += 1
        cumulative_fault_events.append(total_faults)
        bucket_seen += 1
        if bucket_seen >= bucket_size:
            faults_per_bucket.append(bucket_faults)
            bucket_seen = 0
            bucket_faults = 0
    if bucket_seen > 0:
        faults_per_bucket.append(bucket_faults)
    return {
        "delay_ns": delay_series,
        "fault_events_cumulative": cumulative_fault_events,
        "fault_events_per_bucket": faults_per_bucket,
    }


def build_record_replay_sites(events: list[dict[str, Any]], *, max_items: int = 40) -> list[str]:
    sites: list[str] = []
    seen: set[str] = set()
    for item in events:
        site = str(item.get("site", "")).strip()
        if not site or site in seen:
            continue
        seen.add(site)
        sites.append(site)
        if len(sites) >= max_items:
            break
    return sites


def build_record_replay_site_metrics(
    events: list[dict[str, Any]],
    *,
    max_sites: int = 80,
    max_series_points: int = 120,
    bucket_size_events: int = 500,
) -> dict[str, dict[str, Any]]:
    by_site: dict[str, dict[str, Any]] = {}
    for item in events:
        site = str(item.get("site", "")).strip()
        decision = str(item.get("decision", "")).strip()
        if not site or not decision:
            continue
        if site not in by_site:
            if len(by_site) >= max_sites:
                continue
            by_site[site] = {
                "total_events": 0,
                "fault_events": 0,
                "decision_counts": {},
                "delay_values_ns": [],
                "fault_flag_series": [],
                "continue_flag_series": [],
                "events_per_bucket": [],
                "fault_events_per_bucket": [],
                "continue_events_per_bucket": [],
                "_bucket_seen": 0,
                "_bucket_fault": 0,
                "_bucket_continue": 0,
            }
        site_data = by_site[site]
        site_data["total_events"] += 1
        is_fault = decision != "continue"
        if is_fault:
            site_data["fault_events"] += 1
        if len(site_data["fault_flag_series"]) < max_series_points:
            site_data["fault_flag_series"].append(1 if is_fault else 0)
        if len(site_data["continue_flag_series"]) < max_series_points:
            site_data["continue_flag_series"].append(0 if is_fault else 1)
        counts = site_data["decision_counts"]
        counts[decision] = counts.get(decision, 0) + 1
        if decision == "delay_ns":
            delay_value = _to_int(item.get("value", 0))
            delays = site_data["delay_values_ns"]
            if len(delays) < max_series_points:
                delays.append(delay_value)
        site_data["_bucket_seen"] += 1
        if is_fault:
            site_data["_bucket_fault"] += 1
        else:
            site_data["_bucket_continue"] += 1
        if site_data["_bucket_seen"] >= bucket_size_events:
            site_data["events_per_bucket"].append(site_data["_bucket_seen"])
            site_data["fault_events_per_bucket"].append(site_data["_bucket_fault"])
            site_data["continue_events_per_bucket"].append(site_data["_bucket_continue"])
            site_data["_bucket_seen"] = 0
            site_data["_bucket_fault"] = 0
            site_data["_bucket_continue"] = 0

    summarized: dict[str, dict[str, Any]] = {}
    for site, site_data in by_site.items():
        delay_values = list(site_data.get("delay_values_ns", []))
        total_events = int(site_data.get("total_events", 0))
        fault_events = int(site_data.get("fault_events", 0))
        decision_counts = dict(site_data.get("decision_counts", {}))
        if int(site_data.get("_bucket_seen", 0)) > 0:
            site_data["events_per_bucket"].append(int(site_data.get("_bucket_seen", 0)))
            site_data["fault_events_per_bucket"].append(int(site_data.get("_bucket_fault", 0)))
            site_data["continue_events_per_bucket"].append(int(site_data.get("_bucket_continue", 0)))
        fault_rate_pct = round((fault_events * 100.0 / total_events), 2) if total_events > 0 else 0.0
        delay_avg_ns = int(sum(delay_values) / len(delay_values)) if delay_values else 0
        summarized[site] = {
            "total_events": total_events,
            "fault_events": fault_events,
            "continue_events": int(decision_counts.get("continue", 0)),
            "fault_rate_pct": fault_rate_pct,
            "decision_counts": decision_counts,
            "delay_avg_ns": delay_avg_ns,
            "latency_p50_ns": _percentile(delay_values, 50),
            "latency_p95_ns": _percentile(delay_values, 95),
            "latency_p99_ns": _percentile(delay_values, 99),
            "delay_series_ns": delay_values,
            "fault_flag_series": list(site_data.get("fault_flag_series", [])),
            "continue_flag_series": list(site_data.get("continue_flag_series", [])),
            "events_per_bucket": list(site_data.get("events_per_bucket", [])),
            "fault_events_per_bucket": list(site_data.get("fault_events_per_bucket", [])),
            "continue_events_per_bucket": list(site_data.get("continue_events_per_bucket", [])),
            "bucket_size_events": int(bucket_size_events),
            "inferred_config": {
                "delay_active": decision_counts.get("delay_ns", 0) > 0,
                "drop_active": decision_counts.get("drop", 0) > 0,
                "timeout_active": decision_counts.get("timeout_ms", 0) > 0,
                "duplicate_active": decision_counts.get("duplicate", 0) > 0,
                "reorder_active": decision_counts.get("stage_reorder", 0) > 0,
                "connection_error_active": decision_counts.get("connection_error_kind", 0) > 0,
                "nxdomain_active": decision_counts.get("nxdomain", 0) > 0,
            },
        }
    return summarized


def build_record_replay_timeline_events(
    events: list[dict[str, Any]], *, ts: str, max_items: int = 300
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in events[:max_items]:
        decision = str(item.get("decision", ""))
        site = str(item.get("site", ""))
        value = item.get("value", 0)
        severity = "error" if decision == "error" else ("info" if decision == "continue" else "warning")
        out.append(
            {
                "ts": ts,
                "severity": severity,
                "type": f"network.{decision or 'unknown'}",
                "source": "record_replay",
                "name": site or "unknown_site",
                "details": {"value": value},
            }
        )
    return out


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
    summary_override: dict[str, int] | None = None,
    run_json_path: str | None = None,
    additional_events: list[dict[str, Any]] | None = None,
    stdout_excerpt: str = "",
    stderr_excerpt: str = "",
    network_metrics: dict[str, Any] | None = None,
    network_series: dict[str, list[int]] | None = None,
    observed_sites: list[str] | None = None,
    site_metrics: dict[str, dict[str, Any]] | None = None,
    record_replay_path: str = "",
    policy_sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    mode = "ld_preload" if interceptor_path else "none"
    status = status_from_returncode(returncode)
    run_duration_ms = max(0, int(duration_ms))
    try:
        tool_version = version("faultcore")
    except PackageNotFoundError:
        tool_version = ""
    ci_provider = _detect_ci_provider()
    summary = _default_summary(returncode)
    if summary_override:
        summary.update(summary_override)

    scenarios = [
        {
            "name": "command",
            "status": status,
            "duration_ms": run_duration_ms,
        }
    ]
    events = [
        {
            "ts": ended_at,
            "severity": "info" if returncode == 0 else "error",
            "type": "run.completed",
            "source": "faultcore.cli",
            "name": "command_exit",
            "details": {
                "exit_code": returncode,
                "interceptor_active": interceptor_active,
            },
        }
    ]
    if additional_events:
        events.extend(additional_events)
    artifacts: list[dict[str, str]] = []
    if run_json_path:
        artifacts.append({"kind": "run_json", "path": run_json_path})
    if record_replay_path:
        artifacts.append({"kind": "record_replay", "path": record_replay_path})

    return {
        "run_id": str(uuid.uuid4()),
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": run_duration_ms,
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
            "record_replay_path": record_replay_path,
            "policy_sources": policy_sources or [],
        },
        "summary": summary,
        "scenarios": scenarios,
        "events": events,
        "artifacts": artifacts,
        "logs": {
            "stdout_tail": stdout_excerpt,
            "stderr_tail": stderr_excerpt,
        },
        "network_metrics": network_metrics or {},
        "network_series": network_series or {},
        "observed_sites": observed_sites or [],
        "site_metrics": site_metrics or {},
    }


def apply_event_view(
    events: list[dict[str, Any]],
    *,
    max_events: int,
    reverse_events: bool,
) -> tuple[list[dict[str, Any]], bool, int, str]:
    ordered = list(reversed(events)) if reverse_events else list(events)
    order = "desc" if reverse_events else "asc"
    original_count = len(ordered)
    if max_events <= 0 or original_count <= max_events:
        return ordered, False, original_count, order

    head_count = max_events // 2
    tail_count = max_events - head_count
    viewed = ordered[:head_count] + ordered[-tail_count:]
    return viewed, True, original_count, order


def write_run_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_run_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_report_html(path: Path, html_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
