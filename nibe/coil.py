from typing import Dict, Union

from construct import (ConstructError, Int8sl, Int8ul, Int16sl, Int16ul, Int32sl,
                       Int32ul, Padded,)

from nibe.exceptions import DecodeException, EncodeException

parser_map = {
    "u8": Int8ul,
    "u16": Int16ul,
    "u32": Int32ul,
    "s8": Int8sl,
    "s16": Int16sl,
    "s32": Int32sl,
}


class Coil:
    mappings: Dict[str, str]
    reverse_mappings: Dict[str, str]

    def __init__(
        self,
        address: int,
        name: str,
        title: str,
        size: str,
        factor: int = 1,
        info: str = None,
        unit: str = None,
        mappings: dict = None,
        write: bool = False,
        **kwargs,
    ):
        assert isinstance(address, int), "Address must be defined"
        assert name, "Name must be defined"
        assert title, "Title must be defined"
        assert factor, "Factor must be defined"
        assert not (
            mappings is not None and factor != 1
        ), "When mapping is used factor needs to be 1"

        self.parser = parser_map.get(size)
        assert self.parser is not None

        self.address = address
        self.name = name
        self.title = title
        self.factor = factor
        self.mappings = mappings
        self.reverse_mappings = (
            dict((v, k) for k, v in self.mappings.items())
            if self.mappings is not None
            else None
        )
        self.info = info
        self.unit = unit
        self.write = write

        self.other = kwargs

        self._value = None

    @property
    def value(self) -> Union[int, float, str]:
        return self._value

    @value.setter
    def value(self, value: Union[int, float, str]):
        assert (
            self.mappings is None or value in self.reverse_mappings
        ), f"Provided value {value} is not in {self.reverse_mappings.keys()}"

        self._value = value

    @property
    def encoded_value(self) -> bytes:
        return self.encode(self.value)

    def decode(self, raw: bytes) -> Union[int, float, str]:
        value = self.parser.parse(raw)
        try:
            self._check_raw_value_bounds(value)
        except AssertionError as e:
            raise DecodeException(e)
        if self.factor != 1:
            value /= self.factor
        if self.mappings is None:
            return value

        mapped_value = self.mappings.get(str(value))
        if mapped_value is None:
            raise DecodeException(
                f"Mapping not found for {self.name} coil for value: {value}"
            )

        return mapped_value

    def encode(self, val: Union[int, float, str]) -> bytes:
        if self.reverse_mappings is not None:
            mapped_value = self.reverse_mappings.get(str(val))
            if mapped_value is None:
                raise EncodeException(
                    f"Mapping not found for {self.name} coil for value: {val}"
                )
            val = int(mapped_value)

        if self.factor != 1:
            val *= self.factor

        try:
            self._check_raw_value_bounds(val)
        except AssertionError as e:
            raise EncodeException(e)

        try:
            return Padded(4, self.parser).build(int(val))
        except ConstructError as e:
            raise EncodeException(
                f"Failed to encode {self.name} coil for value: {val}, exception: {e}"
            )

    def _check_raw_value_bounds(self, value):
        min = self.other.get("min")
        if min is not None:
            assert (
                value >= min
            ), f"{self.name} coil value is smaller than min({min}) allowed"

        max = self.other.get("max")
        if max is not None:
            assert (
                value <= max
            ), f"{self.name} coil value is larger than max({max}) allowed"

    def __repr__(self):
        return f"Coil {self.address}, name: {self.name}, title: {self.title}, value: {self.value}"
