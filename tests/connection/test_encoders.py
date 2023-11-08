import pytest

from nibe.connection.encoders import CoilDataEncoderModbus, CoilDataEncoderNibeGw


@pytest.mark.parametrize(
    "size, raw, raw_value, word_swap",
    [
        ("s8", b"\xfc\x00\x00\x00", -4, None),
        ("s8", b"\xfc\x00", -4, None),
        ("s8", b"\xfc", -4, None),
        ("s8", b"\xff", -1, None),
        ("s8", b"\x7f", 127, None),
        ("s8", b"\x81", -127, None),
        ("s8", b"\x80", None, None),
        ("u8", b"\x01\x00\x00\x00", 1, None),
        ("u8", b"\x01\x00", 1, None),
        ("u8", b"\x01", 1, None),
        ("u8", b"\xff", None, None),
        ("u8", b"\xff\xff", None, None),
        ("s16", b"\x97\x00", 151, None),
        ("s16", b"\x97\x00\x00\x00", 151, None),
        ("s16", b"\x00\x80", None, None),
        ("s16", b"\x00\x80\x00\x00", None, None),
        ("u16", b"\x01\x00\x00\x00", 1, None),
        ("u16", b"\x01\x00", 1, None),
        ("u16", b"\xff\xff\x00\x00", None, None),
        ("u16", b"\xff\xff", None, None),
        ("s32", b"\x00\x002T", 21554, False),
        ("s32", b"2T\x00\x00", 21554, True),
        ("s32", b"\x00\x80\x00\x00", None, False),
        ("s32", b"\x00\x00\x00\x80", None, True),
        ("s32", b"\x00\x00(\x06", 1576, False),
        ("s32", b"(\x06\x00\x00", 1576, True),
    ],
)
def test_nibegw_decode(
    size,
    raw,
    raw_value,
    word_swap,
):
    if word_swap in (True, None):
        assert CoilDataEncoderNibeGw(True).decode_raw_value(size, raw) == raw_value
    if word_swap in (False, None):
        assert CoilDataEncoderNibeGw(False).decode_raw_value(size, raw) == raw_value


@pytest.mark.parametrize(
    "size, raw, raw_value, word_swap",
    [
        ("s8", b"\xfc\x00\x00\x00", -4, None),
        ("s8", b"\xff\x00\x00\x00", -1, None),
        ("s8", b"\x7f\x00\x00\x00", 127, None),
        ("s8", b"\x81\x00\x00\x00", -127, None),
        ("s8", b"\x80\x00\x00\x00", None, None),
        ("u8", b"\x01\x00\x00\x00", 1, None),
        ("u8", b"\xff\x00\x00\x00", 255, None),
        ("u8", b"\xff\x00\x00\x00", None, None),
        ("s16", b"\x97\x00\x00\x00", 151, None),
        ("u16", b"\x01\x00\x00\x00", 1, None),
        ("u16", b"\xff\x00\x00\x00", 255, None),
        ("u16", b"\xb4\x00\x00\x00", 180, None),
        ("s32", b"\x00\x002T", 21554, False),
        ("s32", b"2T\x00\x00", 21554, True),
        ("s32", b"\x00\x80\x00\x00", None, False),
        ("s32", b"\x00\x00\x00\x80", None, True),
        ("s32", b"\x00\x00(\x06", 1576, False),
        ("s32", b"(\x06\x00\x00", 1576, True),
        ("s32", b"\xff\xff\xd8\xf9", -0x628, False),
        ("s32", b"\xd8\xf9\xff\xff", -0x628, True),
    ],
)
def test_nibegw_encode(
    size,
    raw,
    raw_value,
    word_swap,
):
    if word_swap in (True, None):
        assert CoilDataEncoderNibeGw(True).encode_raw_value(size, raw_value) == raw
    if word_swap in (False, None):
        assert CoilDataEncoderNibeGw(False).encode_raw_value(size, raw_value) == raw


@pytest.mark.parametrize(
    "size, raw, raw_value, word_swap",
    [
        ("s8", [0xFFFC], -4, None),
        ("s8", [0xFFFF], -1, None),
        ("s8", [0x007F], 127, None),
        ("s8", [0xFF81], -127, None),
        ("s8", [0xFF80], None, None),
        ("u8", [0x0001], 1, None),
        ("u8", [0x00FF], None, False),
        ("u8", [0xFFFF], None, False),
        ("s16", [0x0097], 151, None),
        ("s16", [0xFFFF], -1, False),
        ("s16", [0x8000], None, None),
        ("s32", [0x0000, 0x5432], 0x5432, False),
        ("s32", [0x5432, 0x0000], 0x5432, True),
        ("s32", [0x0000, 0x5432], 0x5432, False),
        ("s32", [0x5432, 0x0000], 0x5432, True),
        ("s32", [0x8000, 0x0000], None, False),
        ("s32", [0x0000, 0x8000], None, True),
        ("s32", [0xFFFF, 0xF9D8], -0x628, False),
        ("s32", [0xF9D8, 0xFFFF], -0x628, True),
    ],
)
def test_modbus_decode(
    size,
    raw,
    raw_value,
    word_swap,
):
    if word_swap in (True, None):
        assert CoilDataEncoderModbus(True).decode_raw_value(size, raw) == raw_value
    if word_swap in (False, None):
        assert CoilDataEncoderModbus(False).decode_raw_value(size, raw) == raw_value


@pytest.mark.parametrize(
    "size, raw, raw_value, word_swap",
    [
        ("s8", [0xFFFC], -4, False),
        ("s8", [0xFFFF], -1, False),
        ("s8", [0x007F], 127, False),
        ("s8", [0xFF81], -127, False),
        ("s8", [0xFF80], None, False),
        ("u8", [0x0001], 1, None),
        ("u8", [0x00FF], 255, None),
        ("u8", [0x00FF], None, None),
        ("s16", [0x0097], 151, None),
        ("s16", [0xFFFF], -1, None),
        ("s16", [0x8000], None, None),
        ("s32", [0x0000, 0x5432], 0x5432, False),
        ("s32", [0x5432, 0x0000], 0x5432, True),
        ("s32", [0x0000, 0x5432], 0x5432, False),
        ("s32", [0x5432, 0x0000], 0x5432, True),
        ("s32", [0x8000, 0x0000], None, False),
        ("s32", [0x0000, 0x8000], None, True),
        ("s32", [0xFFFF, 0xF9D8], -0x628, False),
        ("s32", [0xF9D8, 0xFFFF], -0x628, True),
    ],
)
def test_modbus_encode(
    size,
    raw,
    raw_value,
    word_swap,
):
    if word_swap in (True, None):
        assert CoilDataEncoderModbus(True).encode_raw_value(size, raw_value) == raw
    if word_swap in (False, None):
        assert CoilDataEncoderModbus(False).encode_raw_value(size, raw_value) == raw
