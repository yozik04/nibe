from unittest import TestCase

from construct import Int8ul
import pytest

from nibe.coil import Coil
from nibe.exceptions import DecodeException, EncodeException
from nibe.parsers import swapwords


class TestWordSwap(TestCase):
    def test_swapwords(self):
        assert swapwords(b"abcd") == b"cdab"
        assert swapwords(b"ab") == b"ab"


class TestCoil(TestCase):
    def test_create(self):
        coil = Coil(123, "test_name", "test_title", "u8", unknown="some other")

        assert coil.address == 123
        assert coil.name == "test_name"
        assert coil.title == "test_title"
        assert coil.parser == Int8ul
        assert coil.other["unknown"] == "some other"


class TestCoilSigned8(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(48739, "cool-offset-s1-48739", "Cool offset S1", "s8")

    def test_decode(self):
        self.coil.raw_value = b"\xfc\x00\x00\x00"
        assert self.coil.value == -4
        self.coil.raw_value = b"\xfc\x00"
        assert self.coil.value == -4
        self.coil.raw_value = b"\xfc"
        assert self.coil.value == -4

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\x80"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = -4
        assert self.coil.raw_value == b"\xfc\x00\x00\x00"

        with pytest.raises(EncodeException):
            self.coil.value = 256
            _ = self.coil.raw_value

    def test_encode_unavailable(self):
        self.coil.value = None
        with pytest.raises(EncodeException):
            self.coil.raw_value


class TestCoilUnsigned8(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(123, "test", "test", "u8")

    def test_decode(self):
        self.coil.raw_value = b"\x01\x00\x00\x00"
        assert self.coil.value == 1
        self.coil.raw_value = b"\x01\x00"
        assert self.coil.value == 1
        self.coil.raw_value = b"\x01"
        assert self.coil.value == 1

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\xff"
        assert self.coil.value is None
        self.coil.raw_value = b"\xff\xff"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 1
        assert self.coil.raw_value == b"\x01\x00\x00\x00"
        self.coil.value = 255
        assert self.coil.raw_value == b"\xff\x00\x00\x00"

        with pytest.raises(EncodeException):
            self.coil.value = 256
            _ = self.coil.raw_value


class TestCoilUnsigned8WordSwap(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(123, "test", "test", "u8", word_swap=False)

    def test_decode(self):
        self.coil.raw_value = b"\x01\x00\x00\x00"
        assert self.coil.value == 1
        self.coil.raw_value = b"\x01\x00"
        assert self.coil.value == 1
        self.coil.raw_value = b"\x01"
        assert self.coil.value == 1

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\xff"
        assert self.coil.value is None
        self.coil.raw_value = b"\xff\xff"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 1
        assert self.coil.raw_value == b"\x01\x00\x00\x00"
        self.coil.value = 255
        assert self.coil.raw_value == b"\xff\x00\x00\x00"

        with pytest.raises(EncodeException):
            self.coil.value = 256
            _ = self.coil.raw_value


class TestCoilSigned16(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(123, "test", "test", "s16", factor=10, min=50, max=300)

    def test_attributes(self):
        assert self.coil.min == 5.0
        assert self.coil.max == 30.0

        assert self.coil.raw_min == 50
        assert self.coil.raw_max == 300

        assert not self.coil.is_boolean
        assert not self.coil.is_writable

    def test_set_value_bounds(self):
        self.coil.value = 5.0
        self.coil.value = 30

        with pytest.raises(AssertionError):
            self.coil.value = 4.9

        with pytest.raises(AssertionError):
            self.coil.value = 30.1

    def test_decode(self):
        self.coil.raw_value = b"\x97\x00"

    def test_decode_out_of_bounds(self):
        with pytest.raises(DecodeException):
            self.coil.raw_value = b"\x31\x00"

        with pytest.raises(DecodeException):
            self.coil.raw_value = b"\x2d\x10"

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\x00\x80"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 15.1
        assert self.coil.raw_value == b"\x97\x00\x00\x00"

    def test_encode_out_of_bounds(self):
        with pytest.raises(AssertionError):
            self.coil.value = 4

        with pytest.raises(AssertionError):
            self.coil.value = 30.1


class TestCoilUnsigned16(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            123,
            "compressor-frequency-actual-43136",
            "Compressor Frequency, Actual",
            "u16",
            factor=10,
        )

    def test_decode(self):
        self.coil.raw_value = b"\x01\x00\x00\x00"
        assert self.coil.value == 0.1
        self.coil.raw_value = b"\x01\x00"
        assert self.coil.value == 0.1

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\xff\xff"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 0.1
        assert self.coil.raw_value == b"\x01\x00\x00\x00"
        self.coil.value = 25.5
        assert self.coil.raw_value == b"\xff\x00\x00\x00"


class TestCoilUnsigned16WordSwap(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            123,
            "compressor-frequency-actual-43136",
            "Compressor Frequency, Actual",
            "u16",
            factor=10,
            word_swap=False,
        )

    def test_decode(self):
        self.coil.raw_value = b"\x01\x00\x00\x00"
        assert self.coil.value == 0.1
        self.coil.raw_value = b"\x01\x00"
        assert self.coil.value == 0.1

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\xff\xff"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 0.1
        assert self.coil.raw_value == b"\x01\x00\x00\x00"
        self.coil.value = 25.5
        assert self.coil.raw_value == b"\xff\x00\x00\x00"


class TestCoilSigned32(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            43420,
            "tot-op-time-compr-eb100-ep14-43420",
            "Total compressorer operation time",
            "s32",
        )

    def test_decode(self):
        self.coil.raw_value = b"2T\x00\x00"
        assert self.coil.value == 21554

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\x00\x00\x00\x80"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 21554
        assert self.coil.raw_value == b"2T\x00\x00"


class TestCoilSigned32WordSwap(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            43420,
            "tot-op-time-compr-eb100-ep14-43420",
            "Total compressorer operation time",
            "s32",
            word_swap=False,
        )

    def test_decode(self):
        self.coil.raw_value = b"\x00\x00(\x06"
        assert self.coil.value == 1576

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\x00\x80\x00\x00"
        assert self.coil.value is None

    def test_encode(self):
        self.coil.value = 1576
        assert self.coil.raw_value == b"\x00\x00(\x06"


class TestCoilWithMapping(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
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

    def test_set_valid_value(self):
        self.coil.value = "off"

        assert self.coil.value == "OFF"

    def test_set_invalid_value(self):
        with pytest.raises(AssertionError):
            self.coil.value = "Beer"

    def test_decode_mapping(self):
        self.coil.raw_value = b"\x0a"
        assert self.coil.value == "OFF"

    def test_decode_unavailable(self):
        self.coil.raw_value = b"\xff\xff"
        assert self.coil.value is None

    def test_encode_mapping(self):
        self.coil.value = "off"
        assert self.coil.raw_value == b"\x0a\x00\x00\x00"

    def test_decode_mapping_failure(self):
        with pytest.raises(DecodeException):
            self.coil.raw_value = b"\x00"

    def test_encode_mapping_failure(self):
        with pytest.raises(AssertionError):
            self.coil.value = "Unknown"


class TestBooleanCoilWithMapping(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            43024,
            "status-cooling-43024",
            "Status Cooling",
            "u8",
            factor=1,
            mappings={"0": "Off", "1": "On"},
        )

    def test_attributes(self):
        assert self.coil.is_boolean

    def test_set_valid_value(self):
        self.coil.value = "On"
        assert "ON" == self.coil.value

        self.coil.value = "ofF"
        assert "OFF" == self.coil.value


class TestBooleanCoilWithBounds(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(
            47050,
            "status-cooling-43024",
            "Periodic HW",
            "s8",
            factor=1,
            min=0,
            max=1,
            write=True,
        )

    def test_attributes(self):
        assert self.coil.is_boolean

    def test_set_valid_value(self):
        self.coil.value = "ON"
        self.coil.value = "OFF"
