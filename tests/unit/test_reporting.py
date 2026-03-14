from faultcore import reporting


def test_build_run_record_sets_required_fields(monkeypatch):
    monkeypatch.setattr(reporting, "_git_value", lambda _args: "git-value")
    monkeypatch.setenv("FAULTCORE_SEED", "123")
    monkeypatch.setenv("FAULTCORE_CONFIG_SHM", "/faultcore_demo")
    monkeypatch.setenv("FAULTCORE_SHM_OPEN_MODE", "creator")
    monkeypatch.setenv("FAULTCORE_RECORD_REPLAY_MODE", "record")
    monkeypatch.setenv("CI", "1")

    record = reporting.build_run_record(
        command=["pytest", "-q"],
        returncode=0,
        started_at="2026-03-12T00:00:00.000Z",
        ended_at="2026-03-12T00:00:01.000Z",
        duration_ms=1000,
        interceptor_path="/tmp/libfaultcore_interceptor.so",
        ld_preload_effective="/tmp/libfaultcore_interceptor.so",
        interceptor_active=True,
    )

    assert record["status"] == "passed"
    assert record["tool"]["command"] == ["pytest", "-q"]
    assert record["interceptor"]["mode"] == "ld_preload"
    assert record["faultcore"]["seed"] == 123
    assert record["faultcore"]["shm_name"] == "/faultcore_demo"
    assert len(record["events"]) == 1
    assert record["events"][0]["type"] == "run.completed"
    assert len(record["scenarios"]) == 1
    assert record["scenarios"][0]["name"] == "command"
    assert record["summary"]["errors"] == 0


def test_build_run_record_applies_summary_override(monkeypatch):
    monkeypatch.setattr(reporting, "_git_value", lambda _args: "git-value")

    record = reporting.build_run_record(
        command=["pytest", "-q"],
        returncode=1,
        started_at="2026-03-12T00:00:00.000Z",
        ended_at="2026-03-12T00:00:01.000Z",
        duration_ms=1000,
        interceptor_path="/tmp/libfaultcore_interceptor.so",
        ld_preload_effective="/tmp/libfaultcore_interceptor.so",
        interceptor_active=True,
        summary_override={"tests_total": 4, "tests_passed": 2, "tests_failed": 1, "errors": 1},
        run_json_path="artifacts/run.json",
    )

    assert record["summary"]["tests_total"] == 4
    assert record["summary"]["tests_passed"] == 2
    assert record["summary"]["tests_failed"] == 1
    assert record["summary"]["errors"] == 1
    assert record["artifacts"] == [{"kind": "run_json", "path": "artifacts/run.json"}]


def test_parse_pytest_summary_parses_counts():
    text = "=================== 3 passed, 1 failed, 2 errors in 0.42s ==================="
    parsed = reporting.parse_pytest_summary(text, returncode=1)

    assert parsed == {
        "tests_total": 6,
        "tests_passed": 3,
        "tests_failed": 1,
        "errors": 2,
    }


def test_parse_pytest_summary_parses_quiet_output_line():
    text = "208 passed in 0.39s"
    parsed = reporting.parse_pytest_summary(text, returncode=0)

    assert parsed == {
        "tests_total": 208,
        "tests_passed": 208,
        "tests_failed": 0,
        "errors": 0,
    }


def test_parse_pytest_summary_handles_no_tests():
    text = "============================ no tests ran in 0.01s ============================"
    parsed = reporting.parse_pytest_summary(text, returncode=0)

    assert parsed == {
        "tests_total": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "errors": 0,
    }


def test_parse_pytest_failures_extracts_failed_and_error_lines():
    text = "\n".join(
        [
            "FAILED tests/unit/test_alpha.py::test_a - AssertionError: boom",
            "ERROR tests/unit/test_beta.py::test_b - RuntimeError: bad",
        ]
    )
    parsed = reporting.parse_pytest_failures(text)

    assert parsed == [
        "tests/unit/test_alpha.py::test_a - AssertionError: boom",
        "tests/unit/test_beta.py::test_b - RuntimeError: bad",
    ]


def test_summarize_record_replay_counts_and_percentiles():
    metrics = reporting.summarize_record_replay(
        [
            {"site": "a", "decision": "continue", "value": 0},
            {"site": "b", "decision": "delay_ns", "value": 1_000_000},
            {"site": "c", "decision": "delay_ns", "value": 10_000_000},
            {"site": "d", "decision": "drop", "value": 0},
        ]
    )

    assert metrics["recorded_events_total"] == 4
    assert metrics["fault_events_total"] == 3
    assert metrics["continue_count"] == 1
    assert metrics["delay_count"] == 2
    assert metrics["drop_count"] == 1
    assert metrics["latency_p50_ns"] >= 1_000_000


def test_build_record_replay_timeline_events_maps_decisions():
    events = reporting.build_record_replay_timeline_events(
        [{"site": "stream_uplink_pre", "decision": "delay_ns", "value": 5_000_000}],
        ts="2026-03-12T00:00:01.000Z",
    )
    assert len(events) == 1
    assert events[0]["type"] == "network.delay_ns"
    assert events[0]["name"] == "stream_uplink_pre"


