from abc import ABC, abstractmethod

from nibe.coil import Coil


class Connection(ABC):
    DEFAULT_TIMEOUT = 5.0

    @abstractmethod
    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    @abstractmethod
    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass
