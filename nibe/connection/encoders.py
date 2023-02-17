from binascii import hexlify

from construct import (
    Construct,
    ConstructError,
    Int8sl,
    Int8ul,
    Int16sl,
    Int16ul,
    Int32sl,
    Int32ul,
    Padded,
)

from nibe.coil import Coil, CoilData
from nibe.exceptions import DecodeException, EncodeException
from nibe.parsers import WordSwapped

parser_map = {
    "u8": Int8ul,
    "s8": Int8sl,
    "u16": Int16ul,
    "s16": Int16sl,
    "u32": Int32ul,
    "s32": Int32sl,
}

parser_map_word_swaped = parser_map.copy()
parser_map_word_swaped.update(
    {
        "u32": WordSwapped(Int32ul),
        "s32": WordSwapped(Int32sl),
    }
)


class CoilDataEncoder:
    def __init__(self, word_swap: bool = True) -> None:
        self._word_swap = word_swap

    def encode(self, coil_data: CoilData) -> bytes:
        try:
            assert coil_data.is_valid, "Invalid coil data"

            return self._pad(self._get_parser(coil_data.coil), coil_data.raw_value)
        except (ConstructError, AssertionError) as e:
            raise EncodeException(
                f"Failed to encode {coil_data.coil.name} coil for value: {coil_data.value}, exception: {e}"
            )

    def decode(self, coil: Coil, raw: bytes) -> CoilData:
        try:
            parser = self._get_parser(coil)
            assert parser.sizeof() <= len(
                raw
            ), f"Invalid raw data size: given {len(raw)}, expected at least {parser.sizeof()}"
            value = parser.parse(raw)
            if self._is_hitting_integer_limit(coil, value):
                return CoilData(coil, None)

            return CoilData.from_raw_value(coil, value)
        except AssertionError as e:
            raise DecodeException(
                f"Failed to decode {coil.name} coil from raw: {hexlify(raw).decode('utf-8')}, exception: {e}"
            )

    def _is_hitting_integer_limit(self, coil: Coil, int_value: int):
        if coil.size == "u8" and int_value == 0xFF:
            return True
        if coil.size == "s8" and int_value == -0x80:
            return True
        if coil.size == "u16" and int_value == 0xFFFF:
            return True
        if coil.size == "s16" and int_value == -0x8000:
            return True
        if coil.size == "u32" and int_value == 0xFFFFFFFF:
            return True
        if coil.size == "s32" and int_value == -0x80000000:
            return True

        return False

    def _get_parser(self, coil: Coil) -> Construct:
        if self._word_swap:
            return parser_map[coil.size]
        else:
            return parser_map_word_swaped[coil.size]

    def _pad(self, parser: Construct, value: int) -> bytes:
        return Padded(4, parser).build(value)
