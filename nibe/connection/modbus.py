import asyncio
import logging

from async_modbus import modbus_for_url
import async_timeout

from nibe.coil import Coil
from nibe.connection import DEFAULT_TIMEOUT, Connection
from nibe.exceptions import CoilReadException, CoilWriteException
from nibe.heatpump import HeatPump

logger = logging.getLogger("nibe").getChild(__name__)


def split_modbus_data(coil: Coil):
    entity_type = (coil.address // 10000) - 1
    entity_address = (coil.address % 10000) - 1

    if coil.size in ("s32", "u32"):
        entity_count = 2
    else:
        entity_count = 1

    return entity_type, entity_address, entity_count


class Modbus(Connection):
    def __init__(self, heatpump: HeatPump, url, slave_id, conn_options=None):
        self._slave_id = slave_id
        self._heatpump = heatpump
        self._client = modbus_for_url(url, conn_options)

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        logger.debug("Sending read request")
        try:

            entity_type, entity_number, entity_count = split_modbus_data(coil)

            async with async_timeout.timeout(timeout):
                if entity_type == 4:
                    result = await self._client.read_input_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 3:
                    result = await self._client.read_holding_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 2:
                    result = await self._client.read_discrete_inputs(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 1:
                    result = await self._client.read_coils(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                else:
                    raise CoilReadException(f"Unsupported entity type {entity_type}")

            coil.raw_value = b"".join(result)

            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)
        except asyncio.TimeoutError:
            raise CoilReadException(
                f"Timeout waiting for read response for {coil.name}"
            )

        return coil

    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil.value is not None, f"{coil.name} value must be set"

        logger.debug("Sending write request")
        try:
            entity_type, entity_number, entity_count = split_modbus_data(coil)

            with async_timeout.timeout(timeout):
                if entity_type == 3:
                    result = await self._client.write_register(
                        slave_id=self._slave_id,
                        address=entity_number,
                        value=coil.raw_value,
                    )
                elif entity_type == 1:
                    result = await self._client.write_coil(
                        slave_id=self._slave_id,
                        address=entity_number,
                        value=coil.raw_value,
                    )
                else:
                    raise CoilReadException(f"Unsupported entity type {entity_type}")

            if not result:
                raise CoilWriteException(f"Heatpump denied writing {coil.name}")
            else:
                logger.info(f"Write succeeded for {coil.name}")
        except asyncio.TimeoutError:
            raise CoilWriteException(
                f"Timeout waiting for write feedback for {coil.name}"
            )

        return coil
