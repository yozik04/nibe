import asyncio
import logging

from async_modbus import modbus_for_url

from nibe.coil import Coil
from nibe.connection import Connection
from nibe.exceptions import CoilReadException, CoilWriteException, DecodeException
from nibe.heatpump import HeatPump

logger = logging.getLogger("nibe").getChild(__name__)


class Modbus(Connection):
    DEFAULT_TIMEOUT = 5

    def __init__(self, heatpump: HeatPump, url, slave_id, conn_options=None):
        self._slave_id = slave_id
        self._heatpump = heatpump
        self._client = modbus_for_url(url, conn_options)

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        logger.debug(f"Sending read request")
        try:
            result = await asyncio.wait_for(
                self._client.read_coils(
                    slave_id=self._slave_id, starting_address=coil.address, quantity=1
                ),
                timeout,
            )
            coil.raw_value = result[0]
            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)
        except asyncio.TimeoutError:
            raise CoilReadException(
                f"Timeout waiting for read response for {coil.name}"
            )

        return coil

    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil.value is not None

        logger.debug(f"Sending write request")
        try:
            result = await asyncio.wait_for(
                self._client.write_coil(
                    slave_id=self._slave_id, address=coil.address, value=coil.raw_value
                ),
                timeout,
            )

            if not result:
                raise CoilWriteException(f"Heatpump denied writing {coil.name}")
            else:
                logger.info(f"Write succeeded for {coil.name}")
        except asyncio.TimeoutError:
            raise CoilWriteException(
                f"Timeout waiting for write feedback for {coil.name}"
            )

        return coil
