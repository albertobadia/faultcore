import struct

from faultcore.shm_writer import CONFIG_SIZE


def test_faultcore_config_binary_layout_is_stable():
    # magic (u32) + 6x u64 + reserved (u32) = 56 bytes
    fmt = "<IQQQQQQI"
    assert struct.calcsize(fmt) == CONFIG_SIZE == 56


def test_faultcore_config_offsets_are_stable():
    values = (0xFACC0DE, 2, 10, 20, 30, 40, 50, 0)
    blob = struct.pack("<IQQQQQQI", *values)

    assert struct.unpack_from("<I", blob, 0)[0] == 0xFACC0DE
    assert struct.unpack_from("<Q", blob, 4)[0] == 2
    assert struct.unpack_from("<Q", blob, 12)[0] == 10
    assert struct.unpack_from("<Q", blob, 20)[0] == 20
    assert struct.unpack_from("<Q", blob, 28)[0] == 30
    assert struct.unpack_from("<Q", blob, 36)[0] == 40
    assert struct.unpack_from("<Q", blob, 44)[0] == 50
    assert struct.unpack_from("<I", blob, 52)[0] == 0
