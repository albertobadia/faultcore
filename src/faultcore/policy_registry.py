import contextvars
import copy
import importlib
import json
import threading
from collections.abc import Callable
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
    build_payload_mutation_profile,
    build_schedule_profile,
    build_session_budget_profile,
    build_target_profile,
    parse_burst_loss,
    parse_duration,
    parse_packet_loss,
    parse_rate,
    parse_seed,
)

_POLICY_REGISTRY: dict[str, dict[str, Any]] = {}
_THREAD_POLICY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "faultcore_thread_policy",
    default=None,
)
_POLICY_LOCK = threading.RLock()


_REGISTERABLE_FIELDS = (
    "seed",
    "latency",
    "jitter",
    "packet_loss",
    "burst_loss",
    "rate",
    "timeout",
    "uplink",
    "downlink",
    "correlated_loss",
    "connection_error",
    "half_open",
    "packet_duplicate",
    "packet_reorder",
    "dns",
    "targets",
    "schedule",
    "session_budget",
    "payload_mutation",
)

_TRANSPORT_EFFECT_POLICY_KEYS = (
    "latency",
    "jitter",
    "packet_loss_ppm",
    "burst_loss",
    "rate",
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
    "payload_mutation_profile",
)

_OPTIONAL_MAPPING_PROFILE_SPECS: tuple[
    tuple[
        str,
        str,
        Callable[..., dict[str, Any]],
        dict[str, Any],
    ],
    ...,
] = (
    (
        "correlated_loss",
        "correlated_loss_profile",
        build_correlated_loss_profile,
        {
            "p_good_to_bad": 0,
            "p_bad_to_good": 0,
            "loss_good": 0,
            "loss_bad": 0,
        },
    ),
    (
        "connection_error",
        "connection_error_profile",
        build_connection_error_profile,
        {
            "kind": "reset",
            "prob": "100%",
        },
    ),
    (
        "half_open",
        "half_open_profile",
        build_half_open_profile,
        {
            "after": "0",
            "error": "reset",
        },
    ),
    (
        "packet_duplicate",
        "packet_duplicate_profile",
        build_packet_duplicate_profile,
        {
            "prob": "100%",
            "max_extra": 1,
        },
    ),
    (
        "packet_reorder",
        "packet_reorder_profile",
        build_packet_reorder_profile,
        {
            "prob": "100%",
            "max_delay": "0ms",
            "window": 1,
        },
    ),
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
        latency=direction.get("latency"),
        jitter=direction.get("jitter"),
        packet_loss=direction.get("packet_loss"),
        burst_loss=direction.get("burst_loss"),
        rate=direction.get("rate"),
    )


