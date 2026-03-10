import ipaddress


def parse_rate(rate: str | int | float) -> int:
    def as_non_negative(value: float) -> float:
        if value < 0:
            raise ValueError("rate must be >= 0")
        return value

    if isinstance(rate, (int, float)):
        return int(as_non_negative(float(rate)) * 1_000_000)

    normalized_rate = rate.strip().lower()
    units = {
        "gbps": 1_000_000_000,
        "mbps": 1_000_000,
        "kbps": 1_000,
        "bps": 1,
    }
    for suffix, multiplier in units.items():
        if normalized_rate.endswith(suffix):
            numeric = as_non_negative(float(normalized_rate[: -len(suffix)]))
            return int(numeric * multiplier)

    return int(as_non_negative(float(normalized_rate)))


def parse_packet_loss(loss: str | int | float) -> int:
    if isinstance(loss, str):
        raw = loss.strip().lower()
        if raw.endswith("%"):
            value = float(raw[:-1])
            if value < 0 or value > 100:
                raise ValueError("packet_loss percentage must be between 0 and 100")
            return int(value * 10_000)
        if raw.endswith("ppm"):
            value = float(raw[:-3])
            if value < 0 or value > 1_000_000:
                raise ValueError("packet_loss ppm must be between 0 and 1000000")
            return int(value)
        value = float(raw)
    else:
        value = float(loss)

    if value < 0:
        raise ValueError("packet_loss must be >= 0")
    if value <= 1:
        return int(value * 1_000_000)
    if value <= 100:
        return int(value * 10_000)
    if value <= 1_000_000:
        return int(value)
    raise ValueError("packet_loss must be <= 100%, <=1.0 ratio, or <=1000000ppm")


