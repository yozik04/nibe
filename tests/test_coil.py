from unittest import TestCase

from construct import Int8ul

from nibe.coil import Coil
from nibe.exceptions import DecodeException, EncodeException


class TestCoil(TestCase):
    def test_create(self):
        coil = Coil(123, "test_name", "test_title", "u8", unknown="some other")

        self.assertEqual(coil.address, 123)
        self.assertEqual(coil.name, "test_name")
        self.assertEqual(coil.title, "test_title")
        self.assertEqual(coil.parser, Int8ul)
        self.assertEqual(coil.other["unknown"], "some other")


class TestCoilUnsigned8(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(123, "test", "test", "u8")

    def test_decode(self):
        self.assertEqual(1, self.coil.decode(b"\x01\x00\x00\x00"))
        self.assertEqual(1, self.coil.decode(b"\x01\x00"))
        self.assertEqual(1, self.coil.decode(b"\x01"))

    def test_encode(self):
        self.assertEqual(b"\x01\x00\x00\x00", self.coil.encode(1))
        self.assertEqual(b"\xff\x00\x00\x00", self.coil.encode(255))

        with self.assertRaises(EncodeException):
            self.coil.encode(256)


class TestCoilSigned16(TestCase):
    def setUp(self) -> None:
        self.coil = Coil(123, "test", "test", "s16", factor=10, min=50, max=300)

    def test_decode(self):
        self.coil.decode(b"\x97\x00")

    def test_decode_out_of_bounds(self):
        with self.assertRaises(DecodeException):
            self.coil.decode(b"\x31\x00")

        with self.assertRaises(DecodeException):
            self.coil.decode(b"\x2d\x10")

    def test_encode(self):
        self.assertEqual(b"\x97\x00\x00\x00", self.coil.encode(15.1))

    def test_encode_out_of_bounds(self):
        with self.assertRaises(EncodeException):
            self.coil.encode(4)

        with self.assertRaises(EncodeException):
            self.coil.encode(30.1)


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
        self.coil.value = "Off"

        self.assertEqual("Off", self.coil.value)

    def test_set_invalid_value(self):
        with self.assertRaises(AssertionError):
            self.coil.value = "Beer"

    def test_decode_mapping(self):
        self.assertEqual("Off", self.coil.decode(b"\x0a"))

    def test_encode_mapping(self):
        self.assertEqual(b"\x0a\x00\x00\x00", self.coil.encode("Off"))

    def test_decode_mapping_failure(self):
        with self.assertRaises(DecodeException):
            self.coil.decode(b"\x00")

    def test_encode_mapping_failure(self):
        with self.assertRaises(EncodeException):
            self.coil.encode("Unknown")
