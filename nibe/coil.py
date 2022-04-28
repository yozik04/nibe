from typing import Dict, Optional, Union

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


def is_coil_boolean(coil):
    if coil.factor != 1:
        return False

    if coil.min == 0 and coil.max == 1:
        return True

    if coil.mappings and all(k in ["0", "1"] for k in coil.mappings):
        return True

    return False


class Coil:
    mappings: Optional[Dict[str, str]]
    reverse_mappings: Optional[Dict[str, str]]

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

        self.set_mappings(mappings)

        self.info = info
        self.unit = unit
        self.is_writable = write

        self.other = kwargs

        self.raw_min = self.other.get("min")
        self.raw_max = self.other.get("max")

        self.min = self.raw_min / factor if self.raw_min is not None else None
        self.max = self.raw_max / factor if self.raw_max is not None else None

        self.is_boolean = is_coil_boolean(self)
        if self.is_boolean and not mappings:
            self.set_mappings({"0": "OFF", "1": "ON"})

        self._value = None

    def set_mappings(self, mappings):
        if mappings:
            self.mappings = dict((k, v.upper()) for k, v in mappings.items())
            self.reverse_mappings = dict((v.upper(), k) for k, v in mappings.items())
        else:
            self.mappings = None
            self.reverse_mappings = None

    @property
    def value(self) -> Union[int, float, str]:
        return self._value

    @value.setter
    def value(self, value: Union[int, float, str]):
        if self.mappings:
            value = value.upper()
            assert (
                value in self.reverse_mappings
            ), f"Provided value '{value}' is not in {self.reverse_mappings.keys()} for {self.name}"

            self._value = value
            return

        assert isinstance(
            value, (int, float)
        ), f"Provided value '{value}' is invalid type (int and float are supported) for {self.name}"

        self.check_value_bounds(value)

        self._value = value

    @property
    def raw_value(self) -> bytes:
        return self._encode(self.value)

    @raw_value.setter
    def raw_value(self, raw_value: bytes):
        self.value = self._decode(raw_value)

    def _decode(self, raw: bytes) -> Union[int, float, str]:
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

    def _encode(self, val: Union[int, float, str]) -> bytes:
        try:
            if self.reverse_mappings is not None:
                mapped_value = self.reverse_mappings.get(str(val))
                if mapped_value is None:
                    raise EncodeException(
                        f"Mapping not found for {self.name} coil for value: {val}"
                    )

                return self._pad(mapped_value)

            if self.factor != 1:
                val *= self.factor

            self._check_raw_value_bounds(val)

            return self._pad(val)
        except AssertionError as e:
            raise EncodeException(e)
        except ConstructError as e:
            raise EncodeException(
                f"Failed to encode {self.name} coil for value: {val}, exception: {e}"
            )

    def _pad(self, value) -> bytes:
        return Padded(4, self.parser).build(int(value))

    def check_value_bounds(self, value):
        if self.min is not None:
            assert (
                value >= self.min
            ), f"{self.name} coil value is smaller than min({self.min}) allowed"

        if self.max is not None:
            assert (
                value <= self.max
            ), f"{self.name} coil value is larger than max({self.max}) allowed"

    def _check_raw_value_bounds(self, value):
        if self.raw_min is not None:
            assert (
                value >= self.raw_min
            ), f"{self.name} coil raw value is smaller than min({self.raw_min}) allowed"

        if self.raw_max is not None:
            assert (
                value <= self.raw_max
            ), f"{self.name} coil raw value is larger than max({self.raw_max}) allowed"

    def __repr__(self):
        return f"Coil {self.address}, name: {self.name}, title: {self.title}, value: {self.value}"
