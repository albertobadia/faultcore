import contextvars
import copy
import importlib
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
    build_session_budget_profile,
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


_REGISTERABLE_FIELDS = (
    "seed",
    "latency_ms",
    "jitter_ms",
    "packet_loss",
    "burst_loss_len",
    "rate",
    "connect_timeout_ms",
    "recv_timeout_ms",
    "uplink",
    "downlink",
    "correlated_loss",
    "connection_error",
    "half_open",
    "packet_duplicate",
    "packet_reorder",
    "dns_delay_ms",
    "dns_timeout_ms",
    "dns_nxdomain",
    "target",
    "targets",
    "schedule",
    "session_budget",
)

_TRANSPORT_EFFECT_POLICY_KEYS = (
    "latency_ms",
    "jitter_ms",
    "packet_loss_ppm",
    "burst_loss_len",
    "bandwidth_bps",
    "timeouts",
    "uplink_profile",
    "downlink_profile",
    "correlated_loss_profile",
    "connection_error_profile",
    "half_open_profile",
    "packet_duplicate_profile",
    "packet_reorder_profile",
    "schedule_profile",
    "session_budget_profile",
)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a mapping when provided")
    return value


def _coerce_non_negative_int(value: Any, error_message: str) -> int:
    coerced = int(value)
    if coerced < 0:
        raise ValueError(error_message)
    return coerced


def _build_target_rule_from_mapping(target: dict[str, Any]) -> dict[str, Any]:
    return build_target_profile(
        target=target.get("target"),
        host=target.get("host"),
        cidr=target.get("cidr"),
        hostname=target.get("hostname"),
        sni=target.get("sni"),
        port=target.get("port"),
        port_start=target.get("port_start"),
        port_end=target.get("port_end"),
        protocol=target.get("protocol"),
        priority=target.get("priority"),
    )


def _build_target_rule(target: str | dict[str, Any], *, include_priority: bool) -> dict[str, Any]:
    if isinstance(target, str):
        rule = build_target_profile(target=target)
    elif isinstance(target, dict):
        rule = _build_target_rule_from_mapping(target)
    else:
        raise ValueError("target must be a string or mapping when provided")

    if not include_priority:
        rule.pop("priority", None)
    return rule


def _build_single_target_profile(target: str | dict[str, Any]) -> dict[str, Any]:
    return _build_target_rule(target, include_priority=False)


def _build_target_profiles(targets: list[str | dict[str, Any]]) -> list[dict[str, Any]]:
    if not targets:
        raise ValueError("targets must be a non-empty list when provided")

    if not all(isinstance(entry, (str, dict)) for entry in targets):
        raise ValueError("each targets entry must be a string or mapping")

    return sorted(
        (_build_target_rule(entry, include_priority=True) for entry in targets),
        key=lambda profile: profile.get("priority", 100),
        reverse=True,
    )


def _rule_is_dns_observable(rule: dict[str, Any]) -> bool:
    return (
        rule.get("hostname") is not None
        and int(rule.get("protocol", 0)) == 0
        and int(rule.get("port", 0)) == 0
        and "port_start" not in rule
        and "port_end" not in rule
    )


def _rule_is_transport_observable(rule: dict[str, Any]) -> bool:
    return rule.get("hostname") is not None or rule.get("sni") is not None or int(rule.get("kind", 0)) in (1, 2)


def _iter_policy_target_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [policy["target_profile"]] if isinstance(policy.get("target_profile"), dict) else []
    multiple = policy.get("target_profiles")
    if isinstance(multiple, list):
        rules.extend(rule for rule in multiple if isinstance(rule, dict))
    return rules


