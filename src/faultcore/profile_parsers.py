import ipaddress

from faultcore.target_name_helpers import normalize_target_name

_ERROR_KIND_MAP = {
    "reset": 1,
    "refused": 2,
    "unreachable": 3,
}

_TARGET_PROTOCOL_MAP = {
    "any": 0,
    "tcp": 1,
    "udp": 2,
}

_MUTATION_TYPE_MAP = {
    "none": 0,
    "truncate": 1,
    "corrupt_bytes": 2,
    "inject_bytes": 3,
    "replace_pattern": 4,
    "corrupt_encoding": 5,
    "swap_bytes": 6,
}

_MUTATION_TARGET_MAP = {
    "both": 0,
    "uplink": 1,
    "uplink_only": 1,
    "downlink": 2,
    "downlink_only": 2,
}

_MS_PER_SECOND = 1000
_NS_PER_MS = 1_000_000
_PORT_MIN = 0
_PORT_MAX = 65535
_RATE_SUFFIX_MULTIPLIERS = {
    "gbps": 1_000_000_000,
    "mbps": 1_000_000,
    "kbps": 1_000,
    "bps": 1,
}
_SIZE_SUFFIX_MULTIPLIERS = {
    "gb": 1_000_000_000,
    "mb": 1_000_000,
    "kb": 1_000,
    "gbps": 1_000_000_000,
    "mbps": 1_000_000,
    "kbps": 1_000,
    "bps": 1,
}


def parse_duration(t: str) -> int:
    normalized = _non_empty_normalized(t, "duration must be non-empty")
    if normalized.endswith("ms"):
        value = float(normalized[:-2])
        _ensure_range(value, 0, float("inf"), "duration ms must be >= 0")
        return int(value)
    if normalized.endswith("s"):
        value = float(normalized[:-1])
        _ensure_range(value, 0, float("inf"), "duration s must be >= 0")
        return int(value * _MS_PER_SECOND)
    raise ValueError("duration must be in format 'Ns' or 'Nms' (e.g., '200ms', '5s', '0.5s')")


def parse_size(t: str) -> int:
    normalized = _non_empty_normalized(t, "size must be non-empty")
    matched = _match_suffix_multiplier(normalized, _SIZE_SUFFIX_MULTIPLIERS)
    if matched is not None:
        value_str, multiplier = matched
        try:
            value = float(value_str)
        except ValueError as e:
            raise ValueError(f"size value '{value_str}' is not a valid number") from e
        _ensure_range(value, 0, float("inf"), "size must be >= 0")
        return int(value * multiplier)
    raise ValueError("size must be in format 'N<suffix>' (e.g., '1kb', '5mb', '1gb', '100mbps', '1gbps')")


def build_timeout_profile(*, connect: str | None = None, recv: str | None = None) -> dict[str, int]:
    profile: dict[str, int] = {}
    if connect is not None:
        profile["connect_ms"] = parse_duration(connect)
    if recv is not None:
        profile["recv_ms"] = parse_duration(recv)
    return profile


def _ensure_range(value: float | int, minimum: float | int, maximum: float | int, error_message: str) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(error_message)


def _as_non_negative_float(value: float, error_message: str) -> float:
    if value < 0:
        raise ValueError(error_message)
    return value


