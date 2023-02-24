from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable

from nibe.coil import Coil, CoilData
from nibe.exceptions import ReadExceptionGroup, ReadIOException
from nibe.heatpump import HeatPump, ProductInfo, Series

DEFAULT_TIMEOUT: float = 5
READ_PRODUCT_INFO_TIMEOUT: float = 20  # Product info message is sent every 15 seconds


class Connection(ABC):
    """Base class for all connection methods."""

    async def start(self):  # noqa: B027
        """Start the connection."""
        pass

    async def stop(self):  # noqa: B027
        """Close the connection."""
        pass

    @abstractmethod
    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> CoilData:
        """Read a coil data from the heatpump.

        :raises ReadIOException: If failed to read coil data due to IO error (will retry).
        :raises ReadException: If failed to read coil data due to other error (will not retry).
        """
        pass

    async def read_coils(
        self, coils: Iterable[Coil], timeout: float = DEFAULT_TIMEOUT
    ) -> AsyncIterator[CoilData]:
        """Read multiple coil data from the heatpump.

        :raises ReadExceptionGroup: If one or more coils failed to read."""
        exceptions = []
        for coil in coils:
            try:
                yield await self.read_coil(coil, timeout)
            except ReadIOException as exception:
                exceptions.append(exception)
        if exceptions:
            raise ReadExceptionGroup("Failed to read some or all coils", exceptions)

    @abstractmethod
    async def write_coil(
        self, coil_data: CoilData, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        """Write a coil data to the heatpump.

        :raises WriteIOException: If failed to write coil data due to IO error (will retry).
        :raises WriteException: If failed to write coil data due to other error (will not retry).
        """
        pass

    async def read_product_info(
        self, timeout: float = READ_PRODUCT_INFO_TIMEOUT
    ) -> ProductInfo:
        """Read product info from the heatpump.

        :raises ReadIOException: If failed to read product info in time."""
        raise NotImplementedError(
            "read_product_info method is not implemented for this connection method"
        )

    @abstractmethod
    async def verify_connectivity(self):
        """Verify that we have functioning communication.

        :raises NibeException: If failed to verify connectivity."""
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

    coil_data = await connection.read_coil(coil)
    value: str | int = 0
    if coil.mappings:
        value = coil.mappings[str(value)]
    coil_data.value = value
    await connection.write_coil(coil_data)
