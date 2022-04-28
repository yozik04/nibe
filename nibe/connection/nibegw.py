import asyncio
import logging
import socket
from binascii import hexlify

from construct import ChecksumError

from nibe.coil import Coil
from nibe.exceptions import (CoilReadException, CoilWriteException, DecodeException,
                             NibeException)
from nibe.heatpump import HeatPump
from nibe.parsers import ReadRequest, Response, WriteRequest

logger = logging.getLogger("nibe").getChild(__name__)


class NibeGW(asyncio.DatagramProtocol):
    DEFAULT_TIMEOUT = 5

    def __init__(
        self,
        heatpump: HeatPump,
        remote_ip: str,
        remote_read_port: int = 9999,
        remote_write_port: int = 10000,
        listening_ip: str = "0.0.0.0",
        listening_port: int = 9999,
    ) -> None:
        self._heatpump = heatpump
        self._listening_ip = listening_ip
        self._listening_port = listening_port

        self._remote_ip = remote_ip
        self._remote_read_port = remote_read_port
        self._remote_write_port = remote_write_port

        self._transport = None

        self._send_lock = asyncio.Lock()
        self._write_future = None
        self._read_future = None

    async def start(self):
        logger.info(f"Starting UDP server on port {self._listening_port}")

        await asyncio.get_event_loop().create_datagram_endpoint(
            lambda: self,
            local_addr=(self._listening_ip, self._listening_port),
            proto=socket.IPPROTO_UDP,
        )

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, addr):
        logger.debug(f"Received {hexlify(data)} from {addr}")
        try:
            msg = Response.parse(data)
            logger.debug(msg)
            cmd = msg.fields.value.cmd
            if cmd == "MODBUS_DATA_MSG":
                for row in msg.fields.value.data:
                    self._on_raw_coil_value(row.coil_address, row.value)
            elif cmd == "MODBUS_READ_RESP":
                row = msg.fields.value.data
                self._on_raw_coil_value(row.coil_address, row.value)
                if self._read_future and not self._read_future.done():
                    self._read_future.set_result(None)
            elif cmd == "MODBUS_WRITE_RESP":
                if self._write_future and not self._write_future.done():
                    self._write_future.set_result(msg.fields.value.data.result)
            else:
                logger.debug(f"Unknown command {cmd}")
        except ChecksumError:
            logger.warning(
                f"Ignoring packet from {addr} due to checksum error: {hexlify(data)}"
            )
        except NibeException as e:
            logger.error(f"Failed handling packet from {addr}: {e}")
        except Exception as e:
            logger.exception(
                f"Unexpected exception during parsing packet data '{hexlify(data)}' from {addr}",
                e
            )

    async def read_coil(self, coil: Coil, timeout: int = DEFAULT_TIMEOUT) -> Coil:
        async with self._send_lock:
            data = ReadRequest.build(
                dict(fields=dict(value=dict(coil_address=coil.address)))
            )

            self._read_future = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data)} (read request) to {self._remote_ip}:{self._remote_write_port}"
            )
            self._transport.sendto(data, (self._remote_ip, self._remote_read_port))
            logger.debug(f"Waiting for read response for {coil.name}")

            try:
                await asyncio.wait_for(self._read_future, timeout)
            except asyncio.TimeoutError:
                raise CoilReadException(
                    f"Timeout waiting for read response for {coil.name}"
                )
            finally:
                self._read_future = None

            return coil

    async def write_coil(self, coil: Coil, timeout: int = DEFAULT_TIMEOUT) -> Coil:
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil.value is not None
        async with self._send_lock:
            data = WriteRequest.build(
                dict(
                    fields=dict(
                        value=dict(coil_address=coil.address, value=coil.raw_value)
                    )
                )
            )

            self._write_future = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data)} (write request) to {self._remote_ip}:{self._remote_write_port}"
            )
            self._transport.sendto(data, (self._remote_ip, self._remote_write_port))

            try:
                await asyncio.wait_for(self._write_future, timeout)

                result = self._write_future.result()

                if not result:
                    raise CoilWriteException(f"Heatpump denied writing {coil.name}")
                else:
                    logger.info(f"Write succeeded for {coil.name}")
            except asyncio.TimeoutError:
                raise CoilWriteException(
                    f"Timeout waiting for write feedback for {coil.name}"
                )
            finally:
                self._write_future = None

            return coil

    def error_received(self, exc):
        logger.error(exc)

    def _on_raw_coil_value(self, coil_address: int, raw_value: bytes):
        coil = self._heatpump.get_coil_by_address(coil_address)
        if not coil:
            logger.warning(f"Unable to decode: {coil_address} not found")
            return

        try:
            coil.raw_value = raw_value
            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)
        except DecodeException as e:
            logger.error(f"Unable to decode: {e}")

    def stop(self):
        self._transport.close()
        self._transport = None
