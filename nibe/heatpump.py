import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from importlib.resources import files
import json
import logging
from os import PathLike
from typing import Dict, Optional, Union

from nibe.coil import Coil, CoilData
from nibe.event_server import EventServer
from nibe.exceptions import CoilNotFoundException, ModelIdentificationFailed

logger = logging.getLogger("nibe").getChild(__name__)


class Series(Enum):
    """Series enum class"""

    CUSTOM = auto()
    F = auto()
    S = auto()


class Model(Enum):
    """Model enum class"""

    F1155 = "f1155_f1255", Series.F
    F1255 = "f1155_f1255", Series.F

    S1155 = "s1155_s1255", Series.S
    S1255 = "s1155_s1255", Series.S

    F1145 = "f1145_f1245", Series.F
    F1245 = "f1145_f1245", Series.F

    F1345 = "f1345", Series.F
    F1355 = "f1355", Series.F

    F730 = "f730", Series.F
    F750 = "f750", Series.F

    F370 = "f370_f470", Series.F
    F470 = "f370_f470", Series.F

    S320 = "s320_s325", Series.S
    S325 = "s320_s325", Series.S

    S2125 = "s2125", Series.S

    SMO20 = "smo20", Series.F
    SMO40 = "smo40", Series.F

    SMOS40 = "smos40", Series.S

    VVM225 = "vvm225_vvm320_vvm325", Series.F
    VVM320 = "vvm225_vvm320_vvm325", Series.F
    VVM325 = "vvm225_vvm320_vvm325", Series.F

    VVM310 = "vvm310_vvm500", Series.F
    VVM500 = "vvm310_vvm500", Series.F

    CUSTOM = "custom", Series.CUSTOM

    data_file: Union[str, bytes, PathLike[str], PathLike[bytes]]
    series: Series

    def __new__(cls, data_file: str, series: Series):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        obj.data_file = data_file
        obj.series = series
        return obj

    def get_coil_data(self):
        """Get coil data for model"""
        if self == Model.CUSTOM:
            with open(self.data_file) as fh:
                return json.load(fh)
        else:
            with files("nibe.data").joinpath(f"{self.data_file}.json").open("r") as fh:
                return json.load(fh)

    @classmethod
    def keys(cls):
        """Get all keys of the enum class"""
        return cls.__members__.keys()


@dataclass
class ProductInfo:
    """Product info class"""

    model: str
    firmware_version: int

    def identify_model(self) -> Model:
        """Identify model from product info

        :raises ModelIdentificationFailed: When model cannot be identified"""
        for key in Model.keys():
            if key in self.model.upper():
                return getattr(Model, key)

        raise ModelIdentificationFailed(f'Unable to identify model from "{self.model}"')


class HeatPump(EventServer):
    """Heat pump class"""

    COIL_UPDATE_EVENT = "coil_update"

    _address_to_coil: Dict[str, Coil]
    _name_to_coil: Dict[str, Coil]
    word_swap: Optional[bool] = None
    _product_info: Union[ProductInfo, None] = None
    _model: Optional[Model] = None

    def __init__(self, model: Optional[Model] = None):
        super().__init__()

        self._address_to_coil = {}
        self._name_to_coil = {}

        if model is not None:
            self.model = model

    @property
    def model(self) -> Union[Model, None]:
        """Returns the model of the heat pump"""
        return self._model

    @model.setter
    def model(self, model: Model):
        """Sets the model of the heat pump"""
        assert isinstance(model, Model), "Passed argument is not of a Model type"

        self._model = model

    @property
    def series(self) -> Series:
        """Returns the series of the heat pump"""
        assert self._model
        return self._model.series

    @property
    def product_info(self) -> Union[ProductInfo, None]:
        """Returns the product info of the heat pump"""
        return self._product_info

    @product_info.setter
    def product_info(self, product_info: ProductInfo):
        """Sets the product info of the heat pump"""
        assert isinstance(
            product_info, ProductInfo
        ), "Passed argument is not of a ProductInfo type"

        self._product_info = product_info

    async def _load_coils(self):
        assert isinstance(self._model, Model), "Model is not set"
        data = await asyncio.get_running_loop().run_in_executor(
            None, self._model.get_coil_data
        )

        self._address_to_coil = {}
        for k, v in data.items():
            try:
                self._address_to_coil[k] = Coil(address=int(k), **v)
            except (AssertionError, TypeError) as e:
                logger.warning(f"Failed to register coil {k}: {e}")
        self._name_to_coil = {c.name: c for _, c in self._address_to_coil.items()}

    async def initialize(self):
        """Initialize the heat pump"""
        if not isinstance(self._model, Model) and isinstance(
            self._product_info, ProductInfo
        ):
            self.model = self._product_info.identify_model()

        assert isinstance(
            self._model, Model
        ), "Model is not set and product info is not available"

        await self._load_coils()

    def get_coils(self) -> list[Coil]:
        """Returns a list of all coils"""
        return list(self._address_to_coil.values())

    def get_coil_by_address(self, address: Union[int, str]) -> Coil:
        """Returns a coil by address

        :raises CoilNotFoundException: if coil is not found
        """
        try:
            return self._address_to_coil[str(address)]
        except KeyError:
            raise CoilNotFoundException(f"Coil with address {address} not found")

    def get_coil_by_name(self, name: str) -> Coil:
        """Returns a coil by name

        :raises CoilNotFoundException: if coil is not found
        """
        try:
            return self._name_to_coil[str(name)]
        except KeyError:
            raise CoilNotFoundException(f"Coil with name '{name}' not found")

    def notify_coil_update(self, coil_data: CoilData):
        """Notifies listeners about coil update"""
        self.notify_event_listeners(self.COIL_UPDATE_EVENT, coil_data)
