import json
import logging
from collections import defaultdict
from enum import Enum
from importlib.resources import files
from typing import Any, Callable, Dict, Union

from nibe.coil import Coil
from nibe.exceptions import CoilNotFoundException

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


class HeatPump:
    COIL_UPDATE_EVENT = "coil_update"

    _listeners: defaultdict[Any, list[Callable[..., None]]]
    _address_to_coil: Dict[str, Coil]
    _name_to_coil: Dict[str, Coil]
    word_swap: bool = True

    def __init__(self, model: Model):
        assert isinstance(model, Model)
        self.model = model

        self._listeners = defaultdict(list)

    def _load_coils(self):
        data = self.model.get_coil_data()

        self._address_to_coil = {
            k: self._make_coil(address=int(k), **v) for k, v in data.items()
        }
        self._name_to_coil = {c.name: c for _, c in self._address_to_coil.items()}

    def _make_coil(self, address: int, **kwargs):
        kwargs["word_swap"] = self.word_swap
        return Coil(address, **kwargs)

    def initialize(self):
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
        for listener in self._listeners[self.COIL_UPDATE_EVENT]:
            try:
                listener(coil)
            except Exception as e:
                logger.exception(e)

    def subscribe(self, event_name: str, callback: Callable[..., None]):
        self._listeners[event_name].append(callback)