def _as_mapping(value: dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:
    return None if value is None else _require_mapping(value, field_name)


def _set_direction_profile(
    policy: dict[str, Any],
    *,
    raw_value: dict[str, Any] | None,
    field_name: str,
    policy_key: str,
) -> None:
    direction_config = _as_mapping(raw_value, field_name)
    if direction_config is not None:
        policy[policy_key] = _build_direction_policy(direction_config)


def _coerce_timeout_pair(timeout: dict[str, Any] | None) -> tuple[int, int]:
    if timeout is None:
        return (0, 0)
    connect = timeout.get("connect")
    recv = timeout.get("recv")
    connect_ms = parse_duration(connect) if connect is not None else 0
    recv_ms = parse_duration(recv) if recv is not None else 0
    return (connect_ms, recv_ms)


def _set_non_negative_optional(
    policy: dict[str, Any],
    *,
    source_value: Any,
    policy_key: str,
    error_message: str,
) -> None:
    if source_value is not None:
        policy[policy_key] = _coerce_non_negative_int(source_value, error_message)


def _build_optional_mapping_profiles(
    *,
    correlated_loss: dict[str, Any] | None,
    connection_error: dict[str, Any] | None,
    half_open: dict[str, Any] | None,
    packet_duplicate: dict[str, Any] | None,
    packet_reorder: dict[str, Any] | None,
    payload_mutation: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    raw_values = {
        "correlated_loss": correlated_loss,
        "connection_error": connection_error,
        "half_open": half_open,
        "packet_duplicate": packet_duplicate,
        "packet_reorder": packet_reorder,
        "payload_mutation": payload_mutation,
    }
    profiles: dict[str, dict[str, Any]] = {}
    for field_name, policy_key, builder, defaults in _OPTIONAL_MAPPING_PROFILE_SPECS:
        config = _as_mapping(raw_values[field_name], field_name)
        if config is None:
            continue
        profiles[policy_key] = builder(**{key: config.get(key, default) for key, default in defaults.items()})

    payload_mutation_config = _as_mapping(raw_values["payload_mutation"], "payload_mutation")
    if payload_mutation_config is not None:
        profiles["payload_mutation_profile"] = build_payload_mutation_profile(
            enabled=bool(payload_mutation_config.get("enabled", False)),
            prob=payload_mutation_config.get("prob", "100%"),
            type=payload_mutation_config.get("type", "none"),
            target=payload_mutation_config.get("target", "both"),
            truncate_size=payload_mutation_config.get("truncate_size"),
            corrupt_count=payload_mutation_config.get("corrupt_count"),
            corrupt_seed=payload_mutation_config.get("corrupt_seed"),
            inject_position=payload_mutation_config.get("inject_position"),
            inject_data=payload_mutation_config.get("inject_data"),
            replace_find=payload_mutation_config.get("replace_find"),
            replace_with=payload_mutation_config.get("replace_with"),
            swap_pos1=payload_mutation_config.get("swap_pos1"),
            swap_pos2=payload_mutation_config.get("swap_pos2"),
            min_size=payload_mutation_config.get("min_size"),
            max_size=payload_mutation_config.get("max_size"),
            every_n_packets=int(payload_mutation_config.get("every_n_packets", 1)),
            dry_run=bool(payload_mutation_config.get("dry_run", False)),
            max_buffer_size=payload_mutation_config.get("max_buffer_size", "64kb"),
        )
    return profiles


def get_policy_for_apply(name: str) -> dict[str, Any] | None:
    with _POLICY_LOCK:
        return _POLICY_REGISTRY.get(name)


def register_policy(
    name: str,
    *,
    seed: str | int | None = None,
    latency: str | None = None,
    jitter: str | None = None,
    packet_loss: str | None = None,
    burst_loss: str | None = None,
    rate: str | None = None,
    timeout: dict[str, Any] | None = None,
    uplink: dict[str, Any] | None = None,
    downlink: dict[str, Any] | None = None,
    correlated_loss: dict[str, Any] | None = None,
    connection_error: dict[str, Any] | None = None,
    half_open: dict[str, Any] | None = None,
    packet_duplicate: dict[str, Any] | None = None,
    packet_reorder: dict[str, Any] | None = None,
    payload_mutation: dict[str, Any] | None = None,
    dns: dict[str, Any] | None = None,
    targets: list[str | dict[str, Any]] | None = None,
    schedule: dict[str, Any] | None = None,
    session_budget: dict[str, Any] | None = None,
) -> None:
    if not name:
        raise ValueError("policy name must be non-empty")

    policy: dict[str, Any] = {}
    if seed is not None:
        policy["seed"] = parse_seed(seed)
    if latency is not None:
        policy["latency"] = parse_duration(latency)
    if jitter is not None:
        policy["jitter"] = parse_duration(jitter)
    if packet_loss is not None:
        policy["packet_loss_ppm"] = parse_packet_loss(packet_loss)
    if burst_loss is not None:
        policy["burst_loss"] = parse_burst_loss(burst_loss)
    if rate is not None:
        policy["rate"] = parse_rate(rate)
    if timeout is not None:
        policy["timeouts"] = _coerce_timeout_pair(timeout)
    _set_direction_profile(
        policy,
        raw_value=uplink,
        field_name="uplink",
        policy_key="uplink_profile",
    )
    _set_direction_profile(
        policy,
        raw_value=downlink,
        field_name="downlink",
        policy_key="downlink_profile",
    )

    policy.update(
        _build_optional_mapping_profiles(
            correlated_loss=correlated_loss,
            connection_error=connection_error,
            half_open=half_open,
            packet_duplicate=packet_duplicate,
            packet_reorder=packet_reorder,
            payload_mutation=payload_mutation,
        )
    )

    if dns is not None:
        dns_profile = build_dns_profile(
            delay=dns.get("delay"),
            timeout=dns.get("timeout"),
            nxdomain=dns.get("nxdomain"),
        )
        if dns_profile:
            policy["dns_profile"] = dns_profile
    if targets is not None:
        if not isinstance(targets, list):
            raise ValueError("targets must be a non-empty list when provided")
        policy["target_profiles"] = _build_target_profiles(targets)

    schedule_config = _as_mapping(schedule, "schedule")
    if schedule_config is not None:
        policy["schedule_profile"] = build_schedule_profile(
            kind=schedule_config.get("kind", ""),
            every=schedule_config.get("every"),
            duration=schedule_config.get("duration"),
            on=schedule_config.get("on"),
            off=schedule_config.get("off"),
            ramp=schedule_config.get("ramp"),
        )

    session_budget_config = _as_mapping(session_budget, "session_budget")
    if session_budget_config is not None:
        policy["session_budget_profile"] = build_session_budget_profile(
            max_tx=session_budget_config.get("max_tx") or session_budget_config.get("max_bytes_tx"),
            max_rx=session_budget_config.get("max_rx") or session_budget_config.get("max_bytes_rx"),
            max_ops=session_budget_config.get("max_ops"),
            max_duration=session_budget_config.get("max_duration"),
            action=session_budget_config.get("action", "drop"),
            budget_timeout=session_budget_config.get("budget_timeout"),
            error=session_budget_config.get("error"),
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
