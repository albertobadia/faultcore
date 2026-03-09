import faultcore


def test_is_interceptor_loaded_returns_bool():
    result = faultcore.is_interceptor_loaded()
    assert isinstance(result, bool)


def test_is_interceptor_loaded_without_preload():
    import os

    original = os.environ.get("LD_PRELOAD")
    if "LD_PRELOAD" in os.environ:
        del os.environ["LD_PRELOAD"]
    try:
        import ctypes

        is_active = hasattr(ctypes.CDLL(None), "faultcore_interceptor_is_active")

        result = faultcore.is_interceptor_loaded()
        if not is_active:
            assert result is False
        else:
            assert result is True
    finally:
        if original:
            os.environ["LD_PRELOAD"] = original


def test_get_interceptor_path_returns_none_without_build():
    result = faultcore.get_interceptor_path()
    assert result is None or isinstance(result, str)


def test_get_interceptor_path_returns_string_when_exists(monkeypatch, tmp_path):
    from pathlib import Path

    test_so = tmp_path / "libfaultcore_interceptor.so"
    test_so.write_text("dummy")

    def mock_cwd():
        return tmp_path

    monkeypatch.setattr(Path, "cwd", mock_cwd)

    result = faultcore.get_interceptor_path()
    assert result == str(test_so)


def test_get_fault_metrics_raises_when_symbol_missing(monkeypatch):
    import ctypes

    class FakeLib:
        pass

    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: FakeLib())

    try:
        faultcore.get_fault_metrics()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "faultcore_metrics_snapshot is not available" in str(exc)


def test_get_fault_metrics_returns_snapshot_and_supports_reset(monkeypatch):
    import ctypes

    class FakeSnapshotFn:
        def __init__(self):
            self.argtypes = None
            self.restype = None

        def __call__(self, ptr):
            snapshot = ptr._obj
            snapshot.len = 1
            layer = snapshot.layers[0]
            layer.stage = 1
            layer.continue_count = 2
            layer.delay_count = 3
            layer.drop_count = 4
            layer.timeout_count = 5
            layer.error_count = 6
            layer.connection_error_count = 7
            layer.reorder_count = 8
            layer.duplicate_count = 9
            layer.nxdomain_count = 10
            layer.skipped_count = 11
            return True

    class FakeResetFn:
        def __init__(self):
            self.called = False

        def __call__(self):
            self.called = True

    class FakeLib:
        def __init__(self):
            self.faultcore_metrics_snapshot = FakeSnapshotFn()
            self.faultcore_metrics_reset = FakeResetFn()

    fake_lib = FakeLib()
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_lib)

    metrics = faultcore.get_fault_metrics(reset=True)

    assert metrics["layers"] == [
        {
            "stage": "L1",
            "continue": 2,
            "delay": 3,
            "drop": 4,
            "timeout": 5,
            "error": 6,
            "connection_error": 7,
            "reorder": 8,
            "duplicate": 9,
            "nxdomain": 10,
            "skipped": 11,
        }
    ]
    assert metrics["totals"] == {
        "continue": 2,
        "delay": 3,
        "drop": 4,
        "timeout": 5,
        "error": 6,
        "connection_error": 7,
        "reorder": 8,
        "duplicate": 9,
        "nxdomain": 10,
        "skipped": 11,
    }
    assert fake_lib.faultcore_metrics_reset.called is True


def test_get_fault_metrics_context_scope_requires_active_context(monkeypatch):
    import ctypes

    class FakeSnapshotFn:
        def __init__(self):
            self.argtypes = None
            self.restype = None

        def __call__(self, ptr):
            snapshot = ptr._obj
            snapshot.len = 1
            layer = snapshot.layers[0]
            layer.stage = 1
            layer.continue_count = 1
            return True

    class FakeLib:
        def __init__(self):
            self.faultcore_metrics_snapshot = FakeSnapshotFn()

    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: FakeLib())

    try:
        faultcore.get_fault_metrics(scope="context")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "no active fault metrics context" in str(exc)


def test_get_fault_metrics_context_scope_returns_delta(monkeypatch):
    import ctypes

    class FakeSnapshotFn:
        def __init__(self):
            self.argtypes = None
            self.restype = None
            self.calls = 0

        def __call__(self, ptr):
            self.calls += 1
            snapshot = ptr._obj
            snapshot.len = 1
            layer = snapshot.layers[0]
            layer.stage = 1
            base = 10 if self.calls == 1 else 16
            layer.continue_count = base
            layer.delay_count = base + 1
            return True

    class FakeLib:
        def __init__(self):
            self.faultcore_metrics_snapshot = FakeSnapshotFn()

    fake_lib = FakeLib()
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_lib)

    with faultcore.fault_context("x"):
        metrics = faultcore.get_fault_metrics(scope="context")

    assert metrics["layers"] == [
        {
            "stage": "L1",
            "continue": 6,
            "delay": 6,
            "drop": 0,
            "timeout": 0,
            "error": 0,
            "connection_error": 0,
            "reorder": 0,
            "duplicate": 0,
            "nxdomain": 0,
            "skipped": 0,
        }
    ]
    assert metrics["totals"]["continue"] == 6
    assert metrics["totals"]["delay"] == 6