def test_build_record_replay_series_and_sites():
    raw = [
        {"site": "connect_pre", "decision": "continue", "value": 0},
        {"site": "stream_uplink_pre", "decision": "delay_ns", "value": 5_000_000},
        {"site": "stream_uplink_pre", "decision": "drop", "value": 0},
    ]
    series = reporting.build_record_replay_series(raw)
    sites = reporting.build_record_replay_sites(raw)

    assert len(series["delay_ns"]) == 3
    assert series["fault_events_cumulative"][-1] == 2
    assert sum(series["fault_events_per_bucket"]) == 2
    assert sites == ["connect_pre", "stream_uplink_pre"]


def test_build_record_replay_site_metrics_groups_by_site():
    raw = [
        {"site": "connect_pre", "decision": "continue", "value": 0},
        {"site": "stream_uplink_pre", "decision": "delay_ns", "value": 5_000_000},
        {"site": "stream_uplink_pre", "decision": "drop", "value": 0},
    ]
    site_metrics = reporting.build_record_replay_site_metrics(raw)

    assert "stream_uplink_pre" in site_metrics
    assert site_metrics["stream_uplink_pre"]["fault_events"] == 2
    assert site_metrics["stream_uplink_pre"]["inferred_config"]["delay_active"] is True
    assert site_metrics["stream_uplink_pre"]["inferred_config"]["drop_active"] is True


def test_is_pytest_command_detects_path_and_python_module_forms():
    assert reporting.is_pytest_command(["pytest", "-q"]) is True
    assert reporting.is_pytest_command([".venv/bin/pytest", "-q"]) is True
    assert reporting.is_pytest_command(["/usr/bin/python3", "-m", "pytest", "-q"]) is True
    assert reporting.is_pytest_command(["python3.13", "-m", "pytest", "-q"]) is True
    assert reporting.is_pytest_command(["sh", "tests.sh"]) is False


def test_apply_event_view_truncates_head_tail_and_reverses():
    events = [{"id": i} for i in range(1, 7)]
    viewed, truncated, original_count, order = reporting.apply_event_view(events, max_events=4, reverse_events=True)

    assert truncated is True
    assert original_count == 6
    assert order == "desc"
    assert [item["id"] for item in viewed] == [6, 5, 2, 1]


def test_render_report_html_embeds_event_metadata():
    html_text = reporting.render_report_html(
        {
            "run_id": "demo",
            "status": "passed",
            "duration_ms": 10,
            "tool": {"command": ["pytest", "-q"]},
            "environment": {"os": "linux", "arch": "x86_64", "python_version": "3.13.2"},
            "interceptor": {"active": True, "path": "/tmp/libfaultcore.so"},
            "faultcore": {"seed": 0},
            "summary": {"tests_total": 1, "tests_passed": 1, "tests_failed": 0, "errors": 0, "fault_events_total": 2},
            "events": [
                {"ts": "1", "severity": "info", "type": "a", "source": "x", "name": "e1", "details": {}},
                {"ts": "2", "severity": "error", "type": "b", "source": "x", "name": "e2", "details": {}},
            ],
            "scenarios": [],
            "artifacts": [],
            "logs": {"stdout_tail": "hello", "stderr_tail": ""},
            "network_metrics": {"recorded_events_total": 2, "delay_count": 1},
            "network_series": {
                "delay_ns": [0, 10, 5],
                "fault_events_cumulative": [0, 1, 1],
                "fault_events_per_bucket": [0, 1, 1],
            },
            "observed_sites": ["connect_pre", "stream_uplink_pre"],
            "site_metrics": {
                "stream_uplink_pre": {
                    "total_events": 2,
                    "fault_events": 2,
                    "fault_rate_pct": 100.0,
                    "decision_counts": {"delay_ns": 1, "drop": 1},
                    "latency_p50_ns": 5,
                    "latency_p95_ns": 5,
                    "latency_p99_ns": 5,
                    "delay_series_ns": [5],
                    "inferred_config": {"delay_active": True, "drop_active": True},
                }
            },
        },
        max_events=1,
        reverse_events=True,
    )

    assert "events_order=desc" not in html_text
    assert "events_included=1" not in html_text
    assert "events_truncated=true" not in html_text
    assert "faultcore report" in html_text
    assert "stdout (tail)" in html_text
    assert "Network Metrics" in html_text
    assert "Applied Configuration" in html_text
    assert "Per Function/Site" in html_text
    assert "Functions/Sites" not in html_text
    assert "Network Timeline" in html_text
    assert "Fault Events Per Bucket" not in html_text
    assert "data-series-values" in html_text
    assert "chart-tooltip" in html_text


def test_normalize_chart_series_trims_leading_zeros_when_followed_by_data():
    assert reporting._normalize_chart_series([0, 0, 12, 13]) == [12, 13]
    assert reporting._normalize_chart_series([0, 0, 0]) == [0, 0, 0]


def test_trim_initial_warmup_outlier_drops_first_when_tail_is_stable():
    assert reporting._normalize_chart_series([9, 10, 10, 10, 10, 10]) == [10, 10, 10, 10, 10]


def test_trim_initial_warmup_outlier_keeps_first_when_tail_is_variable():
    assert reporting._normalize_chart_series([100, 120, 80, 130, 70, 125]) == [100, 120, 80, 130, 70, 125]
