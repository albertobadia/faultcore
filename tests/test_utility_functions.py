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
        result = faultcore.is_interceptor_loaded()
        assert result is False
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
