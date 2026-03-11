from typing import Any


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
    if target_profile.get("port_start") is not None:
        kwargs["port_start"] = target_profile.get("port_start")
    if target_profile.get("port_end") is not None:
        kwargs["port_end"] = target_profile.get("port_end")
    if target_profile.get("hostname") is not None:
        kwargs["hostname"] = target_profile.get("hostname")
    if target_profile.get("sni") is not None:
        kwargs["sni"] = target_profile.get("sni")
    return kwargs


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

    if wrapper._uplink_profile:
        shm.write_uplink(
            tid,
            latency_ms=wrapper._uplink_profile.get("latency_ms"),
            jitter_ms=wrapper._uplink_profile.get("jitter_ms"),
            packet_loss_ppm=wrapper._uplink_profile.get("packet_loss_ppm"),
            burst_loss_len=wrapper._uplink_profile.get("burst_loss_len"),
            bandwidth_bps=wrapper._uplink_profile.get("bandwidth_bps"),
        )

    if wrapper._downlink_profile:
        shm.write_downlink(
            tid,
            latency_ms=wrapper._downlink_profile.get("latency_ms"),
            jitter_ms=wrapper._downlink_profile.get("jitter_ms"),
            packet_loss_ppm=wrapper._downlink_profile.get("packet_loss_ppm"),
            burst_loss_len=wrapper._downlink_profile.get("burst_loss_len"),
            bandwidth_bps=wrapper._downlink_profile.get("bandwidth_bps"),
        )

    if wrapper._correlated_loss_profile:
        shm.write_correlated_loss(
            tid,
            enabled=bool(wrapper._correlated_loss_profile.get("enabled", 0)),
            p_good_to_bad_ppm=wrapper._correlated_loss_profile.get("p_good_to_bad_ppm", 0),
            p_bad_to_good_ppm=wrapper._correlated_loss_profile.get("p_bad_to_good_ppm", 0),
            loss_good_ppm=wrapper._correlated_loss_profile.get("loss_good_ppm", 0),
            loss_bad_ppm=wrapper._correlated_loss_profile.get("loss_bad_ppm", 0),
        )

    if wrapper._connection_error_profile:
        shm.write_connection_error(
            tid,
            kind=wrapper._connection_error_profile.get("kind", 0),
            prob_ppm=wrapper._connection_error_profile.get("prob_ppm", 0),
        )

    if wrapper._half_open_profile:
        shm.write_half_open(
            tid,
            after_bytes=wrapper._half_open_profile.get("after_bytes", 0),
            err_kind=wrapper._half_open_profile.get("err_kind", 0),
        )

    if wrapper._packet_duplicate_profile:
        shm.write_packet_duplicate(
            tid,
            prob_ppm=wrapper._packet_duplicate_profile.get("prob_ppm", 0),
            max_extra=wrapper._packet_duplicate_profile.get("max_extra", 1),
        )

    if wrapper._packet_reorder_profile:
        shm.write_packet_reorder(
            tid,
            prob_ppm=wrapper._packet_reorder_profile.get("prob_ppm", 0),
            max_delay_ns=wrapper._packet_reorder_profile.get("max_delay_ns", 0),
            window=wrapper._packet_reorder_profile.get("window", 1),
        )

    if wrapper._dns_profile:
        shm.write_dns(
            tid,
            delay_ms=wrapper._dns_profile.get("delay_ms"),
            timeout_ms=wrapper._dns_profile.get("timeout_ms"),
            nxdomain_ppm=wrapper._dns_profile.get("nxdomain_ppm"),
        )

    if wrapper._target_profiles:
        shm.write_targets(tid, wrapper._target_profiles)
    elif wrapper._target_profile:
        shm.write_target(tid, **_target_write_kwargs(wrapper._target_profile))

    if wrapper._schedule_profile:
        shm.write_schedule(
            tid,
            schedule_type=wrapper._schedule_profile.get("schedule_type", 0),
            param_a_ns=wrapper._schedule_profile.get("param_a_ns", 0),
            param_b_ns=wrapper._schedule_profile.get("param_b_ns", 0),
            param_c_ns=wrapper._schedule_profile.get("param_c_ns", 0),
            started_monotonic_ns=started_monotonic_ns,
        )

    if wrapper._session_budget_profile:
        shm.write_session_budget(
            tid,
            max_bytes_tx=wrapper._session_budget_profile.get("max_bytes_tx"),
            max_bytes_rx=wrapper._session_budget_profile.get("max_bytes_rx"),
            max_ops=wrapper._session_budget_profile.get("max_ops"),
            max_duration_ms=wrapper._session_budget_profile.get("max_duration_ms"),
            action=wrapper._session_budget_profile.get("action", 0),
            budget_timeout_ms=wrapper._session_budget_profile.get("budget_timeout_ms"),
            error_kind=wrapper._session_budget_profile.get("error_kind"),
        )
