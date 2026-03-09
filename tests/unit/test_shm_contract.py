import struct

from faultcore.shm_writer import CONFIG_SIZE


def test_faultcore_config_binary_layout_is_stable():
    # magic (u32) + 41x u64 + reserved (u32) = 336 bytes
    fmt = "<I" + ("Q" * 41) + "I"
    assert struct.calcsize(fmt) == CONFIG_SIZE == 336


def test_faultcore_config_offsets_are_stable():
    values = (
        0xFACC0DE,  # magic
        2,  # version
        10,  # latency_ns
        11,  # jitter_ns
        20,  # packet_loss_ppm
        21,  # burst_loss_len
        30,  # bandwidth_bps
        40,  # connect_timeout_ms
        50,  # recv_timeout_ms
        60,  # uplink_latency_ns
        61,  # uplink_jitter_ns
        62,  # uplink_packet_loss_ppm
        63,  # uplink_burst_loss_len
        64,  # uplink_bandwidth_bps
        70,  # downlink_latency_ns
        71,  # downlink_jitter_ns
        72,  # downlink_packet_loss_ppm
        73,  # downlink_burst_loss_len
        74,  # downlink_bandwidth_bps
        80,  # ge_enabled
        81,  # ge_p_good_to_bad_ppm
        82,  # ge_p_bad_to_good_ppm
        83,  # ge_loss_good_ppm
        84,  # ge_loss_bad_ppm
        85,  # conn_err_kind
        86,  # conn_err_prob_ppm
        87,  # half_open_after_bytes
        88,  # half_open_err_kind
        89,  # dup_prob_ppm
        90,  # dup_max_extra
        91,  # reorder_prob_ppm
        92,  # reorder_max_delay_ns
        93,  # reorder_window
        94,  # dns_delay_ns
        95,  # dns_timeout_ms
        96,  # dns_nxdomain_ppm
        97,  # target_enabled
        98,  # target_kind
        99,  # target_ipv4
        100,  # target_prefix_len
        101,  # target_port
        102,  # target_protocol
        0,  # reserved
    )
    blob = struct.pack("<I" + ("Q" * 41) + "I", *values)

    assert struct.unpack_from("<I", blob, 0)[0] == 0xFACC0DE
    assert struct.unpack_from("<Q", blob, 4)[0] == 2
    assert struct.unpack_from("<Q", blob, 12)[0] == 10
    assert struct.unpack_from("<Q", blob, 20)[0] == 11
    assert struct.unpack_from("<Q", blob, 28)[0] == 20
    assert struct.unpack_from("<Q", blob, 36)[0] == 21
    assert struct.unpack_from("<Q", blob, 44)[0] == 30
    assert struct.unpack_from("<Q", blob, 52)[0] == 40
    assert struct.unpack_from("<Q", blob, 60)[0] == 50
    assert struct.unpack_from("<Q", blob, 68)[0] == 60
    assert struct.unpack_from("<Q", blob, 76)[0] == 61
    assert struct.unpack_from("<Q", blob, 84)[0] == 62
    assert struct.unpack_from("<Q", blob, 92)[0] == 63
    assert struct.unpack_from("<Q", blob, 100)[0] == 64
    assert struct.unpack_from("<Q", blob, 108)[0] == 70
    assert struct.unpack_from("<Q", blob, 116)[0] == 71
    assert struct.unpack_from("<Q", blob, 124)[0] == 72
    assert struct.unpack_from("<Q", blob, 132)[0] == 73
    assert struct.unpack_from("<Q", blob, 140)[0] == 74
    assert struct.unpack_from("<Q", blob, 148)[0] == 80
    assert struct.unpack_from("<Q", blob, 156)[0] == 81
    assert struct.unpack_from("<Q", blob, 164)[0] == 82
    assert struct.unpack_from("<Q", blob, 172)[0] == 83
    assert struct.unpack_from("<Q", blob, 180)[0] == 84
    assert struct.unpack_from("<Q", blob, 188)[0] == 85
    assert struct.unpack_from("<Q", blob, 196)[0] == 86
    assert struct.unpack_from("<Q", blob, 204)[0] == 87
    assert struct.unpack_from("<Q", blob, 212)[0] == 88
    assert struct.unpack_from("<Q", blob, 220)[0] == 89
    assert struct.unpack_from("<Q", blob, 228)[0] == 90
    assert struct.unpack_from("<Q", blob, 236)[0] == 91
    assert struct.unpack_from("<Q", blob, 244)[0] == 92
    assert struct.unpack_from("<Q", blob, 252)[0] == 93
    assert struct.unpack_from("<Q", blob, 260)[0] == 94
    assert struct.unpack_from("<Q", blob, 268)[0] == 95
    assert struct.unpack_from("<Q", blob, 276)[0] == 96
    assert struct.unpack_from("<Q", blob, 284)[0] == 97
    assert struct.unpack_from("<Q", blob, 292)[0] == 98
    assert struct.unpack_from("<Q", blob, 300)[0] == 99
    assert struct.unpack_from("<Q", blob, 308)[0] == 100
    assert struct.unpack_from("<Q", blob, 316)[0] == 101
    assert struct.unpack_from("<Q", blob, 324)[0] == 102
    assert struct.unpack_from("<I", blob, 332)[0] == 0
