from contextlib import nullcontext

import pytest

from nibe.coil import Coil, CoilData
from nibe.connection.nibegw import CoilDataEncoder
from nibe.exceptions import DecodeException, EncodeException, ValidationError
from nibe.parsers import swapwords


def test_swapwords():
    assert swapwords(b"abcd") == b"cdab"
    assert swapwords(b"ab") == b"ab"


def test_create():
    coil = Coil(123, "test_name", "test_title", "u8", unknown="some other")

    assert coil.address == 123
    assert coil.name == "test_name"
    assert coil.title == "test_title"
    assert coil.other["unknown"] == "some other"


@pytest.fixture
def encoder():
    return CoilDataEncoder()


@pytest.fixture
def encoder_word_swap_false():
    return CoilDataEncoder(word_swap=False)


@pytest.fixture
def encoder_word_swap():
    return CoilDataEncoder(word_swap=True)


# Signed 8-bit
@pytest.fixture
def coil_signed_s8():
    return Coil(48739, "cool-offset-s1-48739", "Cool offset S1", "s8")


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\xfc\x00\x00\x00", -4),
        (b"\xfc\x00", -4),
        (b"\xfc", -4),
        (b"\xff", -1),
        (b"\x7f", 127),
        (b"\x81", -127),
        (b"\x80", None),
    ],
)
def test_signed_s8_decode(
    raw_value, value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s8: Coil
):
    assert encoder_word_swap_false.decode(coil_signed_s8, raw_value) == CoilData(
        coil_signed_s8, value
    )


def test_signed_s8_encode(
    encoder_word_swap_false: CoilDataEncoder, coil_signed_s8: Coil
):
    coil_data = CoilData(coil_signed_s8, -4)
    assert encoder_word_swap_false.encode(coil_data) == b"\xfc\x00\x00\x00"


@pytest.mark.parametrize("value", [(128), (None), (-129)])
def test_signed_s8_encode_exceptions(
    value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s8: Coil
):
    with pytest.raises(EncodeException):
        coil_data = CoilData(coil_signed_s8, value)
        encoder_word_swap_false.encode(coil_data)


# Unsigned 8-bit
@pytest.fixture
def coil_unsigned_u8():
    return Coil(123, "test", "test", "u8")


def test_validate_error(coil_unsigned_u8: Coil):
    coil_data = CoilData(coil_unsigned_u8, "fail")
    with pytest.raises(ValidationError):
        coil_data.validate()


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x01\x00\x00\x00", 1),
        (b"\x01\x00", 1),
        (b"\x01", 1),
        (b"\xff", None),
        (b"\xff\xff", None),
    ],
)
def test_unsigned_s8_decode(
    raw_value, value, encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8: Coil
):
    assert encoder_word_swap_false.decode(coil_unsigned_u8, raw_value) == CoilData(
        coil_unsigned_u8, value
    )


@pytest.mark.parametrize(
    "value, raw_value",
    [
        (1, b"\x01\x00\x00\x00"),
        (255, b"\xff\x00\x00\x00"),
    ],
)
def test_unsigned_s8_encode(
    value, raw_value, encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8: Coil
):
    coil_data = CoilData(coil_unsigned_u8, value)
    assert encoder_word_swap_false.encode(coil_data) == raw_value


def test_unsigned_s8_encode_exception(
    encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8: Coil
):
    with pytest.raises(EncodeException):
        coil_data = CoilData(coil_unsigned_u8, 256)
        encoder_word_swap_false.encode(coil_data)


# Unsigned 8-bit with word swap
@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x01\x00\x00\x00", 1),
        (b"\x01\x00", 1),
        (b"\x01", 1),
        (b"\xff", None),
        (b"\xff\xff", None),
    ],
)
def test_unsigned_s8_decode_word_swap(
    raw_value, value, encoder_word_swap: CoilDataEncoder, coil_unsigned_u8: Coil
):
    assert encoder_word_swap.decode(coil_unsigned_u8, raw_value) == CoilData(
        coil_unsigned_u8, value
    )


@pytest.mark.parametrize(
    "value, raw_value",
    [
        (1, b"\x01\x00\x00\x00"),
        (255, b"\xff\x00\x00\x00"),
    ],
)
def test_unsigned_s8_encode_word_swap(
    value, raw_value, encoder_word_swap: CoilDataEncoder, coil_unsigned_u8: Coil
):
    coil_data = CoilData(coil_unsigned_u8, value)
    assert encoder_word_swap.encode(coil_data) == raw_value


def test_unsigned_s8_encode_exception_word_swap(
    encoder_word_swap: CoilDataEncoder, coil_unsigned_u8: Coil
):
    with pytest.raises(EncodeException):
        coil_data = CoilData(coil_unsigned_u8, 256)
        encoder_word_swap.encode(coil_data)


# Signed 16-bit
@pytest.fixture
def coil_signed_s16():
    return Coil(123, "test", "test", "s16", factor=10, min=50, max=300)


