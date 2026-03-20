from typing import Any

_DIRECTIONAL_WRITERS = {
    "uplink_profile": "write_uplink",
    "downlink_profile": "write_downlink",
}

_PROFILE_WRITERS = {
    "correlated_loss_profile": (
        "write_correlated_loss",
        {
            "enabled": 0,
            "p_good_to_bad_ppm": 0,
            "p_bad_to_good_ppm": 0,
            "loss_good_ppm": 0,
            "loss_bad_ppm": 0,
        },
    ),
    "connection_error_profile": ("write_connection_error", {"kind": 0, "prob_ppm": 0}),
    "half_open_profile": ("write_half_open", {"after": 0, "err_kind": 0}),
    "packet_duplicate_profile": ("write_packet_duplicate", {"prob_ppm": 0, "max_extra": 1}),
    "packet_reorder_profile": (
        "write_packet_reorder",
        {"prob_ppm": 0, "max_delay_ns": 0, "window": 1},
    ),
    "dns_profile": ("write_dns", {"delay_ms": None, "timeout_ms": None, "nxdomain_ppm": None}),
    "payload_mutation_profile": (
        "write_payload_mutation",
        {
            "enabled": 0,
            "prob_ppm": 0,
            "type": 0,
            "target": 0,
            "truncate_size": 0,
            "corrupt_count": 0,
            "corrupt_seed": 0,
            "inject_position": 0,
            "inject_data": b"",
            "inject_len": 0,
            "replace_find": b"",
            "replace_find_len": 0,
            "replace_with": b"",
            "replace_with_len": 0,
            "swap_pos1": 0,
            "swap_pos2": 0,
            "min_size": 0,
            "max_size": 0,
            "every_n_packets": 1,
            "dry_run": 0,
            "max_buffer_size": 65536,
        },
    ),
}

_SCALAR_WRITERS = {
    "latency": "write_latency",
    "jitter": "write_jitter",
    "packet_loss_ppm": "write_packet_loss",
    "burst_loss": "write_burst_loss",
    "rate": "write_bandwidth",
}

_DIRECTIONAL_FIELDS = ("latency", "jitter", "packet_loss_ppm", "burst_loss", "rate")


def apply_fault_profiles(shm: Any, tid: int, profiles: dict[str, Any], *, started_monotonic_ns: int) -> None:
    if seed := profiles.get("seed"):
        shm.write_policy_seed(tid, seed)

    for field, writer in _SCALAR_WRITERS.items():
        if (value := profiles.get(field)) is not None:
            getattr(shm, writer)(tid, value)

    if timeouts := profiles.get("timeouts"):
        shm.write_timeouts(tid, timeouts.get("connect_ms", 0), timeouts.get("recv_ms", 0))

    for field, writer in _DIRECTIONAL_WRITERS.items():
        profile = profiles.get(field)
        if not profile:
            continue
        values = {name: profile.get(name) for name in _DIRECTIONAL_FIELDS}
        getattr(shm, writer)(tid, **values)

    for field, (writer, defaults) in _PROFILE_WRITERS.items():
        profile = profiles.get(field)
        if not profile:
            continue
        values = {name: profile.get(name, default) for name, default in defaults.items()}
        getattr(shm, writer)(tid, **values)

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
