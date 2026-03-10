from typing import Any

TARGET_NAME_MAX_BYTES = 32


def normalize_target_name(value: str, field_label: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError(f"{field_label} must be non-empty")

    has_wildcard = raw.startswith("*.")
    if "*" in raw and not has_wildcard:
        raise ValueError(f"{field_label} wildcard must use leading '*.' suffix format")
    if raw.count("*") > 1:
        raise ValueError(f"{field_label} wildcard must contain a single '*'")

    core = raw[2:] if has_wildcard else raw
    if not core:
        raise ValueError(f"{field_label} wildcard must include a suffix domain")

    try:
        normalized_core = core.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"{field_label} must be a valid DNS name") from exc

    normalized_core = normalized_core.rstrip(".")
    if not normalized_core:
        raise ValueError(f"{field_label} must be a valid DNS name")

    if has_wildcard and "." not in normalized_core:
        raise ValueError(f"{field_label} wildcard must include a suffix domain")

    normalized = f"*.{normalized_core}" if has_wildcard else normalized_core
    if len(normalized.encode("ascii")) > TARGET_NAME_MAX_BYTES:
        raise ValueError(f"{field_label} must fit in {TARGET_NAME_MAX_BYTES} bytes")
    return normalized


def encode_target_name_bytes(value: Any, field_label: str) -> bytes:
    if value is None:
        return b"\x00" * TARGET_NAME_MAX_BYTES
    if not isinstance(value, str):
        raise ValueError(f"{field_label} must be a string")
    normalized = normalize_target_name(value, field_label)
    return normalized.encode("ascii").ljust(TARGET_NAME_MAX_BYTES, b"\x00")
