import struct

from faultcore.shm_writer import CONFIG_SIZE


def test_faultcore_config_binary_layout_is_stable():
    # legacy fixed layout + SHM vNext targeting extension.
    fmt = "<I" + ("Q" * 46) + "I" + "Q" + "Q" + "16s" + "32s" + "32s"
    assert struct.calcsize(fmt) == CONFIG_SIZE == 472


def test_faultcore_config_offsets_are_stable():
    blob = bytearray(CONFIG_SIZE)

    struct.pack_into("<I", blob, 0, 0xFACC0DE)
    struct.pack_into("<Q", blob, 4, 2)
    struct.pack_into("<Q", blob, 300, 99)
    struct.pack_into("<Q", blob, 308, 100)
    struct.pack_into("<Q", blob, 364, 107)
    struct.pack_into("<I", blob, 372, 0)
    struct.pack_into("<Q", blob, 376, 108)
    struct.pack_into("<Q", blob, 384, 109)
    blob[392:408] = bytes(range(16))
    blob[408:440] = b"host.example.test".ljust(32, b"\x00")
    blob[440:472] = b"sni.example.test".ljust(32, b"\x00")

    assert struct.unpack_from("<I", blob, 0)[0] == 0xFACC0DE
    assert struct.unpack_from("<Q", blob, 4)[0] == 2
    assert struct.unpack_from("<Q", blob, 300)[0] == 99
    assert struct.unpack_from("<Q", blob, 308)[0] == 100
    assert struct.unpack_from("<Q", blob, 364)[0] == 107
    assert struct.unpack_from("<I", blob, 372)[0] == 0
    assert struct.unpack_from("<Q", blob, 376)[0] == 108
    assert struct.unpack_from("<Q", blob, 384)[0] == 109
    assert bytes(blob[392:408]) == bytes(range(16))
    assert bytes(blob[408:440]).rstrip(b"\x00") == b"host.example.test"
    assert bytes(blob[440:472]).rstrip(b"\x00") == b"sni.example.test"