def _as_non_negative_int(value: int | float, error_message: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(error_message)
    return parsed


def _pad_addr16(addr: list[int]) -> list[int]:
    return addr if len(addr) >= 16 else addr + [0] * (16 - len(addr))


def _apply_port_range(profile: dict[str, object], port_start: int | None, port_end: int | None) -> dict[str, object]:
    if port_start is not None and port_end is not None:
        profile["port_start"] = port_start
        profile["port_end"] = port_end
    return profile


def _duration_ms_to_ns(duration: str) -> int:
    return parse_duration(duration) * _NS_PER_MS


def _schedule_profile(schedule_type: int, param_a_ns: int, param_b_ns: int) -> dict[str, int]:
    return {
        "schedule_type": schedule_type,
        "param_a_ns": param_a_ns,
        "param_b_ns": param_b_ns,
        "param_c_ns": 0,
    }


def _non_empty_normalized(value: str, error_message: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _match_suffix_multiplier(value: str, multipliers: dict[str, int]) -> tuple[str, int] | None:
    for suffix, multiplier in multipliers.items():
        if value.endswith(suffix):
            return value[: -len(suffix)], multiplier
    return None


def _rate_to_bps(value: str | float | int, multiplier: int) -> int:
    return int(_as_non_negative_float(float(value), "rate must be >= 0") * multiplier)


def _parse_int_value(value: str, error_message: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(error_message) from None


def _parse_prefixed_int(value: str, *, base: int, error_message: str) -> int:
    try:
        return int(value, base)
    except ValueError:
        raise ValueError(error_message) from None


def _parse_single_port(raw: str, error_message: str) -> int:
    parsed = _parse_int_value(raw, error_message)
    if not _PORT_MIN <= parsed <= _PORT_MAX:
        raise ValueError("port must be between 0 and 65535")
    return parsed


def _validate_port_bounds(value: int, field_name: str) -> None:
    _ensure_range(value, _PORT_MIN, _PORT_MAX, f"target {field_name} must be between 0 and 65535")


def _target_profile_base(
    *,
    kind: int,
    ipv4: int,
    prefix_len: int,
    port: int,
    protocol: int,
    priority: int,
    address_family: int,
    addr: list[int],
) -> dict[str, object]:
    return {
        "enabled": 1,
        "kind": kind,
        "ipv4": ipv4,
        "prefix_len": prefix_len,
        "port": port,
        "protocol": protocol,
        "priority": priority,
        "address_family": address_family,
        "addr": addr,
    }


def _network_target_profile(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    *,
    kind: int,
    port: int,
    protocol: int,
    priority: int,
) -> dict[str, object]:
    is_ipv4 = isinstance(network, ipaddress.IPv4Network)
    return _target_profile_base(
        kind=kind,
        ipv4=int(network.network_address) if is_ipv4 else 0,
        prefix_len=int(network.prefixlen),
        port=port,
        protocol=protocol,
        priority=priority,
        address_family=1 if is_ipv4 else 2,
        addr=_pad_addr16(list(network.network_address.packed)),
    )


def _parse_priority(priority: str | int | None) -> int:
    if priority is None:
        return 100
    parsed_priority = priority if isinstance(priority, int) else int(priority)
    _ensure_range(parsed_priority, 0, 65535, "target priority must be between 0 and 65535")
    return parsed_priority


def parse_rate(rate: str) -> int:
    if not isinstance(rate, str):
        raise TypeError("rate must be a string with suffix (e.g., '100mbps', '1gbps', '500kbps', '1000bps')")

    normalized_rate = _non_empty_normalized(rate, "rate must be non-empty")
    matched = _match_suffix_multiplier(normalized_rate, _RATE_SUFFIX_MULTIPLIERS)
    if matched is not None:
        value, multiplier = matched
        return _rate_to_bps(value, multiplier)

    raise ValueError("rate must include a unit suffix (e.g., '100mbps', '1gbps', '500kbps', '1000bps')")


def parse_packet_loss(loss: str) -> int:
    if not isinstance(loss, str):
        raise TypeError("packet_loss must be a string with '%' or 'ppm' suffix (e.g., '5%', '500ppm')")

    raw = _non_empty_normalized(loss, "packet_loss must be non-empty")
    if raw.endswith("%"):
        value = float(raw[:-1])
        _ensure_range(value, 0, 100, "packet_loss percentage must be between 0 and 100")
        return int(value * 10_000)
    if raw.endswith("ppm"):
        value = float(raw[:-3])
        _ensure_range(value, 0, 1_000_000, "packet_loss ppm must be between 0 and 1000000")
        return int(value)
    raise ValueError("packet_loss must be a string with '%' or 'ppm' suffix (e.g., '5%', '500ppm')")


def parse_burst_loss(value: str) -> int:
    normalized = _non_empty_normalized(value, "burst_loss must be non-empty")
    parsed = _parse_int_value(normalized, "burst_loss must be a valid integer (e.g., '5', '10')")
    if parsed < 0:
        raise ValueError("burst_loss must be >= 0")
    return parsed


def parse_seed(value: str | int) -> int:
    if isinstance(value, int):
        return _as_non_negative_int(value, "seed must be >= 0")
    if not isinstance(value, str):
        raise TypeError("seed must be a string or integer")

    normalized = value.strip()
    if normalized.startswith(("0x", "0X")):
        return _parse_prefixed_int(normalized, base=16, error_message=f"invalid hex seed '{value}'")

    if normalized.startswith(("0b", "0B")):
        return _parse_prefixed_int(normalized, base=2, error_message=f"invalid binary seed '{value}'")

    return _as_non_negative_int(_parse_int_value(normalized, f"invalid seed '{value}'"), "seed must be >= 0")


def parse_port(value: str | int) -> tuple[int, int | None, int | None]:
    if isinstance(value, int):
        if not _PORT_MIN <= value <= _PORT_MAX:
            raise ValueError("port must be between 0 and 65535")
        return value, None, None
    if not isinstance(value, str):
        raise TypeError("port must be a string or integer")
    normalized = _non_empty_normalized(value, "port must be non-empty")
    if "-" in normalized:
        parts = normalized.split("-", 1)
        start = _parse_single_port(parts[0], "port range must contain valid integers")
        end = _parse_single_port(parts[1], "port range must contain valid integers")
        if start > end:
            raise ValueError("port range start must be <= end")
        return 0, start, end
    if "," in normalized:
        first_port = normalized.split(",", 1)[0]
        single_port = _parse_single_port(first_port, "port list must contain valid integers")
        return single_port, None, None
    parsed = _parse_single_port(
        normalized,
        "port must be a valid integer, range (e.g., '80-90'), or list (e.g., '80,443')",
    )
    return parsed, None, None


def build_direction_profile(
    *,
    latency: str | None = None,
    jitter: str | None = None,
    packet_loss: str | None = None,
    burst_loss: str | None = None,
    rate: str | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if latency is not None:
        profile["latency"] = parse_duration(latency)
    if jitter is not None:
        profile["jitter"] = parse_duration(jitter)
    if packet_loss is not None:
        profile["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss is not None:
        profile["burst_loss"] = parse_burst_loss(burst_loss)
    if rate is not None:
        profile["rate"] = parse_rate(rate)
    return profile


def build_correlated_loss_profile(
    *,
    p_good_to_bad: str,
    p_bad_to_good: str,
    loss_good: str,
    loss_bad: str,
) -> dict[str, int]:
    return {
        "enabled": 1,
        "p_good_to_bad_ppm": parse_packet_loss(p_good_to_bad),
        "p_bad_to_good_ppm": parse_packet_loss(p_bad_to_good),
        "loss_good_ppm": parse_packet_loss(loss_good),
        "loss_bad_ppm": parse_packet_loss(loss_bad),
    }


def parse_error_kind(kind: str) -> int:
    normalized = kind.strip().lower()
    parsed = _ERROR_KIND_MAP.get(normalized)
    if parsed is None:
        raise ValueError("error kind must be one of: reset, refused, unreachable")
    return parsed


def build_connection_error_profile(*, kind: str, prob: str = "100%") -> dict[str, int]:
    return {"kind": parse_error_kind(kind), "prob_ppm": parse_packet_loss(prob)}


def build_half_open_profile(*, after: str, error: str = "reset") -> dict[str, int]:
    threshold = parse_size(after)
    if threshold <= 0:
        raise ValueError("after must be > 0")
    return {"after": threshold, "err_kind": parse_error_kind(error)}


def build_packet_duplicate_profile(*, prob: str = "100%", max_extra: int = 1) -> dict[str, int]:
    extra = int(max_extra)
    if extra <= 0:
        raise ValueError("max_extra must be > 0")
    return {"prob_ppm": parse_packet_loss(prob), "max_extra": extra}


def build_packet_reorder_profile(
    *,
    prob: str = "100%",
    max_delay: str = "0ms",
    window: int = 1,
) -> dict[str, int]:
    delay_ms = parse_duration(max_delay)
    reorder_window = int(window)
    if reorder_window <= 0:
        raise ValueError("window must be > 0")
    return {
        "prob_ppm": parse_packet_loss(prob),
        "max_delay_ns": delay_ms * 1_000_000,
        "window": reorder_window,
    }


def _parse_mutation_type(value: str) -> int:
    normalized = _non_empty_normalized(value, "payload_mutation type must be non-empty")
    parsed = _MUTATION_TYPE_MAP.get(normalized)
    if parsed is None:
        raise ValueError(
            "payload_mutation type must be one of: "
            "none, truncate, corrupt_bytes, inject_bytes, replace_pattern, corrupt_encoding, swap_bytes"
        )
    return parsed


def _parse_mutation_target(value: str) -> int:
    normalized = _non_empty_normalized(value, "payload_mutation target must be non-empty")
    parsed = _MUTATION_TARGET_MAP.get(normalized)
    if parsed is None:
        raise ValueError("payload_mutation target must be one of: both, uplink_only, downlink_only")
    return parsed


def _parse_mutation_bytes(value: str | bytes | None, max_len: int) -> tuple[bytes, int]:
    if value is None:
        return b"", 0
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        raise TypeError("payload_mutation bytes values must be str or bytes")
    clipped = data[:max_len]
    return clipped, len(clipped)


def build_payload_mutation_profile(
    *,
    enabled: bool,
    prob: str = "100%",
    type: str,
    target: str = "both",
    truncate_size: str | None = None,
    corrupt_count: int | None = None,
    corrupt_seed: str | int | None = None,
    inject_position: int | None = None,
    inject_data: str | bytes | None = None,
    replace_find: str | bytes | None = None,
    replace_with: str | bytes | None = None,
    swap_pos1: int | None = None,
    swap_pos2: int | None = None,
    min_size: str | None = None,
    max_size: str | None = None,
    every_n_packets: int = 1,
    dry_run: bool = False,
    max_buffer_size: str = "64kb",
) -> dict[str, object]:
    inject_bytes, inject_len = _parse_mutation_bytes(inject_data, 64)
    replace_find_bytes, replace_find_len = _parse_mutation_bytes(replace_find, 32)
    replace_with_bytes, replace_with_len = _parse_mutation_bytes(replace_with, 32)
    return {
        "enabled": 1 if enabled else 0,
        "prob_ppm": parse_packet_loss(prob),
        "type": _parse_mutation_type(type),
        "target": _parse_mutation_target(target),
        "truncate_size": parse_size(truncate_size) if truncate_size is not None else 0,
        "corrupt_count": _as_non_negative_int(corrupt_count or 0, "payload_mutation corrupt_count must be >= 0"),
        "corrupt_seed": parse_seed(corrupt_seed or 0),
        "inject_position": _as_non_negative_int(inject_position or 0, "payload_mutation inject_position must be >= 0"),
        "inject_data": inject_bytes,
        "inject_len": inject_len,
        "replace_find": replace_find_bytes,
        "replace_find_len": replace_find_len,
        "replace_with": replace_with_bytes,
        "replace_with_len": replace_with_len,
        "swap_pos1": _as_non_negative_int(swap_pos1 or 0, "payload_mutation swap_pos1 must be >= 0"),
        "swap_pos2": _as_non_negative_int(swap_pos2 or 0, "payload_mutation swap_pos2 must be >= 0"),
        "min_size": parse_size(min_size) if min_size is not None else 0,
        "max_size": parse_size(max_size) if max_size is not None else 0,
        "every_n_packets": _as_non_negative_int(every_n_packets, "payload_mutation every_n_packets must be >= 0"),
        "dry_run": 1 if dry_run else 0,
        "max_buffer_size": parse_size(max_buffer_size),
    }


def build_dns_profile(
    *,
    delay: str | None = None,
    timeout: str | None = None,
    nxdomain: str | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if delay is not None:
        profile["delay_ms"] = parse_duration(delay)
    if timeout is not None:
        profile["timeout_ms"] = parse_duration(timeout)
    if nxdomain is not None:
        profile["nxdomain_ppm"] = parse_packet_loss(nxdomain)
    return profile


def parse_target_protocol(protocol: str | None) -> int:
    if protocol is None:
        return 0
    try:
        return _TARGET_PROTOCOL_MAP[_non_empty_normalized(protocol, "target protocol must be non-empty")]
    except KeyError as exc:
        raise ValueError("target protocol must be one of: any, tcp, udp") from exc


def _parse_target_host_port(raw: str) -> tuple[str, int]:
    if not raw:
        raise ValueError("target must be non-empty")

    if raw.startswith("["):
        end = raw.find("]")
        if end == -1:
            raise ValueError("target IPv6 host must close bracket with ']'")
        host = raw[1:end]
        tail = raw[end + 1 :]
        if not tail:
            return host, 0
        if not tail.startswith(":"):
            raise ValueError("target must use [host]:port format for bracketed hosts")
        return host, int(tail[1:])

    colon_count = raw.count(":")
    if colon_count > 1:
        raise ValueError("target IPv6 must use brackets in string format, e.g. tcp://[2001:db8::1]:443")
    if colon_count == 1:
        host, port_str = raw.rsplit(":", 1)
        return host, int(port_str)
    return raw, 0


def _parse_target_string(
    target: str,
    *,
    parsed_protocol: int,
    parsed_port: int,
    parsed_port_start: int | None,
    parsed_port_end: int | None,
) -> tuple[int, str | None, str | None, int]:
    raw = target.strip()
    if not raw:
        raise ValueError("target must be non-empty")

    if "://" in raw:
        proto_raw, raw = raw.split("://", 1)
        proto_from_target = parse_target_protocol(proto_raw)
        if parsed_protocol and parsed_protocol != proto_from_target:
            raise ValueError("target protocol conflicts with protocol parameter")
        parsed_protocol = proto_from_target

    if "/" in raw:
        return parsed_protocol, None, raw, parsed_port

    host, target_port = _parse_target_host_port(raw)
    if parsed_port != 0 and target_port != 0 and parsed_port != target_port:
        raise ValueError("target port conflicts with port parameter")
    if target_port != 0 and (parsed_port_start is not None or parsed_port_end is not None):
        raise ValueError("target port conflicts with port_start/port_end parameters")

    resolved_port = target_port or parsed_port
    return parsed_protocol, host, None, resolved_port


def _semantic_target_profile(
    *,
    hostname: str | None,
    sni: str | None,
    port: int,
    protocol: int,
    priority: int,
) -> dict[str, object]:
    profile = _target_profile_base(
        kind=0,
        ipv4=0,
        prefix_len=0,
        port=port,
        protocol=protocol,
        priority=priority,
        address_family=0,
        addr=[0] * 16,
    )
    if hostname is not None:
        profile["hostname"] = hostname
    if sni is not None:
        profile["sni"] = sni
    return profile


def build_target_profile(
    *,
    target: str | None = None,
    host: str | None = None,
    cidr: str | None = None,
    hostname: str | None = None,
    sni: str | None = None,
    port: str | int | None = None,
    protocol: str | None = None,
    priority: str | int | None = None,
) -> dict[str, object]:
    parsed_protocol = parse_target_protocol(protocol)
    parsed_host = host
    if port is not None:
        parsed_port, parsed_port_start, parsed_port_end = parse_port(port)
    else:
        parsed_port = 0
        parsed_port_start = None
        parsed_port_end = None
    parsed_cidr = cidr
    parsed_hostname = normalize_target_name(hostname, "target hostname") if hostname is not None else None
    parsed_sni = normalize_target_name(sni, "target sni") if sni is not None else None

    if target is not None:
        parsed_protocol, target_host, target_cidr, parsed_port = _parse_target_string(
            target,
            parsed_protocol=parsed_protocol,
            parsed_port=parsed_port,
            parsed_port_start=parsed_port_start,
            parsed_port_end=parsed_port_end,
        )
        if target_host is not None:
            parsed_host = target_host
        if target_cidr is not None:
            parsed_cidr = target_cidr

    _validate_port_bounds(parsed_port, "port")
    if parsed_port_start is not None and parsed_port_end is not None:
        _validate_port_bounds(parsed_port_start, "port_start")
        _validate_port_bounds(parsed_port_end, "port_end")
        if parsed_port_start > parsed_port_end:
            raise ValueError("target port_start must be <= port_end")
    parsed_priority = _parse_priority(priority)

    if parsed_hostname and parsed_sni:
        raise ValueError("target cannot define both hostname and sni")
    has_semantic_name = parsed_hostname is not None or parsed_sni is not None

    if parsed_host and parsed_cidr:
        raise ValueError("target cannot define both host and cidr")
    if has_semantic_name and (parsed_host or parsed_cidr):
        raise ValueError("target cannot mix host/cidr with hostname/sni")
    if not parsed_host and not parsed_cidr and not has_semantic_name:
        raise ValueError("target requires either host or cidr")

    if has_semantic_name:
        return _apply_port_range(
            _semantic_target_profile(
                hostname=parsed_hostname,
                sni=parsed_sni,
                port=parsed_port,
                protocol=parsed_protocol,
                priority=parsed_priority,
            ),
            parsed_port_start,
            parsed_port_end,
        )

    if parsed_host:
        try:
            address = ipaddress.ip_address(parsed_host)
        except ValueError as exc:
            raise ValueError("target host must be a valid IPv4 or IPv6 address") from exc
        prefix_len = 32 if isinstance(address, ipaddress.IPv4Address) else 128
        network = ipaddress.ip_network(f"{address}/{prefix_len}", strict=False)
        return _apply_port_range(
            _network_target_profile(
                network,
                kind=1,
                port=parsed_port,
                protocol=parsed_protocol,
                priority=parsed_priority,
            ),
            parsed_port_start,
            parsed_port_end,
        )

    try:
        network = ipaddress.ip_network(parsed_cidr, strict=False)
    except ValueError as exc:
        raise ValueError("target cidr must be a valid IPv4 or IPv6 CIDR") from exc
    max_prefix_len = 32 if isinstance(network, ipaddress.IPv4Network) else 128
    if network.prefixlen < 0 or network.prefixlen > max_prefix_len:
        raise ValueError(f"target prefix_len must be between 0 and {max_prefix_len}")
    return _apply_port_range(
        _network_target_profile(
            network,
            kind=2,
            port=parsed_port,
            protocol=parsed_protocol,
            priority=parsed_priority,
        ),
        parsed_port_start,
        parsed_port_end,
    )


def build_schedule_profile(
    *,
    kind: str,
    every: str | None = None,
    duration: str | None = None,
    on: str | None = None,
    off: str | None = None,
    ramp: str | None = None,
) -> dict[str, int]:
    normalized = _non_empty_normalized(kind, "schedule kind must be non-empty")
    match normalized:
        case "spike":
            if every is None or duration is None:
                raise ValueError("spike profile requires every and duration")
            cycle_ns = _duration_ms_to_ns(every)
            active_ns = _duration_ms_to_ns(duration)
            if cycle_ns <= 0 or active_ns <= 0 or active_ns > cycle_ns:
                raise ValueError("spike profile requires 0 < duration <= every")
            return _schedule_profile(2, cycle_ns, active_ns)
        case "flapping":
            if on is None or off is None:
                raise ValueError("flapping profile requires on and off")
            on_ns = _duration_ms_to_ns(on)
            off_ns = _duration_ms_to_ns(off)
            if on_ns <= 0 or off_ns <= 0:
                raise ValueError("flapping profile requires on > 0 and off > 0")
            return _schedule_profile(3, on_ns, off_ns)
        case "ramp":
            if ramp is None:
                raise ValueError("ramp profile requires ramp")
            ramp_ns = _duration_ms_to_ns(ramp)
            if ramp_ns <= 0:
                raise ValueError("ramp profile requires ramp > 0")
            return _schedule_profile(1, ramp_ns, 0)
        case _:
            raise ValueError("schedule kind must be one of: ramp, spike, flapping")


def build_session_budget_profile(
    *,
    max_tx: str | None = None,
    max_rx: str | None = None,
    max_ops: int | None = None,
    max_duration: str | None = None,
    action: str = "drop",
    budget_timeout: str | None = None,
    error: str | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}

    if max_tx is not None:
        profile["max_bytes_tx"] = parse_size(max_tx)
    if max_rx is not None:
        profile["max_bytes_rx"] = parse_size(max_rx)
    if max_ops is not None:
        if max_ops <= 0:
            raise ValueError("session_budget max_ops must be > 0")
        profile["max_ops"] = max_ops
    if max_duration is not None:
        profile["max_duration"] = parse_duration(max_duration)

    if not profile:
        raise ValueError("session_budget requires at least one limit")

    normalized_action = _non_empty_normalized(action, "session_budget action must be non-empty")
    match normalized_action:
        case "drop":
            profile["action"] = 1
            if budget_timeout is not None:
                raise ValueError("session_budget budget_timeout only applies to action=timeout")
            if error is not None:
                raise ValueError("session_budget error only applies to action=connection_error")
        case "timeout":
            profile["action"] = 2
            if budget_timeout is None:
                raise ValueError("session_budget budget_timeout is required for action=timeout")
            timeout_ms = parse_duration(budget_timeout)
            if timeout_ms <= 0:
                raise ValueError("session_budget budget_timeout must be > 0")
            profile["budget_timeout"] = timeout_ms
            if error is not None:
                raise ValueError("session_budget error only applies to action=connection_error")
        case "connection_error":
            profile["action"] = 3
            profile["error_kind"] = parse_error_kind(error or "reset")
            if budget_timeout is not None:
                raise ValueError("session_budget budget_timeout only applies to action=timeout")
        case _:
            raise ValueError("session_budget action must be one of: drop, timeout, connection_error")

    return profile
