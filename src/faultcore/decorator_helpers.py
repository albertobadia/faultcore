from typing import Any

_SCALAR_WRITERS = (
    ("_latency", "write_latency"),
    ("_jitter", "write_jitter"),
    ("_packet_loss_ppm", "write_packet_loss"),
    ("_burst_loss", "write_burst_loss"),
    ("_rate", "write_bandwidth"),
)

_DIRECTIONAL_FIELDS = (
    "latency",
    "jitter",
    "packet_loss_ppm",
    "burst_loss",
    "rate",
)

_DIRECTIONAL_WRITERS = (
    ("_uplink_profile", "write_uplink"),
    ("_downlink_profile", "write_downlink"),
)

_TARGET_OPTIONAL_FIELDS = (
    "port_start",
    "port_end",
    "hostname",
    "sni",
)

_PROFILE_WRITERS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "_correlated_loss_profile",
        "write_correlated_loss",
        {
            "enabled": 0,
            "p_good_to_bad_ppm": 0,
            "p_bad_to_good_ppm": 0,
            "loss_good_ppm": 0,
            "loss_bad_ppm": 0,
        },
    ),
    (
        "_connection_error_profile",
        "write_connection_error",
        {
            "kind": 0,
            "prob_ppm": 0,
        },
    ),
    (
        "_half_open_profile",
        "write_half_open",
        {
            "after": 0,
            "err_kind": 0,
        },
    ),
    (
        "_packet_duplicate_profile",
        "write_packet_duplicate",
        {
            "prob_ppm": 0,
            "max_extra": 1,
        },
    ),
    (
        "_packet_reorder_profile",
        "write_packet_reorder",
        {
            "prob_ppm": 0,
            "max_delay_ns": 0,
            "window": 1,
        },
    ),
    (
        "_dns_profile",
        "write_dns",
        {
            "delay_ms": None,
            "timeout_ms": None,
            "nxdomain_ppm": None,
        },
    ),
)


def _target_write_kwargs(target_profile: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "enabled": bool(target_profile.get("enabled", 0)),
        "kind": target_profile.get("kind", 0),
        "ipv4": target_profile.get("ipv4", 0),
        "prefix_len": target_profile.get("prefix_len", 0),
        "port": target_profile.get("port", 0),
        "protocol": target_profile.get("protocol", 0),
        "address_family": target_profile.get("address_family", 0),
        "addr": target_profile.get("addr"),
    }
    for field in _TARGET_OPTIONAL_FIELDS:
        if (value := target_profile.get(field)) is not None:
            kwargs[field] = value
    return kwargs


def _write_profile(
    shm: Any,
    tid: int,
    profile: dict[str, Any] | None,
    writer_name: str,
    defaults: dict[str, Any],
) -> None:
    if not profile:
        return
    params = {field: profile.get(field, default) for field, default in defaults.items()}
    getattr(shm, writer_name)(tid, **params)


def apply_fault_profiles(shm: Any, tid: int, profiles: dict[str, Any], *, started_monotonic_ns: int) -> None:
    if seed := profiles.get("seed"):
        shm.write_policy_seed(tid, seed)

    for field, writer in _SCALAR_WRITERS:
        if (value := profiles.get(field.lstrip("_"))) is not None:
            getattr(shm, writer)(tid, value)

    if timeouts := profiles.get("timeouts"):
        shm.write_timeouts(tid, timeouts.get("connect_ms", 0), timeouts.get("recv_ms", 0))

    for attr, writer in _DIRECTIONAL_WRITERS:
        if profile := profiles.get(attr.lstrip("_")):
            params = {f: profile.get(f) for f in _DIRECTIONAL_FIELDS}
            getattr(shm, writer)(tid, **params)

    for attr, writer, defaults in _PROFILE_WRITERS:
        if profile := profiles.get(attr.lstrip("_")):
            _write_profile(shm, tid, profile, writer, defaults)

    if target_profiles := profiles.get("target_profiles"):
        shm.write_targets(tid, target_profiles)

    if schedule := profiles.get("schedule_profile"):
        shm.write_schedule(
            tid,
            schedule_type=schedule.get("schedule_type", 0),
            param_a_ns=schedule.get("param_a_ns", 0),
            param_b_ns=schedule.get("param_b_ns", 0),
            param_c_ns=schedule.get("param_c_ns", 0),
            started_monotonic_ns=started_monotonic_ns,
        )

    if budget := profiles.get("session_budget_profile"):
        shm.write_session_budget(
            tid,
            max_bytes_tx=budget.get("max_bytes_tx"),
            max_bytes_rx=budget.get("max_bytes_rx"),
            max_ops=budget.get("max_ops"),
            max_duration_ms=budget.get("max_duration"),
            action=budget.get("action", 0),
            budget_timeout_ms=budget.get("budget_timeout"),
            error_kind=budget.get("error_kind"),
        )
