from abc import ABC, abstractmethod
from dataclasses import dataclass

from nibe.coil import Coil

DEFAULT_TIMEOUT: float = 5
READ_PRODUCT_TIMEOUT: float = 20  # Product message is sent every 15 seconds


@dataclass
class Product:
    model: str
    version: int


class Connection(ABC):
    async def start(self):
        pass

    async def stop(self):
        pass

    @abstractmethod
    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    @abstractmethod
    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    async def read_product(self, timeout: float = READ_PRODUCT_TIMEOUT) -> Product:
        raise NotImplemented(
            "read_product method is not implemented for this connection method"
        )
