from abc import abstractmethod
from binascii import hexlify
from typing import Generic, List, Optional, SupportsInt, TypeVar

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
from nibe.exceptions import DecodeException, EncodeException, ValidationError
from nibe.parsers import WordSwapped

parser_map = {
    "u8": Int8ul,
    "s8": Int8sl,
    "u16": Int16ul,
    "s16": Int16sl,
    "u32": Int32ul,
    "s32": Int32sl,
}

parser_map_word_swapped = parser_map.copy()
parser_map_word_swapped.update(
    {
        "u32": WordSwapped(Int32ul),
        "s32": WordSwapped(Int32sl),
    }
)

integer_limit = {
    "u8": 0xFF,
    "s8": -0x80,
    "u16": 0xFFFF,
    "s16": -0x8000,
    "u32": 0xFFFFFFFF,
    "s32": -0x80000000,
}


def is_hitting_integer_limit(size: str, int_value: int):
    limit = integer_limit[size]
    if limit < 0:
        return int_value <= limit
    return int_value >= limit


_RawDataT = TypeVar("_RawDataT")


class CoilDataEncoder(Generic[_RawDataT]):
    """Encode and decode coil data."""

    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    @abstractmethod
    def encode_raw_value(self, size: str, raw_value: int) -> _RawDataT:
        pass

    def encode(self, coil_data: CoilData) -> _RawDataT:
        """Encode coil data to bytes.

        :raises EncodeException: If encoding fails"""
        try:
            coil_data.validate()
            return self.encode_raw_value(coil_data.coil.size, coil_data.raw_value)
        except (ValueError, ConstructError, ValidationError) as e:
            raise EncodeException(
                f"Failed to encode {coil_data.coil.name} coil for value: {coil_data.value}, exception: {e}"
            )

    @abstractmethod
    def decode_raw_value(self, size: str, raw: _RawDataT) -> int:
        pass

    def decode(self, coil: Coil, raw: _RawDataT) -> CoilData:
        """Decode coil data from bytes.

        :raises DecodeException: If decoding fails"""
        try:
            value = self.decode_raw_value(coil.size, raw)
            if is_hitting_integer_limit(coil.size, value):
                value = None

            return CoilData.from_raw_value(coil, value)

        except (ValueError, AssertionError, ConstructError, ValidationError) as e:
            raise DecodeException(
                f"Failed to decode {coil.name} coil from raw: {hexlify(raw).decode('utf-8')}, exception: {e}"
            ) from e


class CoilDataEncoderNibeGw(CoilDataEncoder[bytes]):
    """Encode and decode coil data."""

    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    def encode_raw_value(self, size: str, raw_value: int) -> bytes:
        """Encode coil data to bytes."""
        return self._pad(self._get_parser(size), raw_value)

    def decode_raw_value(self, size: str, raw: bytes) -> int:
        """Decode coil data from bytes."""
        parser = self._get_parser(size)
        assert parser.sizeof() <= len(
            raw
        ), f"Invalid raw data size: given {len(raw)}, expected at least {parser.sizeof()}"
        value = parser.parse(raw)
        return value

    def _get_parser(self, size: str) -> Construct:
        if size in ["u32", "s32"] and self.word_swap is None:
            raise ValueError("Word swap is not set, cannot parse 32 bit integers")

        if self.word_swap:  # yes, it is visa versa
            return parser_map[size]
        else:
            return parser_map_word_swapped[size]

    def _pad(self, parser: Construct, value: int) -> bytes:
        return Padded(4, parser).build(value)


class CoilDataEncoderModbus(CoilDataEncoder[List[SupportsInt]]):
    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    def encode_raw_value(self, size: str, raw_value: int) -> List[SupportsInt]:
        signed = size in ("s32", "s16", "s8")

        raw_bytes = raw_value.to_bytes(8, "little", signed=signed)
        if size in ("s32", "u32"):
            if self.word_swap:
                return [
                    int.from_bytes(raw_bytes[0:2], "little", signed=False),
                    int.from_bytes(raw_bytes[2:4], "little", signed=False),
                ]
            else:
                return [
                    int.from_bytes(raw_bytes[2:4], "little", signed=False),
                    int.from_bytes(raw_bytes[0:2], "little", signed=False),
                ]
        elif size in ("s16", "u16", "s8", "u8"):
            return [int.from_bytes(raw_bytes[0:2], "little", signed=False)]
        raise ValueError("Unknown coil encoding")

    def decode_raw_value(self, size: str, raw: List[SupportsInt]) -> int:
        signed = size in ("s32", "s16", "s8")

        if not self.word_swap:
            raw = reversed(raw)
        raw_bytes = [byte for value in raw for byte in int(value).to_bytes(2, "little")]
        raw_value = int.from_bytes(raw_bytes, byteorder="little", signed=signed)
        return raw_value
