from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable

from nibe.coil import Coil
from nibe.exceptions import CoilReadException, CoilReadExceptionGroup
from nibe.heatpump import HeatPump, ProductInfo, Series

DEFAULT_TIMEOUT: float = 5
READ_PRODUCT_INFO_TIMEOUT: float = 20  # Product info message is sent every 15 seconds


class Connection(ABC):
    async def start(self):  # noqa: B027
        pass

    async def stop(self):  # noqa: B027
        pass

    @abstractmethod
    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    async def read_coils(
        self, coils: Iterable[Coil], timeout: float = DEFAULT_TIMEOUT
    ) -> AsyncIterator[Coil]:
        exceptions = []
        for coil in coils:
            try:
                yield await self.read_coil(coil, timeout)
            except CoilReadException as exception:
                exceptions.append(exception)
        if exceptions:
            raise CoilReadExceptionGroup("Failed to read some or all coils", exceptions)

    @abstractmethod
    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        pass

    async def read_product_info(
        self, timeout: float = READ_PRODUCT_INFO_TIMEOUT
    ) -> ProductInfo:
        raise NotImplementedError(
            "read_product_info method is not implemented for this connection method"
        )

    @abstractmethod
    async def verify_connectivity(self):
        pass


async def verify_connectivity_read_write_alarm(
    connection: Connection, heatpump: HeatPump
):
    """Verify that we have functioning communication.

    To verify connection, we read the alarm reset field and write it as 0
    this will be ignored by the pump, this will throw exceptions on failure.
    """
    if heatpump.series == Series.S:
        coil = heatpump.get_coil_by_name("reset-alarm-40023")
    else:
        coil = heatpump.get_coil_by_name("alarm-reset-45171")

    coil = await connection.read_coil(coil)
    value: str | int = 0
    if coil.mappings:
        value = coil.mappings[str(value)]
    coil.value = value
    coil = await connection.write_coil(coil)
