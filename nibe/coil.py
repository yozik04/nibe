from dataclasses import dataclass
import datetime
from typing import Dict, Optional, Union

from nibe.exceptions import NoMappingException, ValidationError

MIN_DATE = datetime.date(2007, 1, 1)
MAX_DATE = MIN_DATE + datetime.timedelta(0xFFFE)


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

    mappings: Optional[Dict[str, str]] = None
    reverse_mappings: Optional[Dict[str, str]] = None

    def __init__(
        self,
        address: int,
        name: str,
        title: str,
        size: str,
        factor: int = 1,
        write: bool = False,
        **kwargs,
    ):
        r"""Initialize coil.

        :param address: Coil address
        :param name: Coil name
        :param title: Coil title
        :param size: Coil size ("u8", "s8", "u16", "s16", "u32", "s32")
        :param factor: Coil raw value factor (used for value translation)
        :param write: Is coil writable
        :param kwargs:
            - mappings: Coil mappings (used for value translation)
            - info: Coil info
            - unit: Coil measurement unit
            - type: Coil type (number or date)
            - min: Coil raw min value (used for validation)
            - max: Coil raw max value (used for validation)
        """

        assert isinstance(address, int), "Address must be defined"
        assert name, "Name must be defined"
        assert title, "Title must be defined"
        assert factor, "Factor must be defined"

        self.address = address
        self.name = name
        self.title = title
        self.size = size
        self.factor = factor
        self.is_writable = write

        if "mappings" in kwargs:
            mappings = kwargs.pop("mappings")
            assert factor == 1, "When mapping is used factor needs to be 1"
            self.set_mappings(mappings)

        self.info = kwargs.pop("info", None)
        self.unit = kwargs.pop("unit", None)
        self.type = kwargs.pop("type", "number")

        assert self.type in [
            "number",
            "date",
        ], f"Invalid coil type {self.type} for coil {self.name}"

        assert not (
            self.has_mappings and self.type == "date"
        ), f"Date coil {self.name} cannot have mappings"

        self.raw_min = kwargs.pop("min", None)
        self.raw_max = kwargs.pop("max", None)

        self.min = self.raw_min / factor if self.raw_min is not None else None
        self.max = self.raw_max / factor if self.raw_max is not None else None

        self.is_boolean = is_coil_boolean(self)
        if self.is_boolean and not self.has_mappings:
            self.set_mappings({"0": "OFF", "1": "ON"})

        self.is_date = self.type == "date"

        self.other = kwargs

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
    value: Union[int, float, str, datetime.date, None] = None

    def __repr__(self) -> str:
        return f"Coil {self.coil.name}, value: {self.value}"

    @staticmethod
    def from_mapping(coil: Coil, value: int) -> "CoilData":
        """Create CoilData from raw value using mappings."""
        return CoilData(coil, coil.get_mapping_for(value))

    @staticmethod
    def from_raw_value(coil: Coil, value: Union[int, None]) -> "CoilData":
        """Create CoilData from raw value."""
        if value is None:
            return CoilData(coil, None)
        assert coil.is_raw_value_valid(
            value
        ), f"Raw value {value} is out of range for coil {coil.name}"

        if coil.is_date:
            return CoilData(coil, MIN_DATE + datetime.timedelta(days=value))

        if coil.has_mappings:
            return CoilData.from_mapping(coil, value)

        if coil.factor == 1:
            return CoilData(coil, value)
        else:
            return CoilData(coil, value / coil.factor)

    @property
    def raw_value(self) -> int:
        """Return raw value for coil."""
        if self.coil.is_date:
            assert isinstance(
                self.value, datetime.date
            ), f"Provided value '{self.value}' is invalid type (datetime.date is expected) for {self.coil.name}"

            return (self.value - MIN_DATE).days

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

        if self.coil.is_date and not isinstance(self.value, datetime.date):
            raise ValidationError(
                f"{self.coil.name} coil value ({self.value}) is invalid type (expected datetime.date)"
            )

        if self.coil.has_mappings:
            self.coil.get_reverse_mapping_for(
                self.value
            )  # can throw NoMappingException(ValidationException) or AssertionError
            return

        if not isinstance(self.value, (int, float, datetime.date)):
            raise ValidationError(
                f"{self.coil.name} coil value ({self.value}) is invalid type (expected int, float or datetime.date)"
            )

        self._check_value_bounds()

    def _check_value_bounds(self):
        if self.coil.is_date:
            if self.value < MIN_DATE:
                raise ValidationError(
                    f"{self.coil.name} coil value ({self.value}) is smaller than min allowed ({MIN_DATE})"
                )

            if self.value > MAX_DATE:
                raise ValidationError(
                    f"{self.coil.name} coil value ({self.value}) is larger than max allowed ({MAX_DATE})"
                )

        else:
            if self.coil.min is not None and self.value < self.coil.min:
                raise ValidationError(
                    f"{self.coil.name} coil value ({self.value}) is smaller than min allowed ({self.coil.min})"
                )

            if self.coil.max is not None and self.value > self.coil.max:
                raise ValidationError(
                    f"{self.coil.name} coil value ({self.value}) is larger than max allowed ({self.coil.max})"
                )
