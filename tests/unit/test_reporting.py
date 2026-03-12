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
    assert record["events"] == []
    assert record["summary"]["errors"] == 0


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
        },
        max_events=1,
        reverse_events=True,
    )

    assert "events_order=desc" in html_text
    assert "events_included=1" in html_text
    assert "events_truncated=true" in html_text
    assert "faultcore report" in html_text