def _validate_target_observability(policy: dict[str, Any]) -> None:
    rules = _iter_policy_target_rules(policy)
    if not rules:
        return

    has_dns_effects = "dns_profile" in policy
    has_transport_effects = any(key in policy for key in _TRANSPORT_EFFECT_POLICY_KEYS)
    if not has_dns_effects and not has_transport_effects:
        return

    has_dns_observable_rule = any(_rule_is_dns_observable(rule) for rule in rules)
    has_transport_observable_rule = any(_rule_is_transport_observable(rule) for rule in rules)

    if has_dns_effects and not has_dns_observable_rule:
        raise ValueError(
            "targets do not expose DNS-observable selectors for dns_* effects; "
            "use hostname-only rules (without port/protocol filters)"
        )
    if has_transport_effects and not has_transport_observable_rule:
        raise ValueError(
            "targets do not expose transport-observable selectors for non-dns effects; "
            "use host/cidr, hostname, or sni rules"
        )


def _build_direction_policy(direction: dict[str, Any]) -> dict[str, Any]:
    return build_direction_profile(
        latency_ms=direction.get("latency_ms"),
        jitter_ms=direction.get("jitter_ms"),
        packet_loss=direction.get("packet_loss"),
        burst_loss_len=direction.get("burst_loss_len"),
        rate=direction.get("rate"),
    )


def _coerce_timeout_pair(
    connect_timeout_ms: int | None,
    recv_timeout_ms: int | None,
) -> tuple[int, int]:
    error_message = "connect_timeout_ms and recv_timeout_ms must be >= 0"
    connect_ms = _coerce_non_negative_int(connect_timeout_ms, error_message) if connect_timeout_ms is not None else 0
    recv_ms = _coerce_non_negative_int(recv_timeout_ms, error_message) if recv_timeout_ms is not None else 0
    return connect_ms, recv_ms


