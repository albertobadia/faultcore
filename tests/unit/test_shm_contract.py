import struct

from faultcore.shm_writer import CONFIG_SIZE


def test_faultcore_config_binary_layout_is_stable():
    # magic (u32) + 18x u64 + reserved (u32) = 152 bytes
    fmt = "<I" + ("Q" * 18) + "I"
    assert struct.calcsize(fmt) == CONFIG_SIZE == 152


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
        0,  # reserved
    )
    blob = struct.pack("<I" + ("Q" * 18) + "I", *values)

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
    assert struct.unpack_from("<I", blob, 148)[0] == 0
