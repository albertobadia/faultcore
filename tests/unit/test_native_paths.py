import pytest

from faultcore import native


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("x86_64", "linux-x86_64"),
        ("amd64", "linux-x86_64"),
        ("i686", "linux-i686"),
        ("x86", "linux-i686"),
        ("aarch64", "linux-aarch64"),
        ("arm64", "linux-aarch64"),
    ],
)
def test_get_platform_tag_accepts_linux_arch_aliases(machine: str, expected: str) -> None:
    assert native.get_platform_tag(system="Linux", machine=machine) == expected


def test_get_platform_tag_rejects_non_linux() -> None:
    with pytest.raises(RuntimeError, match="Unsupported operating system"):
        native.get_platform_tag(system="Darwin", machine="arm64")


def test_get_interceptor_path_resolves_native_layout(monkeypatch, tmp_path) -> None:
    native_dir = tmp_path / "_native" / "linux-aarch64"
    native_dir.mkdir(parents=True)
    interceptor = native_dir / "libfaultcore_interceptor.so"
    interceptor.write_bytes(b"")

    monkeypatch.setattr(native, "_package_dir", lambda: tmp_path)
    monkeypatch.setattr(native, "get_platform_tag", lambda: "linux-aarch64")

    assert native.get_interceptor_path() == str(interceptor)


def test_get_interceptor_path_raises_when_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(native, "_package_dir", lambda: tmp_path)
    monkeypatch.setattr(native, "get_platform_tag", lambda: "linux-aarch64")

    with pytest.raises(FileNotFoundError, match="Interceptor not found"):
        native.get_interceptor_path()


def test_get_extension_path_prefers_package_level_binary(monkeypatch, tmp_path) -> None:
    package_level = tmp_path / "_faultcore.abi3.so"
    package_level.write_bytes(b"top-level")

    native_dir = tmp_path / "_native" / "linux-aarch64"
    native_dir.mkdir(parents=True)
    (native_dir / "_faultcore.abi3.so").write_bytes(b"native-layout")

    monkeypatch.setattr(native, "_package_dir", lambda: tmp_path)
    monkeypatch.setattr(native, "get_platform_tag", lambda: "linux-aarch64")

    assert native.get_extension_path() == str(package_level)


def test_get_extension_path_falls_back_to_native_layout(monkeypatch, tmp_path) -> None:
    native_dir = tmp_path / "_native" / "linux-aarch64"
    native_dir.mkdir(parents=True)
    native_ext = native_dir / "_faultcore.abi3.so"
    native_ext.write_bytes(b"native-layout")

    monkeypatch.setattr(native, "_package_dir", lambda: tmp_path)
    monkeypatch.setattr(native, "get_platform_tag", lambda: "linux-aarch64")

    assert native.get_extension_path() == str(native_ext)
