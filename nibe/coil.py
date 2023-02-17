from dataclasses import dataclass
from typing import Dict, Optional, Union

from nibe.exceptions import NoMappingException


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

        self.size = size

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

    def set_mappings(self, mappings):
        if mappings:
            self.mappings = {k: v.upper() for k, v in mappings.items()}
            self.reverse_mappings = {v.upper(): k for k, v in mappings.items()}
        else:
            self.mappings = None
            self.reverse_mappings = None

    @property
    def has_mappings(self):
        return self.mappings is not None

    def get_mapping_for(self, value: int):
        if not self.mappings:
            raise NoMappingException(f"No mappings defined for {self.name}")

        try:
            return self.mappings[str(value)]
        except KeyError:
            raise NoMappingException(
                f"Mapping not found for {self.name} coil for value: {value}"
            )

    def get_reverse_mapping_for(self, value: Union[int, float, str, None]) -> int:
        assert isinstance(
            value, str
        ), f"Provided value '{value}' is invalid type (str is supported) for {self.name}"

        if not self.reverse_mappings:
            raise NoMappingException(f"No reverse mappings defined for {self.name}")

        try:
            value = value.upper()
            return int(self.reverse_mappings[str(value)])
        except KeyError:
            raise NoMappingException(
                f"Reverse mapping not found for {self.name} coil for value: {value}"
            )

    def is_raw_value_valid(self, value: int) -> bool:
        if not isinstance(value, int):
            return False

        if self.raw_min is not None and value < self.raw_min:
            return False

        if self.raw_max is not None and value > self.raw_max:
            return False

        return True

    def __repr__(self):
        return f"Coil {self.address}, name: {self.name}, title: {self.title}"


@dataclass
class CoilData:
    coil: Coil
    value: Union[int, float, str, None] = None

    def __repr__(self) -> str:
        return f"Coil {self.coil.name}, value: {self.value}"

    @staticmethod
    def from_mapping(coil: Coil, value: int) -> "CoilData":
        return CoilData(coil, coil.get_mapping_for(value))

    @staticmethod
    def from_raw_value(coil: Coil, value: int) -> "CoilData":
        assert coil.is_raw_value_valid(
            value
        ), f"Raw value {value} is out of range for coil {coil.name}"

        if coil.has_mappings:
            return CoilData.from_mapping(coil, value)

        return CoilData(coil, value / coil.factor)

    @property
    def raw_value(self) -> int:
        if self.coil.has_mappings:
            return self.coil.get_reverse_mapping_for(self.value)

        assert isinstance(
            self.value, (int, float)
        ), f"Provided value '{self.value}' is invalid type (int or float is supported) for {self.coil.name}"

        raw_value = int(self.value * self.coil.factor)
        assert self.coil.is_raw_value_valid(
            raw_value
        ), f"Value {self.value} is out of range for coil {self.coil.name}"

        return raw_value

    @property
    def is_valid(self) -> bool:
        if self.value is None:
            return False

        if self.coil.has_mappings:
            try:
                self.coil.get_reverse_mapping_for(self.value)
                return True
            except NoMappingException:
                return False

        try:
            assert isinstance(
                self.value, (int, float)
            ), f"Provided value '{self.value}' is invalid type (int or float is supported) for {self.coil.name}"

            self._check_value_bounds()

        except AssertionError:
            return False

        return True

    def _check_value_bounds(self):
        if self.coil.min is not None:
            assert (
                self.value >= self.coil.min
            ), f"{self.coil.name} coil value ({self.value}) is smaller than min allowed ({self.coil.min})"

        if self.coil.max is not None:
            assert (
                self.value <= self.coil.max
            ), f"{self.coil.name} coil value ({self.value}) is larger than max allowed ({self.coil.max})"
