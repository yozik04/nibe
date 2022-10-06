from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable

from nibe.coil import Coil
from nibe.heatpump import ProductInfo

DEFAULT_TIMEOUT: float = 5
READ_PRODUCT_INFO_TIMEOUT: float = 20  # Product info message is sent every 15 seconds


class Connection(ABC):
    async def start(self):
        pass

    async def stop(self):
        pass

    @abstractmethod
    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    async def read_coils(
        self, coils: Iterable[Coil], timeout: float = DEFAULT_TIMEOUT
    ) -> AsyncIterator[Coil]:
        for coil in coils:
            yield await self.read_coil(coil, timeout)

    @abstractmethod
    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    async def read_product_info(
        self, timeout: float = READ_PRODUCT_INFO_TIMEOUT
    ) -> ProductInfo:
        raise NotImplementedError(
            "read_product_info method is not implemented for this connection method"
        )
