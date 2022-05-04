import asyncio
import logging
import socket
from asyncio import CancelledError, InvalidStateError
from binascii import hexlify
from contextlib import suppress
from functools import reduce
from io import BytesIO
from operator import xor

from construct import (Array, Bytes, Checksum, ChecksumError, Const, Enum, FixedSized,
                       Flag, Int8ub, Int16ul, RawCopy, Struct, Subconstruct, Switch,
                       this,)

from nibe.coil import Coil
from nibe.connection import Connection
from nibe.exceptions import (CoilReadException, CoilReadTimeoutException,
                             CoilWriteException, CoilWriteTimeoutException,
                             DecodeException, NibeException,)
from nibe.heatpump import HeatPump

logger = logging.getLogger("nibe").getChild(__name__)


class NibeGW(asyncio.DatagramProtocol, Connection):
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
                    try:
                        self._on_raw_coil_value(row.coil_address, row.value)
                    except DecodeException as e:
                        logger.error(str(e))
            elif cmd == "MODBUS_READ_RESP":
                row = msg.fields.value.data
                try:
                    self._on_raw_coil_value(row.coil_address, row.value)
                    with suppress(InvalidStateError, CancelledError, AttributeError):
                        self._read_future.set_result(None)
                except DecodeException as e:
                    with suppress(InvalidStateError, CancelledError, AttributeError):
                        self._read_future.set_exception(CoilReadException(str(e), e))
                    raise
            elif cmd == "MODBUS_WRITE_RESP":
                with suppress(InvalidStateError, CancelledError, AttributeError):
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
                e,
            )

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
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
                raise CoilReadTimeoutException(
                    f"Timeout waiting for read response for {coil.name}"
                )
            finally:
                self._read_future = None

            return coil

    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
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
                raise CoilWriteTimeoutException(
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
            raise DecodeException(f"Unable to decode: {coil_address} not found")

        coil.raw_value = raw_value
        logger.info(f"{coil.name}: {coil.value}")
        self._heatpump.notify_coil_update(coil)

    def stop(self):
        self._transport.close()
        self._transport = None


def xor8(data: bytes) -> int:
    chksum = reduce(xor, data)
    if chksum == 0x5C:
        chksum = 0xC5
    return chksum


class Dedupe5C(Subconstruct):
    def __init__(self, subcon):
        super().__init__(subcon)
        self.name = subcon.name

    def _parse(self, stream, context, path):
        unescaped = stream.getvalue().replace(b"\x5c\x5c", b"\x5c")
        context.length = len(unescaped)
        with BytesIO(unescaped) as stream2:
            obj = self.subcon._parsereport(stream2, context, path)
        return obj

    def _build(self, obj, stream, context, path):
        escaped = stream.getvalue().replace(b"\x5c", b"\x5c\x5c")
        context.length = len(escaped)
        with BytesIO(escaped) as stream2:
            buildret = self.subcon._build(obj, stream2, context, path)
        return obj


Data = Dedupe5C(
    Switch(
        this.cmd,
        {
            "MODBUS_READ_RESP": Struct("coil_address" / Int16ul, "value" / Bytes(4)),
            "MODBUS_DATA_MSG": Array(
                lambda this: this.length // 4,
                Struct("coil_address" / Int16ul, "value" / Bytes(2)),
            ),
            "MODBUS_WRITE_RESP": Struct("result" / Flag),
        },
        default=Bytes(this.length),
    )
)


Command = Enum(
    Int8ub,
    RMU_DATA_MSG=0x62,
    MODBUS_DATA_MSG=0x68,
    MODBUS_READ_REQ=0x69,
    MODBUS_READ_RESP=0x6A,
    MODBUS_WRITE_REQ=0x6B,
    MODBUS_WRITE_RESP=0x6C,
)


# fmt: off
Response = Struct(
    "start_byte" / Const(0x5C, Int8ub),
    "empty_byte" / Const(0x00, Int8ub),
    "fields" / RawCopy(
        Struct(
            "address" / Enum(
                Int8ub,
                # 0x13 = 19, ?
                SMS40=0x16,
                RMU40=0x19,
                MODBUS40=0x20,
            ),
            "cmd" / Command,
            "length" / Int8ub,
            "data" / FixedSized(this.length, Data),
        )
    ),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
).compile()


ReadRequest = Struct(
    "fields" / RawCopy(
        Struct(
            "start_byte" / Const(0xC0, Int8ub),
            "cmd" / Const(Command.MODBUS_READ_REQ, Command),
            "length" / Const(0x02, Int8ub),
            "coil_address" / Int16ul,
        )
    ),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
).compile()


WriteRequest = Struct(
    "fields" / RawCopy(
        Struct(
            "start_byte" / Const(0xC0, Int8ub),
            "cmd" / Const(Command.MODBUS_WRITE_REQ, Command),
            "length" / Const(0x06, Int8ub),
            "coil_address" / Int16ul,
            "value" / Bytes(4),
        )
    ),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
).compile()
# fmt: on