def test_signed_s16_attributes(coil_signed_s16: Coil):
    assert coil_signed_s16.min == 5.0
    assert coil_signed_s16.max == 30.0

    assert coil_signed_s16.raw_min == 50
    assert coil_signed_s16.raw_max == 300

    assert not coil_signed_s16.is_boolean
    assert not coil_signed_s16.is_writable


@pytest.mark.parametrize(
    "value, expected_raises",
    [
        (5.0, nullcontext()),
        (30.0, nullcontext()),
        (4.9, pytest.raises(ValidationError)),
        (30.1, pytest.raises(ValidationError)),
    ],
)
def test_signed_s16_is_valid(value, expected_raises, coil_signed_s16: Coil):
    coil_data = CoilData(coil_signed_s16, value)
    with expected_raises:
        coil_data.validate()


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x97\x00", 15.1),
        (b"\x00\x80", None),
    ],
)
def test_signed_s16_decode(
    raw_value, value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s16: Coil
):
    assert encoder_word_swap_false.decode(coil_signed_s16, raw_value) == CoilData(
        coil_signed_s16, value
    )


@pytest.mark.parametrize(
    "raw_value",
    [
        (b"\x31\x00"),
        (b"\x2d\x10"),
    ],
)
def test_signed_s16_decode_exception(
    raw_value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s16: Coil
):
    with pytest.raises(DecodeException):
        encoder_word_swap_false.decode(coil_signed_s16, raw_value)


def test_signed_s16_encode(
    encoder_word_swap_false: CoilDataEncoder, coil_signed_s16: Coil
):
    coil_data = CoilData(coil_signed_s16, 15.1)
    assert encoder_word_swap_false.encode(coil_data) == b"\x97\x00\x00\x00"


@pytest.mark.parametrize(
    "value",
    [
        (4),
        (30.1),
    ],
)
def test_signed_s16_encode_exception(
    value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s16: Coil
):
    with pytest.raises(EncodeException):
        coil_data = CoilData(coil_signed_s16, value)
        encoder_word_swap_false.encode(coil_data)


# Unsigned 16-bit
@pytest.fixture
def coil_unsigned_u16():
    return Coil(
        123,
        "compressor-frequency-actual-43136",
        "Compressor Frequency, Actual",
        "u16",
        factor=10,
    )


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x01\x00\x00\x00", 0.1),
        (b"\x01\x00", 0.1),
        (b"\xff\xff", None),
    ],
)
def test_unsigned_u16_decode(
    raw_value, value, encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u16: Coil
):
    assert encoder_word_swap_false.decode(coil_unsigned_u16, raw_value) == CoilData(
        coil_unsigned_u16, value
    )


@pytest.mark.parametrize(
    "value, raw_value",
    [
        (0.1, b"\x01\x00\x00\x00"),
        (25.5, b"\xff\x00\x00\x00"),
    ],
)
def test_unsigned_u16_encode(
    value, raw_value, encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u16: Coil
):
    coil_data = CoilData(coil_unsigned_u16, value)
    assert encoder_word_swap_false.encode(coil_data) == raw_value


# Unsigned 16-bit word swap
@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x01\x00\x00\x00", 0.1),
        (b"\x01\x00", 0.1),
        (b"\xff\xff", None),
    ],
)
def test_unsigned_u16_word_swap_decode(
    raw_value, value, encoder_word_swap: CoilDataEncoder, coil_unsigned_u16: Coil
):
    assert encoder_word_swap.decode(coil_unsigned_u16, raw_value) == CoilData(
        coil_unsigned_u16, value
    )


@pytest.mark.parametrize(
    "value, raw_value",
    [
        (0.1, b"\x01\x00\x00\x00"),
        (25.5, b"\xff\x00\x00\x00"),
    ],
)
def test_unsigned_u16_word_swap_encode(
    value, raw_value, encoder_word_swap: CoilDataEncoder, coil_unsigned_u16: Coil
):
    coil_data = CoilData(coil_unsigned_u16, value)
    assert encoder_word_swap.encode(coil_data) == raw_value


# Signed 32-bit
@pytest.fixture
def coil_signed_s32():
    return Coil(
        43420,
        "tot-op-time-compr-eb100-ep14-43420",
        "Total compressorer operation time",
        "s32",
    )


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x00\x002T", 21554),
        (b"\x00\x80\x00\x00", None),
    ],
)
def test_signed_s32_decode(
    raw_value, value, encoder_word_swap_false: CoilDataEncoder, coil_signed_s32: Coil
):
    assert encoder_word_swap_false.decode(coil_signed_s32, raw_value) == CoilData(
        coil_signed_s32, value
    )


def test_signed_s32_encode(
    encoder_word_swap_false: CoilDataEncoder, coil_signed_s32: Coil
):
    coil_data = CoilData(coil_signed_s32, 21554)
    assert encoder_word_swap_false.encode(coil_data) == b"\x00\x002T"


