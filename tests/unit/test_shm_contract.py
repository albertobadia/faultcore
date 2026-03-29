import struct

from faultcore.shm_writer import CONFIG_SIZE

_CONFIG_FORMAT = (
    "<I"
    + ("Q" * 46)
    + "I"
    + "Q"
    + "Q"
    + "16s"
    + "32s"
    + "32s"
    + ("Q" * 9)
    + ("Q" * 8)
    + "64s"
    + "Q"
    + "32s"
    + "Q"
    + "32s"
    + "Q"
    + ("Q" * 7)
    + ("Q" * 8)
)


def test_faultcore_config_binary_layout_is_stable() -> None:
    assert CONFIG_SIZE == 880


def test_faultcore_config_offsets_are_stable() -> None:
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
    struct.pack_into("<Q", blob, 472, 1)
    struct.pack_into("<Q", blob, 480, 1000)
    struct.pack_into("<Q", blob, 488, 2000)
    struct.pack_into("<Q", blob, 496, 3000)
    struct.pack_into("<Q", blob, 504, 4000)
    struct.pack_into("<Q", blob, 512, 2)
    struct.pack_into("<Q", blob, 520, 50)
    struct.pack_into("<Q", blob, 528, 3)
    struct.pack_into("<Q", blob, 536, 123456)
    struct.pack_into("<Q", blob, 544, 1)
    struct.pack_into("<Q", blob, 552, 500000)
    struct.pack_into("<Q", blob, 560, 2)
    struct.pack_into("<Q", blob, 568, 1)
    blob[608:672] = b"abc".ljust(64, b"\x00")

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
    assert struct.unpack_from("<Q", blob, 472)[0] == 1
    assert struct.unpack_from("<Q", blob, 480)[0] == 1000
    assert struct.unpack_from("<Q", blob, 488)[0] == 2000
    assert struct.unpack_from("<Q", blob, 496)[0] == 3000
    assert struct.unpack_from("<Q", blob, 504)[0] == 4000
    assert struct.unpack_from("<Q", blob, 512)[0] == 2
    assert struct.unpack_from("<Q", blob, 520)[0] == 50
    assert struct.unpack_from("<Q", blob, 528)[0] == 3
    assert struct.unpack_from("<Q", blob, 536)[0] == 123456
    assert struct.unpack_from("<Q", blob, 544)[0] == 1
    assert struct.unpack_from("<Q", blob, 552)[0] == 500000
    assert struct.unpack_from("<Q", blob, 560)[0] == 2
    assert struct.unpack_from("<Q", blob, 568)[0] == 1
    assert bytes(blob[608:672]).rstrip(b"\x00") == b"abc"
