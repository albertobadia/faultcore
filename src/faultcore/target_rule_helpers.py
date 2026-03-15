from collections.abc import Sequence
from typing import Any

from faultcore.target_name_helpers import encode_target_name_bytes

_U64_MAX = 0xFFFFFFFFFFFFFFFF
_U32_MAX = 0xFFFFFFFF


def rule_int(rule: dict[str, Any], key: str, default: int, idx: int) -> int:
    try:
        return int(rule.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"targets[{idx}].{key} must be an integer") from exc


def _addr16_from_rule(rule: dict[str, Any], idx: int) -> bytes:
    raw = rule.get("addr")
    if raw is None:
        return b"\x00" * 16
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) != 16:
            raise ValueError(f"targets[{idx}].addr must contain exactly 16 bytes")
        return bytes(raw)
    if isinstance(raw, Sequence):
        values = list(raw)
        if len(values) != 16:
            raise ValueError(f"targets[{idx}].addr must contain exactly 16 bytes")
        try:
            return bytes(int(v) & 0xFF for v in values)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"targets[{idx}].addr must contain integer byte values") from exc
    raise ValueError(f"targets[{idx}].addr must be bytes-like or a 16-item sequence")


def normalize_target_address(rule: dict[str, Any], idx: int) -> tuple[int, bytes]:
    ipv4 = rule_int(rule, "ipv4", 0, idx)
    if not 0 <= ipv4 <= _U32_MAX:
        raise ValueError(f"targets[{idx}].ipv4 must be a valid u32 value")

    kind = rule_int(rule, "kind", 0, idx)
    family = rule_int(rule, "address_family", 0, idx)
    if family not in (0, 1, 2):
        raise ValueError(f"targets[{idx}].address_family must be one of 0, 1, 2")

    has_addr = rule.get("addr") is not None
    if family == 0 and kind in (1, 2) and not has_addr:
        family = 1

    if family == 1:
        if has_addr:
            return family, _addr16_from_rule(rule, idx)
        return family, ipv4.to_bytes(4, "big") + (b"\x00" * 12)
    if family == 2:
        return family, _addr16_from_rule(rule, idx)
    return 0, b"\x00" * 16


def resolve_port_range(rule: dict[str, Any], idx: int) -> tuple[int, int]:
    has_port = rule.get("port") is not None
    has_start = rule.get("port_start") is not None
    has_end = rule.get("port_end") is not None

    if has_port and (has_start or has_end):
        raise ValueError(f"targets[{idx}] cannot define both port and port_start/port_end")
    if has_start != has_end:
        raise ValueError(f"targets[{idx}] requires both port_start and port_end")

    if has_start and has_end:
        start = rule_int(rule, "port_start", 0, idx)
        end = rule_int(rule, "port_end", 0, idx)
    else:
        port = rule_int(rule, "port", 0, idx)
        if port == 0:
            return 0, 0
        start, end = port, port

    if not 0 <= start <= 65535:
        raise ValueError(f"targets[{idx}].port_start must be between 0 and 65535")
    if not 0 <= end <= 65535:
        raise ValueError(f"targets[{idx}].port_end must be between 0 and 65535")
    if start > end:
        raise ValueError(f"targets[{idx}].port_start must be <= port_end")
    return start, end


def validate_target_rule(rule: dict[str, Any], idx: int) -> None:
    enabled = rule_int(rule, "enabled", 0, idx)
    if enabled not in (0, 1):
        raise ValueError(f"targets[{idx}].enabled must be 0 or 1")

    priority = rule_int(rule, "priority", 100, idx)
    if not 0 <= priority <= _U64_MAX:
        raise ValueError(f"targets[{idx}].priority must be between 0 and 18446744073709551615")

    kind = rule_int(rule, "kind", 0, idx)
    if kind not in (0, 1, 2):
        raise ValueError(f"targets[{idx}].kind must be one of 0, 1, 2")

    hostname_bytes = encode_target_name_bytes(rule.get("hostname"), f"targets[{idx}].hostname")
    sni_bytes = encode_target_name_bytes(rule.get("sni"), f"targets[{idx}].sni")
    has_hostname = any(hostname_bytes)
    has_sni = any(sni_bytes)
    if has_hostname and has_sni:
        raise ValueError(f"targets[{idx}] cannot define both hostname and sni")
    if (has_hostname or has_sni) and kind != 0:
        raise ValueError(f"targets[{idx}] semantic hostname/sni rules require kind=0")
    if enabled == 1 and not (has_hostname or has_sni) and kind == 0:
        raise ValueError(f"targets[{idx}] requires kind host/cidr or hostname/sni")

    address_family, _ = normalize_target_address(rule, idx)
    prefix_len = rule_int(rule, "prefix_len", 0, idx)
    max_prefix = 128 if address_family == 2 else 32
    if not 0 <= prefix_len <= max_prefix:
        raise ValueError(f"targets[{idx}].prefix_len must be between 0 and {max_prefix}")

    protocol = rule_int(rule, "protocol", 0, idx)
    if protocol not in (0, 1, 2):
        raise ValueError(f"targets[{idx}].protocol must be one of 0, 1, 2")

    resolve_port_range(rule, idx)