def build_direction_profile(
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        profile["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        profile["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        profile["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        profile["burst_loss_len"] = b
    if rate is not None:
        profile["bandwidth_bps"] = parse_rate(rate)
    return profile


def build_correlated_loss_profile(
    *,
    p_good_to_bad: str | int | float,
    p_bad_to_good: str | int | float,
    loss_good: str | int | float,
    loss_bad: str | int | float,
) -> dict[str, int]:
    profile = {
        "p_good_to_bad_ppm": parse_packet_loss(p_good_to_bad),
        "p_bad_to_good_ppm": parse_packet_loss(p_bad_to_good),
        "loss_good_ppm": parse_packet_loss(loss_good),
        "loss_bad_ppm": parse_packet_loss(loss_bad),
    }
    profile["enabled"] = 1
    return profile


def parse_error_kind(kind: str) -> int:
    normalized = kind.strip().lower()
    if normalized == "reset":
        return 1
    if normalized == "refused":
        return 2
    if normalized == "unreachable":
        return 3
    raise ValueError("error kind must be one of: reset, refused, unreachable")


def build_connection_error_profile(*, kind: str, prob: str | int | float = "100%") -> dict[str, int]:
    return {"kind": parse_error_kind(kind), "prob_ppm": parse_packet_loss(prob)}


def build_half_open_profile(*, after_bytes: int, error: str = "reset") -> dict[str, int]:
    threshold = int(after_bytes)
    if threshold <= 0:
        raise ValueError("after_bytes must be > 0")
    return {"after_bytes": threshold, "err_kind": parse_error_kind(error)}


def build_packet_duplicate_profile(*, prob: str | int | float = "100%", max_extra: int = 1) -> dict[str, int]:
    extra = int(max_extra)
    if extra <= 0:
        raise ValueError("max_extra must be > 0")
    return {"prob_ppm": parse_packet_loss(prob), "max_extra": extra}


def build_packet_reorder_profile(
    *,
    prob: str | int | float = "100%",
    max_delay_ms: int = 0,
    window: int = 1,
) -> dict[str, int]:
    delay_ms = int(max_delay_ms)
    if delay_ms < 0:
        raise ValueError("max_delay_ms must be >= 0")
    reorder_window = int(window)
    if reorder_window <= 0:
        raise ValueError("window must be > 0")
    return {
        "prob_ppm": parse_packet_loss(prob),
        "max_delay_ns": delay_ms * 1_000_000,
        "window": reorder_window,
    }


def build_dns_profile(
    *,
    delay_ms: int | None = None,
    timeout_ms: int | None = None,
    nxdomain: str | int | float | None = None,
) -> dict[str, int]:
    profile: dict[str, int] = {}
    if delay_ms is not None:
        d = int(delay_ms)
        if d < 0:
            raise ValueError("dns delay must be >= 0")
        profile["delay_ms"] = d
    if timeout_ms is not None:
        t = int(timeout_ms)
        if t < 0:
            raise ValueError("dns timeout must be >= 0")
        profile["timeout_ms"] = t
    if nxdomain is not None:
        profile["nxdomain_ppm"] = parse_packet_loss(nxdomain)
    return profile


def parse_target_protocol(protocol: str | None) -> int:
    if protocol is None:
        return 0
    normalized = protocol.strip().lower()
    if normalized == "tcp":
        return 1
    if normalized == "udp":
        return 2
    raise ValueError("target protocol must be one of: tcp, udp")


def build_target_profile(
    *,
    target: str | None = None,
    host: str | None = None,
    cidr: str | None = None,
    port: int | None = None,
    protocol: str | None = None,
    priority: int | None = None,
) -> dict[str, int]:
    parsed_protocol = parse_target_protocol(protocol)
    parsed_host = host
    parsed_port = int(port) if port is not None else 0
    parsed_cidr = cidr

    if target is not None:
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
            parsed_cidr = raw
        else:
            if ":" in raw:
                host_part, port_part = raw.rsplit(":", 1)
                raw = host_part
                if parsed_port != 0 and parsed_port != int(port_part):
                    raise ValueError("target port conflicts with port parameter")
                parsed_port = int(port_part)
            parsed_host = raw

    if parsed_port < 0 or parsed_port > 65535:
        raise ValueError("target port must be between 0 and 65535")
    parsed_priority = 100 if priority is None else int(priority)
    if parsed_priority < 0 or parsed_priority > 65535:
        raise ValueError("target priority must be between 0 and 65535")

    if parsed_host and parsed_cidr:
        raise ValueError("target cannot define both host and cidr")
    if not parsed_host and not parsed_cidr:
        raise ValueError("target requires either host or cidr")

    if parsed_host:
        try:
            ipv4 = int(ipaddress.IPv4Address(parsed_host))
        except ipaddress.AddressValueError as exc:
            raise ValueError("target host must be a valid IPv4 address (IPv6 is not supported)") from exc
        return {
            "enabled": 1,
            "kind": 1,
            "ipv4": ipv4,
            "prefix_len": 32,
            "port": parsed_port,
            "protocol": parsed_protocol,
            "priority": parsed_priority,
        }

    network = ipaddress.IPv4Network(parsed_cidr, strict=False)
    return {
        "enabled": 1,
        "kind": 2,
        "ipv4": int(network.network_address),
        "prefix_len": int(network.prefixlen),
        "port": parsed_port,
        "protocol": parsed_protocol,
        "priority": parsed_priority,
    }


def build_schedule_profile(
    *,
    kind: str,
    every_s: int | float | None = None,
    duration_s: int | float | None = None,
    on_s: int | float | None = None,
    off_s: int | float | None = None,
    ramp_s: int | float | None = None,
) -> dict[str, int]:
    normalized = kind.strip().lower()
    if normalized == "spike":
        if every_s is None or duration_s is None:
            raise ValueError("spike profile requires every_s and duration_s")
        cycle_ns = int(float(every_s) * 1_000_000_000)
        active_ns = int(float(duration_s) * 1_000_000_000)
        if cycle_ns <= 0 or active_ns <= 0 or active_ns > cycle_ns:
            raise ValueError("spike profile requires 0 < duration_s <= every_s")
        return {"schedule_type": 2, "param_a_ns": cycle_ns, "param_b_ns": active_ns, "param_c_ns": 0}

    if normalized == "flapping":
        if on_s is None or off_s is None:
            raise ValueError("flapping profile requires on_s and off_s")
        on_ns = int(float(on_s) * 1_000_000_000)
        off_ns = int(float(off_s) * 1_000_000_000)
        if on_ns <= 0 or off_ns <= 0:
            raise ValueError("flapping profile requires on_s > 0 and off_s > 0")
        return {"schedule_type": 3, "param_a_ns": on_ns, "param_b_ns": off_ns, "param_c_ns": 0}

    if normalized == "ramp":
        if ramp_s is None:
            raise ValueError("ramp profile requires ramp_s")
        ramp_ns = int(float(ramp_s) * 1_000_000_000)
        if ramp_ns <= 0:
            raise ValueError("ramp profile requires ramp_s > 0")
        return {"schedule_type": 1, "param_a_ns": ramp_ns, "param_b_ns": 0, "param_c_ns": 0}

    raise ValueError("schedule kind must be one of: ramp, spike, flapping")
