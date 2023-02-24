from dataclasses import dataclass
from typing import Dict, Optional, Union

from nibe.exceptions import NoMappingException, ValidationError


def is_coil_boolean(coil):
    if coil.factor != 1:
        return False

    if coil.min == 0 and coil.max == 1:
        return True

    if coil.mappings and all(k in ["0", "1"] for k in coil.mappings):
        return True

    return False


class Coil:
    """Represents a coil."""

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
        """Set mappings for value translation."""
        if mappings:
            self.mappings = {k: v.upper() for k, v in mappings.items()}
            self.reverse_mappings = {v.upper(): k for k, v in mappings.items()}
        else:
            self.mappings = None
            self.reverse_mappings = None

    @property
    def has_mappings(self):
        """Return True if mappings are defined."""
        return self.mappings is not None

    def get_mapping_for(self, value: int):
        """Return mapping for value.

        :raises NoMappingException: When no mapping is found"""
        if not self.mappings:
            raise NoMappingException(f"No mappings defined for {self.name}")

        try:
            return self.mappings[str(value)]
        except KeyError:
            raise NoMappingException(
                f"Mapping not found for {self.name} coil for value: {value}"
            )

    def get_reverse_mapping_for(self, value: Union[int, float, str, None]) -> int:
        """Return reverse mapping for value.

        :raises NoMappingException: When no mapping is found"""
        if not isinstance(value, str):
            raise ValidationError(
                f"{self.name} coil value ({value}) is invalid type (str is expected)"
            )

        if not self.reverse_mappings:
            raise NoMappingException(
                f"{self.name} coil has no reverse mappings defined"
            )

        try:
            value = value.upper()
            return int(self.reverse_mappings[str(value)])
        except KeyError:
            raise NoMappingException(
                f"{self.name} coil reverse mapping not found for value: {value}"
            )

    def is_raw_value_valid(self, value: int) -> bool:
        """Return True if provided raw value is valid."""
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
    """Represents a coil data."""

    coil: Coil
    value: Union[int, float, str, None] = None

    def __repr__(self) -> str:
        return f"Coil {self.coil.name}, value: {self.value}"

    @staticmethod
    def from_mapping(coil: Coil, value: int) -> "CoilData":
        """Create CoilData from raw value using mappings."""
        return CoilData(coil, coil.get_mapping_for(value))

    @staticmethod
    def from_raw_value(coil: Coil, value: int) -> "CoilData":
        """Create CoilData from raw value."""
        assert coil.is_raw_value_valid(
            value
        ), f"Raw value {value} is out of range for coil {coil.name}"

        if coil.has_mappings:
            return CoilData.from_mapping(coil, value)

        return CoilData(coil, value / coil.factor)

    @property
    def raw_value(self) -> int:
        """Return raw value for coil."""
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

    def validate(self) -> None:
        """Validate coil data.

        :raises ValidationError: when validation fails"""
        if self.value is None:
            raise ValidationError(f"Value for {self.coil.name} is not set")

        if self.coil.has_mappings:
            self.coil.get_reverse_mapping_for(
                self.value
            )  # can throw NoMappingException(ValidationException) or AssertionError
            return

        if not isinstance(self.value, (int, float)):
            raise ValidationError(
                f"{self.coil.name} coil value ({self.value}) is invalid type (expected int or float)"
            )

        self._check_value_bounds()

    def _check_value_bounds(self):
        if self.coil.min is not None and self.value < self.coil.min:
            raise ValidationError(
                f"{self.coil.name} coil value ({self.value}) is smaller than min allowed ({self.coil.min})"
            )

        if self.coil.max is not None and self.value > self.coil.max:
            raise ValidationError(
                f"{self.coil.name} coil value ({self.value}) is larger than max allowed ({self.coil.max})"
            )
