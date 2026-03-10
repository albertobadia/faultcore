import contextvars
import copy
import json
import threading
from pathlib import Path
from typing import Any

from faultcore.profile_parsers import (
    build_connection_error_profile,
    build_correlated_loss_profile,
    build_direction_profile,
    build_dns_profile,
    build_half_open_profile,
    build_packet_duplicate_profile,
    build_packet_reorder_profile,
    build_schedule_profile,
    build_target_profile,
    parse_packet_loss,
    parse_rate,
)

_POLICY_REGISTRY: dict[str, dict[str, Any]] = {}
_THREAD_POLICY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "faultcore_thread_policy",
    default=None,
)
_POLICY_LOCK = threading.RLock()


def get_policy_for_apply(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.get(name)


def register_policy(
    name: str,
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
    timeout_ms: int | None = None,
    connect_timeout_ms: int | None = None,
    recv_timeout_ms: int | None = None,
    uplink: dict[str, Any] | None = None,
    downlink: dict[str, Any] | None = None,
    correlated_loss: dict[str, Any] | None = None,
    connection_error: dict[str, Any] | None = None,
    half_open: dict[str, Any] | None = None,
    packet_duplicate: dict[str, Any] | None = None,
    packet_reorder: dict[str, Any] | None = None,
    dns_delay_ms: int | None = None,
    dns_timeout_ms: int | None = None,
    dns_nxdomain: str | int | float | None = None,
    target: str | dict[str, Any] | None = None,
    targets: list[str | dict[str, Any]] | None = None,
    schedule: dict[str, Any] | None = None,
) -> None:
    if not name:
        raise ValueError("policy name must be non-empty")

    policy: dict[str, Any] = {}
    if target is not None and targets is not None:
        raise ValueError("target and targets are mutually exclusive")
    if latency_ms is not None:
        if int(latency_ms) < 0:
            raise ValueError("latency_ms must be >= 0")
        policy["latency_ms"] = int(latency_ms)
    if jitter_ms is not None:
        if int(jitter_ms) < 0:
            raise ValueError("jitter_ms must be >= 0")
        policy["jitter_ms"] = int(jitter_ms)
    if packet_loss is not None:
        policy["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        b = int(burst_loss_len)
        if b < 0:
            raise ValueError("burst_loss_len must be >= 0")
        policy["burst_loss_len"] = b
    if rate is not None:
        policy["bandwidth_bps"] = parse_rate(rate)
    if timeout_ms is not None:
        t = int(timeout_ms)
        if t < 0:
            raise ValueError("timeout_ms must be >= 0")
        policy["timeouts"] = (t, t)
    if connect_timeout_ms is not None or recv_timeout_ms is not None:
        connect_ms = int(connect_timeout_ms) if connect_timeout_ms is not None else 0
        recv_ms = int(recv_timeout_ms) if recv_timeout_ms is not None else 0
        if connect_ms < 0 or recv_ms < 0:
            raise ValueError("connect_timeout_ms and recv_timeout_ms must be >= 0")
        policy["timeouts"] = (connect_ms, recv_ms)
    if uplink is not None:
        if not isinstance(uplink, dict):
            raise ValueError("uplink must be a mapping when provided")
        policy["uplink_profile"] = build_direction_profile(
            latency_ms=uplink.get("latency_ms"),
            jitter_ms=uplink.get("jitter_ms"),
            packet_loss=uplink.get("packet_loss"),
            burst_loss_len=uplink.get("burst_loss_len"),
            rate=uplink.get("rate"),
        )
    if downlink is not None:
        if not isinstance(downlink, dict):
            raise ValueError("downlink must be a mapping when provided")
        policy["downlink_profile"] = build_direction_profile(
            latency_ms=downlink.get("latency_ms"),
            jitter_ms=downlink.get("jitter_ms"),
            packet_loss=downlink.get("packet_loss"),
            burst_loss_len=downlink.get("burst_loss_len"),
            rate=downlink.get("rate"),
        )
    if correlated_loss is not None:
        if not isinstance(correlated_loss, dict):
            raise ValueError("correlated_loss must be a mapping when provided")
        policy["correlated_loss_profile"] = build_correlated_loss_profile(
            p_good_to_bad=correlated_loss.get("p_good_to_bad", 0),
            p_bad_to_good=correlated_loss.get("p_bad_to_good", 0),
            loss_good=correlated_loss.get("loss_good", 0),
            loss_bad=correlated_loss.get("loss_bad", 0),
        )
    if connection_error is not None:
        if not isinstance(connection_error, dict):
            raise ValueError("connection_error must be a mapping when provided")
        policy["connection_error_profile"] = build_connection_error_profile(
            kind=connection_error.get("kind", "reset"),
            prob=connection_error.get("prob", "100%"),
        )
    if half_open is not None:
        if not isinstance(half_open, dict):
            raise ValueError("half_open must be a mapping when provided")
        policy["half_open_profile"] = build_half_open_profile(
            after_bytes=half_open.get("after_bytes", 0),
            error=half_open.get("error", "reset"),
        )
    if packet_duplicate is not None:
        if not isinstance(packet_duplicate, dict):
            raise ValueError("packet_duplicate must be a mapping when provided")
        policy["packet_duplicate_profile"] = build_packet_duplicate_profile(
            prob=packet_duplicate.get("prob", "100%"),
            max_extra=packet_duplicate.get("max_extra", 1),
        )
    if packet_reorder is not None:
        if not isinstance(packet_reorder, dict):
            raise ValueError("packet_reorder must be a mapping when provided")
        policy["packet_reorder_profile"] = build_packet_reorder_profile(
            prob=packet_reorder.get("prob", "100%"),
            max_delay_ms=packet_reorder.get("max_delay_ms", 0),
            window=packet_reorder.get("window", 1),
        )
    dns_profile = build_dns_profile(
        delay_ms=dns_delay_ms,
        timeout_ms=dns_timeout_ms,
        nxdomain=dns_nxdomain,
    )
    if dns_profile:
        policy["dns_profile"] = dns_profile
    if target is not None:
        if isinstance(target, str):
            policy["target_profile"] = build_target_profile(target=target)
        elif isinstance(target, dict):
            policy["target_profile"] = build_target_profile(
                target=target.get("target"),
                host=target.get("host"),
                cidr=target.get("cidr"),
                port=target.get("port"),
                protocol=target.get("protocol"),
            )
        else:
            raise ValueError("target must be a string or mapping when provided")
    if targets is not None:
        if not isinstance(targets, list) or not targets:
            raise ValueError("targets must be a non-empty list when provided")
        built_rules: list[dict[str, int]] = []
        for entry in targets:
            if isinstance(entry, str):
                built_rules.append(build_target_profile(target=entry))
            elif isinstance(entry, dict):
                built_rules.append(
                    build_target_profile(
                        target=entry.get("target"),
                        host=entry.get("host"),
                        cidr=entry.get("cidr"),
                        port=entry.get("port"),
                        protocol=entry.get("protocol"),
                        priority=entry.get("priority"),
                    )
                )
            else:
                raise ValueError("each targets entry must be a string or mapping")
        policy["target_profiles"] = sorted(
            built_rules,
            key=lambda profile: profile.get("priority", 100),
            reverse=True,
        )
    if schedule is not None:
        if not isinstance(schedule, dict):
            raise ValueError("schedule must be a mapping when provided")
        policy["schedule_profile"] = build_schedule_profile(
            kind=schedule.get("kind", ""),
            every_s=schedule.get("every_s"),
            duration_s=schedule.get("duration_s"),
            on_s=schedule.get("on_s"),
            off_s=schedule.get("off_s"),
            ramp_s=schedule.get("ramp_s"),
        )
    with _POLICY_LOCK:
        _POLICY_REGISTRY[name] = policy


def clear_policies() -> None:
    with _POLICY_LOCK:
        _POLICY_REGISTRY.clear()


def list_policies() -> list[str]:
    with _POLICY_LOCK:
        return sorted(_POLICY_REGISTRY.keys())


def get_policy(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        policy = _POLICY_REGISTRY.get(name)
    if policy is None:
        return None
    return copy.deepcopy(policy)


def unregister_policy(name: str) -> bool:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.pop(name, None) is not None


def load_policies(path: str | Path) -> int:
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".json":
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif ext in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except Exception as exc:
            raise ValueError("YAML support requires PyYAML installed") from exc
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    else:
        raise ValueError("Unsupported policy format; use .json, .yaml or .yml")

    if not isinstance(raw, dict):
        raise ValueError("Policy file must contain an object keyed by policy name")

    loaded = 0
    for name, cfg in raw.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            raise ValueError("Each policy entry must be a mapping")
        register_policy(
            name,
            latency_ms=cfg.get("latency_ms"),
            jitter_ms=cfg.get("jitter_ms"),
            packet_loss=cfg.get("packet_loss"),
            burst_loss_len=cfg.get("burst_loss_len"),
            rate=cfg.get("rate"),
            timeout_ms=cfg.get("timeout_ms"),
            connect_timeout_ms=cfg.get("connect_timeout_ms"),
            recv_timeout_ms=cfg.get("recv_timeout_ms"),
            uplink=cfg.get("uplink"),
            downlink=cfg.get("downlink"),
            correlated_loss=cfg.get("correlated_loss"),
            connection_error=cfg.get("connection_error"),
            half_open=cfg.get("half_open"),
            packet_duplicate=cfg.get("packet_duplicate"),
            packet_reorder=cfg.get("packet_reorder"),
            dns_delay_ms=cfg.get("dns_delay_ms"),
            dns_timeout_ms=cfg.get("dns_timeout_ms"),
            dns_nxdomain=cfg.get("dns_nxdomain"),
            target=cfg.get("target"),
            targets=cfg.get("targets"),
            schedule=cfg.get("schedule"),
        )
        loaded += 1
    return loaded


def set_thread_policy(policy_name: str | None) -> None:
    _THREAD_POLICY.set(policy_name)


def get_thread_policy() -> str | None:
    return _THREAD_POLICY.get()
