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
    _value: Union[int, float, str, None]

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

        self._value = None

    def set_mappings(self, mappings):
        if mappings:
            self.mappings = {k: v.upper() for k, v in mappings.items()}
            self.reverse_mappings = {v.upper(): k for k, v in mappings.items()}
        else:
            self.mappings = None
            self.reverse_mappings = None

    @property
    def value(self) -> Union[int, float, str, None]:
        return self._value

    @value.setter
    def value(self, value: Union[int, float, str, None]):
        if value is None:
            self._value = None
            return

        if self.reverse_mappings:
            assert isinstance(
                value, str
            ), f"Provided value '{value}' is invalid type (str is supported) for {self.name}"

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

    def get_reverse_mapping_for(self, value: Union[int, float, str, None]):
        if not self.reverse_mappings:
            raise NoMappingException(f"No reverse mappings defined for {self.name}")

        try:
            return self.reverse_mappings[str(value)]
        except KeyError:
            raise NoMappingException(
                f"Reverse mapping not found for {self.name} coil for value: {value}"
            )

    def check_value_bounds(self, value):
        if self.min is not None:
            assert (
                value >= self.min
            ), f"{self.name} coil value ({value}) is smaller than min allowed ({self.min})"

        if self.max is not None:
            assert (
                value <= self.max
            ), f"{self.name} coil value ({value}) is larger than max allowed ({self.max})"

    def check_raw_value_bounds(self, value):
        if self.raw_min is not None:
            assert (
                value >= self.raw_min
            ), f"value ({value}) is smaller than min allowed ({self.raw_min})"

        if self.raw_max is not None:
            assert (
                value <= self.raw_max
            ), f"value ({value}) is larger than max allowed ({self.raw_max})"

    def __repr__(self):
        return f"Coil {self.address}, name: {self.name}, title: {self.title}, value: {self.value}"
