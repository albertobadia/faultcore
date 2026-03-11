from typing import Any


def _target_write_kwargs(target_profile: dict[str, Any]) -> dict[str, Any]:
    port_start = target_profile.get("port_start")
    port_end = target_profile.get("port_end")
    hostname = target_profile.get("hostname")
    sni = target_profile.get("sni")

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
    if port_start is not None:
        kwargs["port_start"] = port_start
    if port_end is not None:
        kwargs["port_end"] = port_end
    if hostname is not None:
        kwargs["hostname"] = hostname
    if sni is not None:
        kwargs["sni"] = sni
    return kwargs


def _write_direction_profile(tid: int, write_method: Any, profile: dict[str, Any]) -> None:
    write_method(
        tid,
        latency_ms=profile.get("latency_ms"),
        jitter_ms=profile.get("jitter_ms"),
        packet_loss_ppm=profile.get("packet_loss_ppm"),
        burst_loss_len=profile.get("burst_loss_len"),
        bandwidth_bps=profile.get("bandwidth_bps"),
    )


def apply_fault_profiles(shm: Any, tid: int, wrapper: Any, *, started_monotonic_ns: int) -> None:
    if wrapper._seed is not None:
        shm.write_policy_seed(tid, wrapper._seed)

    if wrapper._latency_ms:
        shm.write_latency(tid, wrapper._latency_ms)

    if wrapper._jitter_ms:
        shm.write_jitter(tid, wrapper._jitter_ms)

    if wrapper._packet_loss_ppm is not None:
        shm.write_packet_loss(tid, wrapper._packet_loss_ppm)

    if wrapper._burst_loss_len is not None:
        shm.write_burst_loss(tid, wrapper._burst_loss_len)

    if wrapper._bandwidth_bps:
        shm.write_bandwidth(tid, wrapper._bandwidth_bps)

    if wrapper._timeouts:
        connect_ms, recv_ms = wrapper._timeouts
        shm.write_timeouts(tid, connect_ms, recv_ms)

    uplink_profile = wrapper._uplink_profile
    if uplink_profile:
        _write_direction_profile(tid, shm.write_uplink, uplink_profile)

    downlink_profile = wrapper._downlink_profile
    if downlink_profile:
        _write_direction_profile(tid, shm.write_downlink, downlink_profile)

    correlated_loss_profile = wrapper._correlated_loss_profile
    if correlated_loss_profile:
        shm.write_correlated_loss(
            tid,
            enabled=bool(correlated_loss_profile.get("enabled", 0)),
            p_good_to_bad_ppm=correlated_loss_profile.get("p_good_to_bad_ppm", 0),
            p_bad_to_good_ppm=correlated_loss_profile.get("p_bad_to_good_ppm", 0),
            loss_good_ppm=correlated_loss_profile.get("loss_good_ppm", 0),
            loss_bad_ppm=correlated_loss_profile.get("loss_bad_ppm", 0),
        )

    connection_error_profile = wrapper._connection_error_profile
    if connection_error_profile:
        shm.write_connection_error(
            tid,
            kind=connection_error_profile.get("kind", 0),
            prob_ppm=connection_error_profile.get("prob_ppm", 0),
        )

    half_open_profile = wrapper._half_open_profile
    if half_open_profile:
        shm.write_half_open(
            tid,
            after_bytes=half_open_profile.get("after_bytes", 0),
            err_kind=half_open_profile.get("err_kind", 0),
        )

    packet_duplicate_profile = wrapper._packet_duplicate_profile
    if packet_duplicate_profile:
        shm.write_packet_duplicate(
            tid,
            prob_ppm=packet_duplicate_profile.get("prob_ppm", 0),
            max_extra=packet_duplicate_profile.get("max_extra", 1),
        )

    packet_reorder_profile = wrapper._packet_reorder_profile
    if packet_reorder_profile:
        shm.write_packet_reorder(
            tid,
            prob_ppm=packet_reorder_profile.get("prob_ppm", 0),
            max_delay_ns=packet_reorder_profile.get("max_delay_ns", 0),
            window=packet_reorder_profile.get("window", 1),
        )

    dns_profile = wrapper._dns_profile
    if dns_profile:
        shm.write_dns(
            tid,
            delay_ms=dns_profile.get("delay_ms"),
            timeout_ms=dns_profile.get("timeout_ms"),
            nxdomain_ppm=dns_profile.get("nxdomain_ppm"),
        )

    if wrapper._target_profiles:
        shm.write_targets(tid, wrapper._target_profiles)
    elif wrapper._target_profile:
        shm.write_target(tid, **_target_write_kwargs(wrapper._target_profile))

    schedule_profile = wrapper._schedule_profile
    if schedule_profile:
        shm.write_schedule(
            tid,
            schedule_type=schedule_profile.get("schedule_type", 0),
            param_a_ns=schedule_profile.get("param_a_ns", 0),
            param_b_ns=schedule_profile.get("param_b_ns", 0),
            param_c_ns=schedule_profile.get("param_c_ns", 0),
            started_monotonic_ns=started_monotonic_ns,
        )

    session_budget_profile = wrapper._session_budget_profile
    if session_budget_profile:
        shm.write_session_budget(
            tid,
            max_bytes_tx=session_budget_profile.get("max_bytes_tx"),
            max_bytes_rx=session_budget_profile.get("max_bytes_rx"),
            max_ops=session_budget_profile.get("max_ops"),
            max_duration_ms=session_budget_profile.get("max_duration_ms"),
            action=session_budget_profile.get("action", 0),
            budget_timeout_ms=session_budget_profile.get("budget_timeout_ms"),
            error_kind=session_budget_profile.get("error_kind"),
        )
