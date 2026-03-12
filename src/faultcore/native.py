import os
import platform
from pathlib import Path

_LINUX_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


def _resolve_override(env_var: str) -> str | None:
    override = os.environ.get(env_var)
    if not override:
        return None

    override_path = Path(override)
    if not override_path.is_file():
        raise FileNotFoundError(f"{env_var} does not point to a file: {override}")
    return str(override_path)


def _resolve_first_existing(paths: tuple[Path, ...], *, not_found_message: str) -> str:
    for path in paths:
        if path.is_file():
            return str(path)
    raise FileNotFoundError(not_found_message)


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def get_platform_tag(*, system: str | None = None, machine: str | None = None) -> str:
    detected_system = system or platform.system()
    if detected_system != "Linux":
        raise RuntimeError(f"Unsupported operating system for native artifacts: {detected_system}")

    raw_machine = (machine or platform.machine()).lower()
    normalized_machine = _LINUX_ARCH_ALIASES.get(raw_machine)
    if normalized_machine is None:
        raise RuntimeError(f"Unsupported CPU architecture for native artifacts: {raw_machine}")
    return f"linux-{normalized_machine}"


def get_interceptor_path() -> str:
    override = _resolve_override("FAULTCORE_INTERCEPTOR_PATH")
    if override is not None:
        return override

    path = _package_dir() / "_native" / get_platform_tag() / "libfaultcore_interceptor.so"
    return _resolve_first_existing((path,), not_found_message=f"Interceptor not found at expected path: {path}")


def get_extension_path() -> str:
    override = _resolve_override("FAULTCORE_EXTENSION_PATH")
    if override is not None:
        return override

    package_dir = _package_dir()
    package_level = package_dir / "_faultcore.abi3.so"
    native_layout = package_dir / "_native" / get_platform_tag() / "_faultcore.abi3.so"
    return _resolve_first_existing(
        (package_level, native_layout),
        not_found_message=f"Faultcore extension not found. Checked: {package_level} and {native_layout}",
    )
