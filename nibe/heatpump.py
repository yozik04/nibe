import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from typing import Any, Callable, Dict, Union

from nibe.coil import Coil
from nibe.exceptions import CoilNotFoundException, ModelIdentificationFailed

logger = logging.getLogger("nibe").getChild(__name__)


class Model(Enum):
    F1155 = "f1155_f1255"
    F1255 = "f1155_f1255"

    F1145 = "f1145_f1245"
    F1245 = "f1145_f1245"

    F1345 = "f1345"
    F1355 = "f1355"

    F730 = "f730"
    F750 = "f750"

    F370 = "f370_f470"
    F470 = "f370_f470"

    SMO20 = "smo20"
    SMO40 = "smo40"

    VVM225 = "vvm225_vvm320_vvm325"
    VVM320 = "vvm225_vvm320_vvm325"
    VVM325 = "vvm225_vvm320_vvm325"

    VVM310 = "vvm310_vvm500"
    VVM500 = "vvm310_vvm500"

    def get_coil_data(self):
        return json.loads(files("nibe.data").joinpath(f"{self.value}.json").read_text())

    @classmethod
    def keys(cls):
        return cls.__members__.keys()


@dataclass
class ProductInfo:
    model: str
    firmware_version: int

    def infer_model(self) -> Model:
        for key in Model.keys():
            if key in self.model.upper():
                return getattr(Model, key)

        raise ModelIdentificationFailed(f'Unable to identify model from "{self.model}"')


class HeatPump:
    COIL_UPDATE_EVENT = "coil_update"

    _listeners: defaultdict[Any, list[Callable[..., None]]]
    _address_to_coil: Dict[str, Coil]
    _name_to_coil: Dict[str, Coil]
    word_swap: bool = True
    _product_info: Union[ProductInfo, None] = None
    _model: Union[Model, None] = None

    def __init__(self, model: Model = None):
        if model is not None:
            self.model = model

        self._listeners = defaultdict(list)

    @property
    def model(self) -> Union[Model, None]:
        return self._model

    @model.setter
    def model(self, model: Model):
        assert isinstance(model, Model), "Passed argument is not of a Model type"

        self._model = model

    @property
    def product_info(self) -> Union[ProductInfo, None]:
        return self._product_info

    @product_info.setter
    def product_info(self, product_info: ProductInfo):
        assert isinstance(
            product_info, ProductInfo
        ), "Passed argument is not of a ProductInfo type"

        self._product_info = product_info

    def _load_coils(self):
        data = self._model.get_coil_data()

        self._address_to_coil = {
            k: self._make_coil(address=int(k), **v) for k, v in data.items()
        }
        self._name_to_coil = {c.name: c for _, c in self._address_to_coil.items()}

    def _make_coil(self, address: int, **kwargs):
        kwargs["word_swap"] = self.word_swap
        return Coil(address, **kwargs)

    def initialize(self):
        if not isinstance(self._model, Model) and isinstance(
            self._product_info, ProductInfo
        ):
            self.model = self._product_info.infer_model()

        assert isinstance(
            self._model, Model
        ), "Model is not set and product info is not available"

        self._load_coils()

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

    def notify_event_listeners(self, event_name: str, *args, **kwargs):
        for listener in self._listeners[event_name]:
            try:
                listener(*args, **kwargs)
            except Exception as e:
                logger.exception(e)

    def subscribe(self, event_name: str, callback: Callable[..., None]):
        self._listeners[event_name].append(callback)