# Signed 32-bit word swap
@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"(\x06\x00\x00", 1576),
        (b"\x00\x00\x00\x80", None),
    ],
)
def test_signed_s32_word_swap_decode(
    raw_value, value, encoder_word_swap: CoilDataEncoder, coil_signed_s32: Coil
):
    assert encoder_word_swap.decode(coil_signed_s32, raw_value) == CoilData(
        coil_signed_s32, value
    )


def test_signed_s32_word_swap_encode(
    encoder_word_swap: CoilDataEncoder, coil_signed_s32: Coil
):
    coil_data = CoilData(coil_signed_s32, 1576)
    assert encoder_word_swap.encode(coil_data) == b"(\x06\x00\x00"


# Unsigned 8-bit with mapping
@pytest.fixture
def coil_unsigned_u8_mapping():
    return Coil(
        123,
        "prio-43086",
        "Prio",
        "u8",
        factor=1,
        mappings={
            "10": "Off",
            "20": "Hot Water",
            "30": "Heat",
            "40": "Pool",
            "41": "Pool 2",
            "50": "Transfer",
            "60": "Cooling",
        },
    )


@pytest.mark.parametrize(
    "raw_value, value",
    [
        (b"\x0a", "OFF"),
        (b"\xff\xff", None),
    ],
)
def test_unsigned_u8_mapping_decode(
    raw_value,
    value,
    encoder_word_swap_false: CoilDataEncoder,
    coil_unsigned_u8_mapping: Coil,
):
    assert encoder_word_swap_false.decode(
        coil_unsigned_u8_mapping, raw_value
    ) == CoilData(coil_unsigned_u8_mapping, value)


def test_unsigned_u8_mapping_decode_exception(
    encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8_mapping: Coil
):
    with pytest.raises(DecodeException):
        encoder_word_swap_false.decode(coil_unsigned_u8_mapping, b"\x00")


@pytest.mark.parametrize(
    "value, raw_value",
    [
        ("OFF", b"\x0a\x00\x00\x00"),
        ("off", b"\x0a\x00\x00\x00"),
        ("Hot Water", b"\x14\x00\x00\x00"),
    ],
)
def test_unsigned_u8_mapping_encode(
    value,
    raw_value,
    encoder_word_swap_false: CoilDataEncoder,
    coil_unsigned_u8_mapping: Coil,
):
    coil_data = CoilData(coil_unsigned_u8_mapping, value)
    assert encoder_word_swap_false.encode(coil_data) == raw_value


def test_unsigned_u8_mapping_encode_exception(
    encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8_mapping: Coil
):
    coil_data = CoilData(coil_unsigned_u8_mapping, "Beer")
    with pytest.raises(EncodeException):
        encoder_word_swap_false.encode(coil_data)


# Unsigned 8-bit boolean
@pytest.fixture
def coil_unsigned_u8_boolean():
    return Coil(
        43024,
        "status-cooling-43024",
        "Status Cooling",
        "u8",
        factor=1,
        mappings={"0": "Off", "1": "On"},
    )


def test_unsigned_u8_boolean(coil_unsigned_u8_boolean: Coil):
    assert coil_unsigned_u8_boolean.is_boolean


def test_unsigned_u8_encode(
    encoder_word_swap_false: CoilDataEncoder, coil_unsigned_u8_boolean: Coil
):
    coil_data = CoilData(coil_unsigned_u8_boolean, "On")
    assert encoder_word_swap_false.encode(coil_data) == b"\x01\x00\x00\x00"


# Unsigned 8-bit boolean with bounds
@pytest.fixture
def coil_unsigned_u8_boolean_with_bounds():
    return Coil(
        47050,
        "status-cooling-43024",
        "Periodic HW",
        "s8",
        factor=1,
        min=0,
        max=1,
    )


def test_unsigned_u8_boolean_with_bounds_is_boolean(
    coil_unsigned_u8_boolean_with_bounds: Coil,
):
    assert coil_unsigned_u8_boolean_with_bounds.is_boolean


@pytest.mark.parametrize(
    "value, raw_value",
    [
        ("On", b"\x01\x00\x00\x00"),
        ("Off", b"\x00\x00\x00\x00"),
    ],
)
def test_unsigned_u8_boolean_with_bounds_encode(
    value,
    raw_value,
    encoder_word_swap_false: CoilDataEncoder,
    coil_unsigned_u8_boolean_with_bounds: Coil,
):
    coil_data = CoilData(coil_unsigned_u8_boolean_with_bounds, value)
    assert encoder_word_swap_false.encode(coil_data) == raw_value


@pytest.mark.parametrize("size", ["u32", "s32"])
def test_word_swap_unset(size, encoder: CoilDataEncoder):
    coil = Coil(1, "test", "test", size)
    with pytest.raises(DecodeException):
        encoder.decode(coil, b"(\x06\x00\x00")

    with pytest.raises(EncodeException):
        encoder.encode(CoilData(coil, 1))