def get_policy_for_apply(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.get(name)


def register_policy(
    name: str,
    *,
    seed: int | None = None,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
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
    session_budget: dict[str, Any] | None = None,
) -> None:
    if not name:
        raise ValueError("policy name must be non-empty")

    policy: dict[str, Any] = {}
    if target is not None and targets is not None:
        raise ValueError("target and targets are mutually exclusive")
    if seed is not None:
        policy["seed"] = _coerce_non_negative_int(seed, "seed must be >= 0")
    if latency_ms is not None:
        policy["latency_ms"] = _coerce_non_negative_int(latency_ms, "latency_ms must be >= 0")
    if jitter_ms is not None:
        policy["jitter_ms"] = _coerce_non_negative_int(jitter_ms, "jitter_ms must be >= 0")
    if packet_loss is not None:
        policy["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss_len is not None:
        policy["burst_loss_len"] = _coerce_non_negative_int(
            burst_loss_len,
            "burst_loss_len must be >= 0",
        )
    if rate is not None:
        policy["bandwidth_bps"] = parse_rate(rate)
    if connect_timeout_ms is not None or recv_timeout_ms is not None:
        policy["timeouts"] = _coerce_timeout_pair(connect_timeout_ms, recv_timeout_ms)
    if uplink is not None:
        policy["uplink_profile"] = _build_direction_policy(_require_mapping(uplink, "uplink"))
    if downlink is not None:
        policy["downlink_profile"] = _build_direction_policy(_require_mapping(downlink, "downlink"))
    if correlated_loss is not None:
        correlated_loss_mapping = _require_mapping(correlated_loss, "correlated_loss")
        policy["correlated_loss_profile"] = build_correlated_loss_profile(
            p_good_to_bad=correlated_loss_mapping.get("p_good_to_bad", 0),
            p_bad_to_good=correlated_loss_mapping.get("p_bad_to_good", 0),
            loss_good=correlated_loss_mapping.get("loss_good", 0),
            loss_bad=correlated_loss_mapping.get("loss_bad", 0),
        )
    if connection_error is not None:
        connection_error_mapping = _require_mapping(connection_error, "connection_error")
        policy["connection_error_profile"] = build_connection_error_profile(
            kind=connection_error_mapping.get("kind", "reset"),
            prob=connection_error_mapping.get("prob", "100%"),
        )
    if half_open is not None:
        half_open_mapping = _require_mapping(half_open, "half_open")
        policy["half_open_profile"] = build_half_open_profile(
            after_bytes=half_open_mapping.get("after_bytes", 0),
            error=half_open_mapping.get("error", "reset"),
        )
    if packet_duplicate is not None:
        packet_duplicate_mapping = _require_mapping(packet_duplicate, "packet_duplicate")
        policy["packet_duplicate_profile"] = build_packet_duplicate_profile(
            prob=packet_duplicate_mapping.get("prob", "100%"),
            max_extra=packet_duplicate_mapping.get("max_extra", 1),
        )
    if packet_reorder is not None:
        packet_reorder_mapping = _require_mapping(packet_reorder, "packet_reorder")
        policy["packet_reorder_profile"] = build_packet_reorder_profile(
            prob=packet_reorder_mapping.get("prob", "100%"),
            max_delay_ms=packet_reorder_mapping.get("max_delay_ms", 0),
            window=packet_reorder_mapping.get("window", 1),
        )
    dns_profile = build_dns_profile(
        delay_ms=dns_delay_ms,
        timeout_ms=dns_timeout_ms,
        nxdomain=dns_nxdomain,
    )
    if dns_profile:
        policy["dns_profile"] = dns_profile
    if target is not None:
        policy["target_profile"] = _build_single_target_profile(target)
    if targets is not None:
        if not isinstance(targets, list):
            raise ValueError("targets must be a non-empty list when provided")
        policy["target_profiles"] = _build_target_profiles(targets)
    if schedule is not None:
        schedule_mapping = _require_mapping(schedule, "schedule")
        policy["schedule_profile"] = build_schedule_profile(
            kind=schedule_mapping.get("kind", ""),
            every_s=schedule_mapping.get("every_s"),
            duration_s=schedule_mapping.get("duration_s"),
            on_s=schedule_mapping.get("on_s"),
            off_s=schedule_mapping.get("off_s"),
            ramp_s=schedule_mapping.get("ramp_s"),
        )
    if session_budget is not None:
        session_budget_mapping = _require_mapping(session_budget, "session_budget")
        policy["session_budget_profile"] = build_session_budget_profile(
            max_bytes_tx=session_budget_mapping.get("max_bytes_tx"),
            max_bytes_rx=session_budget_mapping.get("max_bytes_rx"),
            max_ops=session_budget_mapping.get("max_ops"),
            max_duration_ms=session_budget_mapping.get("max_duration_ms"),
            action=session_budget_mapping.get("action", "drop"),
            budget_timeout_ms=session_budget_mapping.get("budget_timeout_ms"),
            error=session_budget_mapping.get("error"),
        )
    _validate_target_observability(policy)
    with _POLICY_LOCK:
        _POLICY_REGISTRY[name] = policy


def clear_policies() -> None:
    with _POLICY_LOCK:
        _POLICY_REGISTRY.clear()


def list_policies() -> list[str]:
    with _POLICY_LOCK:
        return sorted(_POLICY_REGISTRY)


def get_policy(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        policy = _POLICY_REGISTRY.get(name)
    return copy.deepcopy(policy) if policy is not None else None


def unregister_policy(name: str) -> bool:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.pop(name, None) is not None


def load_policies(path: str | Path) -> int:
    path_obj = Path(path)
    extension = path_obj.suffix.lower()

    if extension == ".json":
        with path_obj.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif extension in {".yaml", ".yml"}:
        try:
            yaml_module = importlib.import_module("yaml")
        except Exception as exc:
            raise ValueError("YAML support requires PyYAML installed") from exc
        with path_obj.open("r", encoding="utf-8") as f:
            raw = yaml_module.safe_load(f)
    else:
        raise ValueError("Unsupported policy format; use .json, .yaml or .yml")

    if not isinstance(raw, dict):
        raise ValueError("Policy file must contain an object keyed by policy name")

    loaded = 0
    for name, cfg in raw.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            raise ValueError("Each policy entry must be a mapping")
        policy_kwargs = {field: cfg.get(field) for field in _REGISTERABLE_FIELDS}
        register_policy(name, **policy_kwargs)
        loaded += 1
    return loaded


def set_thread_policy(policy_name: str | None) -> None:
    _THREAD_POLICY.set(policy_name)


def get_thread_policy() -> str | None:
    return _THREAD_POLICY.get()
