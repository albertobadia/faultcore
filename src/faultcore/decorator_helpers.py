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
        value = target_profile.get(field)
        if value is not None:
            kwargs[field] = value
    return kwargs


def _write_direction_profile(tid: int, write_method: Any, profile: dict[str, Any]) -> None:
    write_method(tid, **{field: profile.get(field) for field in _DIRECTIONAL_FIELDS})


def _write_profile(
    shm: Any,
    tid: int,
    profile: dict[str, Any] | None,
    writer_name: str,
    defaults: dict[str, Any],
) -> None:
    if not profile:
        return
    getattr(shm, writer_name)(tid, **{field: profile.get(field, default) for field, default in defaults.items()})


def _write_schedule_profile(
    shm: Any,
    tid: int,
    schedule_profile: dict[str, Any],
    *,
    started_monotonic_ns: int,
) -> None:
    shm.write_schedule(
        tid,
        schedule_type=schedule_profile.get("schedule_type", 0),
        param_a_ns=schedule_profile.get("param_a_ns", 0),
        param_b_ns=schedule_profile.get("param_b_ns", 0),
        param_c_ns=schedule_profile.get("param_c_ns", 0),
        started_monotonic_ns=started_monotonic_ns,
    )


def _write_session_budget_profile(shm: Any, tid: int, session_budget_profile: dict[str, Any]) -> None:
    shm.write_session_budget(
        tid,
        max_bytes_tx=session_budget_profile.get("max_bytes_tx"),
        max_bytes_rx=session_budget_profile.get("max_bytes_rx"),
        max_ops=session_budget_profile.get("max_ops"),
        max_duration_ms=session_budget_profile.get("max_duration"),
        action=session_budget_profile.get("action", 0),
        budget_timeout_ms=session_budget_profile.get("budget_timeout"),
        error_kind=session_budget_profile.get("error_kind"),
    )


def _write_scalar_fields(shm: Any, tid: int, profiles: dict[str, Any]) -> None:
    if seed := profiles.get("seed"):
        shm.write_policy_seed(tid, seed)
    for field_name, writer_name in _SCALAR_WRITERS:
        if (value := profiles.get(field_name.lstrip("_"))) is not None:
            getattr(shm, writer_name)(tid, value)


def apply_fault_profiles(shm: Any, tid: int, profiles: dict[str, Any], *, started_monotonic_ns: int) -> None:
    _write_scalar_fields(shm, tid, profiles)

    if timeouts := profiles.get("timeouts"):
        shm.write_timeouts(tid, timeouts.get("connect_ms", 0), timeouts.get("recv_ms", 0))

    for profile_attr, writer_name in _DIRECTIONAL_WRITERS:
        if profile := profiles.get(profile_attr.lstrip("_")):
            _write_direction_profile(tid, getattr(shm, writer_name), profile)

    for profile_attr, writer_name, defaults in _PROFILE_WRITERS:
        if profile := profiles.get(profile_attr.lstrip("_")):
            _write_profile(shm, tid, profile, writer_name, defaults)

    if target_profiles := profiles.get("target_profiles"):
        shm.write_targets(tid, target_profiles)

    if schedule_profile := profiles.get("schedule_profile"):
        _write_schedule_profile(shm, tid, schedule_profile, started_monotonic_ns=started_monotonic_ns)

    if session_budget_profile := profiles.get("session_budget_profile"):
        _write_session_budget_profile(shm, tid, session_budget_profile)
