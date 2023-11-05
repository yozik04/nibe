from abc import abstractmethod
from binascii import hexlify
from typing import Generic, List, Optional, TypeVar

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


_RawDataT = TypeVar("_RawDataT")


class CoilDataEncoder(Generic[_RawDataT]):
    """Encode and decode coil data."""

    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    @abstractmethod
    def _encode(self, coil_data: CoilData) -> _RawDataT:
        pass

    def encode(self, coil_data: CoilData) -> _RawDataT:
        """Encode coil data to bytes.

        :raises EncodeException: If encoding fails"""
        try:
            return self._encode(coil_data)
        except (ValueError, ConstructError, ValidationError) as e:
            raise EncodeException(
                f"Failed to encode {coil_data.coil.name} coil for value: {coil_data.value}, exception: {e}"
            )

    @abstractmethod
    def _decode(self, coil: Coil, raw: _RawDataT) -> CoilData:
        pass

    def decode(self, coil: Coil, raw: _RawDataT) -> CoilData:
        """Decode coil data from bytes.

        :raises DecodeException: If decoding fails"""
        try:
            return self._decode(coil, raw)
        except (ValueError, AssertionError, ConstructError, ValidationError) as e:
            raise DecodeException(
                f"Failed to decode {coil.name} coil from raw: {hexlify(raw).decode('utf-8')}, exception: {e}"
            ) from e

    def _is_hitting_integer_limit(self, coil: Coil, int_value: int):
        if coil.size == "u8" and int_value >= 0xFF:
            return True
        if coil.size == "s8" and int_value <= -0x80:
            return True
        if coil.size == "u16" and int_value >= 0xFFFF:
            return True
        if coil.size == "s16" and int_value <= -0x8000:
            return True
        if coil.size == "u32" and int_value >= 0xFFFFFFFF:
            return True
        if coil.size == "s32" and int_value <= -0x80000000:
            return True

        return False


class CoilDataEncoderNibeGw(CoilDataEncoder[bytes]):
    """Encode and decode coil data."""

    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    def _encode(self, coil_data: CoilData) -> bytes:
        """Encode coil data to bytes."""
        coil_data.validate()

        return self._pad(self._get_parser(coil_data.coil), coil_data.raw_value)

    def _decode(self, coil: Coil, raw: bytes) -> CoilData:
        """Decode coil data from bytes."""
        parser = self._get_parser(coil)
        assert parser.sizeof() <= len(
            raw
        ), f"Invalid raw data size: given {len(raw)}, expected at least {parser.sizeof()}"
        value = parser.parse(raw)
        if self._is_hitting_integer_limit(coil, value):
            return CoilData(coil, None)

        return CoilData.from_raw_value(coil, value)

    def _get_parser(self, coil: Coil) -> Construct:
        if coil.size in ["u32", "s32"] and self.word_swap is None:
            raise ValueError("Word swap is not set, cannot parse 32 bit integers")

        if self.word_swap:  # yes, it is visa versa
            return parser_map[coil.size]
        else:
            return parser_map_word_swapped[coil.size]

    def _pad(self, parser: Construct, value: int) -> bytes:
        return Padded(4, parser).build(value)


class CoilDataCoderModbus(CoilDataEncoder[List[int]]):
    word_swap: Optional[bool] = None

    def __init__(self, word_swap: Optional[bool] = None):
        self.word_swap = word_swap

    def _encode(self, coil_data: CoilData) -> List[int]:
        coil_data.validate()
        coil = coil_data.coil

        signed = coil.size in ("s32", "s16", "s8")

        raw_value = coil_data.raw_value
        raw_bytes = raw_value.to_bytes(8, "little", signed=signed)
        if coil.size in ("s32", "u32"):
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
        elif coil.size in ("s16", "u16", "s8", "u8"):
            return [int.from_bytes(raw_bytes[0:2], "little", signed=False)]
        raise ValueError("Unknown coil encoding")

    def _decode(self, coil: Coil, values: List[int]) -> CoilData:
        signed = coil.size in ("s32", "s16", "s8")

        raw_bytes = [byte for value in values for byte in value.to_bytes(2, "little")]
        raw_value = int.from_bytes(raw_bytes, byteorder="little", signed=signed)

        if self._is_hitting_integer_limit(coil, raw_value):
            return CoilData(coil, None)

        return CoilData.from_raw_value(coil, raw_value)
