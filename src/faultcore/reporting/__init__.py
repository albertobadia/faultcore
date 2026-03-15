from . import core as _core
from .core import (
    apply_event_view,
    build_record_replay_series,
    build_record_replay_site_metrics,
    build_record_replay_sites,
    build_record_replay_timeline_events,
    is_pytest_command,
    load_record_replay_events,
    load_run_json,
    parse_pytest_failures,
    parse_pytest_summary,
    summarize_record_replay,
    utc_now_iso,
    write_report_html,
    write_run_json,
)
from .html_renderer import _normalize_chart_series, render_report_html

_git_value = _core._git_value
_RUN_RECORD_KEYS = (
    "command",
    "returncode",
    "started_at",
    "ended_at",
    "duration_ms",
    "interceptor_path",
    "ld_preload_effective",
    "interceptor_active",
    "summary_override",
    "run_json_path",
    "additional_events",
    "stdout_excerpt",
    "stderr_excerpt",
    "network_metrics",
    "network_series",
    "observed_sites",
    "site_metrics",
    "record_replay_path",
)


def build_run_record(
    *,
    command,
    returncode,
    started_at,
    ended_at,
    duration_ms,
    interceptor_path,
    ld_preload_effective,
    interceptor_active,
    summary_override=None,
    run_json_path=None,
    additional_events=None,
    stdout_excerpt="",
    stderr_excerpt="",
    network_metrics=None,
    network_series=None,
    observed_sites=None,
    site_metrics=None,
    record_replay_path="",
):
    _core._git_value = _git_value
    local_values = locals()
    run_record_kwargs = {key: local_values[key] for key in _RUN_RECORD_KEYS}
    return _core.build_run_record(**run_record_kwargs)


__all__ = [
    "_git_value",
    "apply_event_view",
    "build_record_replay_series",
    "build_record_replay_site_metrics",
    "build_record_replay_sites",
    "build_record_replay_timeline_events",
    "build_run_record",
    "is_pytest_command",
    "load_record_replay_events",
    "load_run_json",
    "parse_pytest_failures",
    "parse_pytest_summary",
    "render_report_html",
    "summarize_record_replay",
    "utc_now_iso",
    "write_report_html",
    "write_run_json",
    "_normalize_chart_series",
]
