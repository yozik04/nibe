import asyncio
import logging
from typing import List

from async_modbus import modbus_for_url
import async_timeout
from umodbus.exceptions import ModbusError

from nibe.coil import Coil
from nibe.connection import DEFAULT_TIMEOUT, Connection
from nibe.connection.encoders import CoilDataEncoder
from nibe.exceptions import (
    CoilReadException,
    CoilReadTimeoutException,
    CoilWriteException,
    CoilWriteTimeoutException,
    ModbusUrlException,
)
from nibe.heatpump import HeatPump

from . import verify_connectivity_read_write_alarm

logger = logging.getLogger("nibe").getChild(__name__)


def split_modbus_data(coil: Coil):
    entity_type = coil.address // 10000
    entity_address = (coil.address % 10000) - 1

    if coil.size in ("s32", "u32"):
        entity_count = 2
    else:
        entity_count = 1

    return entity_type, entity_address, entity_count


def decode_u16_list(data: bytes, count: int) -> List[int]:
    """Split data into chunks of a certain max length, cropping of trailing data."""
    res = []
    for i in range(0, count * 2, 2):
        res.append(int.from_bytes(data[i : i + 2], "little", signed=False))
    return res


def encode_u16_list(data: List[int]) -> bytes:
    return bytes(
        byte for val in data for byte in int(val).to_bytes(2, "little", signed=False)
    )


def split_chunks(data, max_len, chunks) -> List[int]:
    """Split data into chunks of a certain max length, cropping of trailing data."""
    count = len(data) // chunks
    res = []
    for i in range(0, len(data), count):
        chunk = data[i : i + count]
        assert all(x == 0 for x in chunk[max_len:])
        res.append(int.from_bytes(chunk[0:max_len], "little"), signed=False)
    return res


class Modbus(Connection):
    def __init__(self, heatpump: HeatPump, url, slave_id, conn_options=None):
        self._slave_id = slave_id
        self._heatpump = heatpump

        try:
            self._client = modbus_for_url(url, conn_options)
        except ValueError as exc:
            raise ModbusUrlException(str(exc)) from exc

        self.coil_encoder = CoilDataEncoder(heatpump.word_swap)

    async def stop(self) -> None:
        await self._client.stream.close()

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        logger.debug("Sending read request")
        entity_type, entity_number, entity_count = split_modbus_data(coil)

        try:

            async with async_timeout.timeout(timeout):
                if entity_type == 3:
                    result = await self._client.read_input_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 4:
                    result = await self._client.read_holding_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 1:
                    result = await self._client.read_discrete_inputs(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                elif entity_type == 0:
                    result = await self._client.read_coils(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        quantity=entity_count,
                    )
                else:
                    raise CoilReadException(f"Unsupported entity type {entity_type}")

            coil.value = self.coil_encoder.decode(coil, encode_u16_list(result))

            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)
        except ModbusError as exc:
            raise CoilReadException(
                f"Error '{str(exc)}' reading {coil.name} starting: {entity_number} count: {entity_count} from: {self._slave_id}"
            ) from exc
        except asyncio.TimeoutError:
            raise CoilReadTimeoutException(
                f"Timeout waiting for read response for {coil.name}"
            )

        return coil

    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil.value is not None, f"{coil.name} value must be set"

        logger.debug("Sending write request")

        entity_type, entity_number, entity_count = split_modbus_data(coil)
        try:

            async with async_timeout.timeout(timeout):
                if entity_type == 4:
                    result = await self._client.write_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        values=decode_u16_list(
                            self.coil_encoder.encode(coil), entity_count
                        ),
                    )
                elif entity_type == 0:
                    result = await self._client.write_coils(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        values=decode_u16_list(
                            self.coil_encoder.encode(coil), entity_count
                        ),
                    )
                else:
                    raise CoilReadException(f"Unsupported entity type {entity_type}")

            if not result:
                raise CoilWriteException(f"Heatpump denied writing {coil.name}")
            else:
                logger.info(f"Write succeeded for {coil.name}")
        except ModbusError as exc:
            raise CoilWriteException(
                f"Error '{str(exc)}' writing {coil.name} starting: {entity_number} count: {entity_count} to: {self._slave_id}"
            ) from exc
        except asyncio.TimeoutError:
            raise CoilWriteTimeoutException(
                f"Timeout waiting for write feedback for {coil.name}"
            )

        return coil

    async def verify_connectivity(self):
        """Verify that we have functioning communication."""
        await verify_connectivity_read_write_alarm(self, self._heatpump)
