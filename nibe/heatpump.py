import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from importlib.resources import files
import json
import logging
from os import PathLike
from typing import Dict, Union

from nibe.coil import Coil
from nibe.event_server import EventServer
from nibe.exceptions import CoilNotFoundException, ModelIdentificationFailed

logger = logging.getLogger("nibe").getChild(__name__)


class Series(Enum):
    F = auto()
    S = auto()


class Model(Enum):
    F1155 = "f1155_f1255"
    F1255 = "f1155_f1255"

    S1155 = "s1155_s1255"
    S1255 = "s1155_s1255"

    F1145 = "f1145_f1245"
    F1245 = "f1145_f1245"

    F1345 = "f1345"
    F1355 = "f1355"

    F730 = "f730"
    F750 = "f750"

    F370 = "f370_f470"
    F470 = "f370_f470"

    S320 = "s320_s325"
    S325 = "s320_s325"

    SMO20 = "smo20"
    SMO40 = "smo40"

    SMOS40 = "smos40"

    VVM225 = "vvm225_vvm320_vvm325"
    VVM320 = "vvm225_vvm320_vvm325"
    VVM325 = "vvm225_vvm320_vvm325"

    VVM310 = "vvm310_vvm500"
    VVM500 = "vvm310_vvm500"

    CUSTOM = "custom"

    data_file: Union[str, bytes, PathLike[str], PathLike[bytes]]

    def get_coil_data(self):
        if self.value == "custom":
            with open(self.data_file) as fh:
                return json.load(fh)
        else:
            return json.loads(
                files("nibe.data").joinpath(f"{self.value}.json").read_text()
            )

    @classmethod
    def keys(cls):
        return cls.__members__.keys()


@dataclass
class ProductInfo:
    model: str
    firmware_version: int

    def identify_model(self) -> Model:
        for key in Model.keys():
            if key in self.model.upper():
                return getattr(Model, key)

        raise ModelIdentificationFailed(f'Unable to identify model from "{self.model}"')


class HeatPump(EventServer):
    COIL_UPDATE_EVENT = "coil_update"

    _address_to_coil: Dict[str, Coil]
    _name_to_coil: Dict[str, Coil]
    word_swap: bool = True
    _product_info: Union[ProductInfo, None] = None
    _model: Union[Model, None] = None

    def __init__(self, model: Model = None):
        super().__init__()

        self._address_to_coil = {}
        self._name_to_coil = {}

        if model is not None:
            self.model = model

    @property
    def model(self) -> Union[Model, None]:
        return self._model

    @model.setter
    def model(self, model: Model):
        assert isinstance(model, Model), "Passed argument is not of a Model type"

        self._model = model

    @property
    def series(self) -> Series:
        if self._model in (
            Model.S1155,
            Model.S1255,
            Model.S320,
            Model.S325,
            Model.SMOS40,
        ):
            return Series.S
        return Series.F

    @property
    def product_info(self) -> Union[ProductInfo, None]:
        return self._product_info

    @product_info.setter
    def product_info(self, product_info: ProductInfo):
        assert isinstance(
            product_info, ProductInfo
        ), "Passed argument is not of a ProductInfo type"

        self._product_info = product_info

    async def _load_coils(self):
        data = await asyncio.get_running_loop().run_in_executor(
            None, self._model.get_coil_data
        )

        self._address_to_coil = {}
        for k, v in data.items():
            try:
                self._address_to_coil[k] = self._make_coil(address=int(k), **v)
            except (AssertionError, TypeError) as e:
                logger.warning(f"Failed to register coil {k}: {e}")
        self._name_to_coil = {c.name: c for _, c in self._address_to_coil.items()}

    def _make_coil(self, address: int, **kwargs):
        kwargs["word_swap"] = self.word_swap
        return Coil(address, **kwargs)

    async def initialize(self):
        if not isinstance(self._model, Model) and isinstance(
            self._product_info, ProductInfo
        ):
            self.model = self._product_info.identify_model()

        assert isinstance(
            self._model, Model
        ), "Model is not set and product info is not available"

        await self._load_coils()

    def get_coils(self) -> list[Coil]:
        return list(self._address_to_coil.values())

    def get_coil_by_address(self, address: Union[int, str]) -> Coil:
        try:
            return self._address_to_coil[str(address)]
        except KeyError:
            raise CoilNotFoundException(f"Coil with address {address} not found")

    def get_coil_by_name(self, name: str) -> Coil:
        try:
            return self._name_to_coil[str(name)]
        except KeyError:
            raise CoilNotFoundException(f"Coil with name '{name}' not found")

    def notify_coil_update(self, coil: Coil):
        self.notify_event_listeners(self.COIL_UPDATE_EVENT, coil)
