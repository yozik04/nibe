import asyncio
import logging

from async_modbus import modbus_for_url
import async_timeout
from tenacity import retry, retry_if_exception_type, stop_after_attempt
from umodbus.exceptions import ModbusError

from nibe.coil import Coil, CoilData
from nibe.connection import DEFAULT_TIMEOUT, Connection
from nibe.connection.encoders import CoilDataEncoderModbus
from nibe.exceptions import (
    DecodeException,
    ModbusUrlException,
    ReadException,
    ReadIOException,
    ReadTimeoutException,
    ValidationError,
    WriteDeniedException,
    WriteIOException,
    WriteTimeoutException,
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


class Modbus(Connection):
    """Modbus connection."""

    def __init__(
        self,
        heatpump: HeatPump,
        url,
        slave_id,
        conn_options=None,
        read_retries: int = 3,
        write_retries: int = 3,
    ):
        self._slave_id = slave_id
        self._heatpump = heatpump

        self.read_coil = retry(
            retry=retry_if_exception_type(ReadIOException),
            stop=stop_after_attempt(read_retries),
            reraise=True,
        )(self.read_coil)

        self.write_coil = retry(
            retry=retry_if_exception_type(WriteIOException),
            stop=stop_after_attempt(write_retries),
            reraise=True,
        )(self.write_coil)

        try:
            self._client = modbus_for_url(url, conn_options)
        except ValueError as exc:
            raise ModbusUrlException(str(exc)) from exc

        self.coil_encoder = CoilDataEncoderModbus(heatpump.word_swap)

    async def stop(self) -> None:
        await self._client.stream.close()

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> CoilData:
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
                    raise ReadException(f"Unsupported entity type {entity_type}")

            coil_data = self.coil_encoder.decode(coil, result)

            logger.info(coil_data)
            self._heatpump.notify_coil_update(coil_data)
        except (ModbusError, asyncio.IncompleteReadError) as exc:
            raise ReadIOException(
                f"Error '{str(exc)}' reading {coil.name} starting: {entity_number} count: {entity_count} from: {self._slave_id}"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise ReadTimeoutException(
                f"Timeout waiting for read response for {coil.name}"
            ) from exc
        except (DecodeException, ValidationError) as exc:
            raise ReadException(f"Failed decoding response for {coil.name}") from exc

        return coil_data

    async def write_coil(
        self, coil_data: CoilData, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        coil = coil_data.coil
        assert coil.is_writable, f"{coil.name} is not writable"

        entity_type, entity_number, entity_count = split_modbus_data(coil)
        try:
            values = self.coil_encoder.encode(coil_data)

            logger.debug("Sending write request")
            async with async_timeout.timeout(timeout):
                if entity_type == 4:
                    result = await self._client.write_registers(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        values=values,
                    )
                elif entity_type == 0:
                    result = await self._client.write_coils(
                        slave_id=self._slave_id,
                        starting_address=entity_number,
                        values=values,
                    )
                else:
                    raise ReadIOException(f"Unsupported entity type {entity_type}")

            if not result:
                raise WriteDeniedException(f"Heatpump denied writing {coil.name}")
            else:
                logger.info(f"Write succeeded for {coil.name}")
        except ValidationError as exc:
            raise WriteIOException(
                f"Error validating {coil.name} coil value: {str(exc)}"
            ) from exc
        except (ModbusError, asyncio.IncompleteReadError) as exc:
            raise WriteIOException(
                f"Error '{str(exc)}' writing {coil.name} starting: {entity_number} count: {entity_count} to: {self._slave_id}"
            ) from exc
        except asyncio.TimeoutError:
            raise WriteTimeoutException(
                f"Timeout waiting for write feedback for {coil.name}"
            )

    async def verify_connectivity(self):
        await verify_connectivity_read_write_alarm(self, self._heatpump)
