import asyncio
import logging
import socket
from asyncio import CancelledError, InvalidStateError
from binascii import hexlify
from contextlib import suppress
from functools import reduce
from io import BytesIO
from operator import xor

from construct import (
    Array,
    Bytes,
    Checksum,
    ChecksumError,
    Const,
    Enum,
    FixedSized,
    Flag,
    GreedyString,
    Int8ub,
    Int16ub,
    Int16ul,
    RawCopy,
    Struct,
    Subconstruct,
    Switch,
    this,
)

from nibe.coil import Coil
from nibe.connection import DEFAULT_TIMEOUT, READ_PRODUCT_INFO_TIMEOUT, Connection
from nibe.event_server import EventServer
from nibe.exceptions import (
    CoilNotFoundException,
    CoilReadException,
    CoilReadTimeoutException,
    CoilWriteException,
    CoilWriteTimeoutException,
    NibeException,
    ProductInfoReadTimeoutException,
)
from nibe.heatpump import HeatPump, ProductInfo

logger = logging.getLogger("nibe").getChild(__name__)


class ConnectionStatus(Enum):
    UNKNOWN = None
    INITIALIZING = "initializing"
    LISTENING = "listening"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class NibeGW(asyncio.DatagramProtocol, Connection, EventServer):
    CONNECTION_STATUS_EVENT = "connection_status"

    def __init__(
        self,
        heatpump: HeatPump,
        remote_ip: str,
        remote_read_port: int = 9999,
        remote_write_port: int = 10000,
        listening_ip: str = "0.0.0.0",
        listening_port: int = 9999,
    ) -> None:
        super().__init__()

        self._heatpump = heatpump
        self._listening_ip = listening_ip
        self._listening_port = listening_port

        self._remote_ip = remote_ip
        self._remote_read_port = remote_read_port
        self._remote_write_port = remote_write_port

        self._transport = None
        self._status = ConnectionStatus.UNKNOWN

        self._send_lock = asyncio.Lock()
        self._futures = {}

    async def start(self):
        logger.info(f"Starting UDP server on port {self._listening_port}")

        self._set_status(ConnectionStatus.INITIALIZING)

        await asyncio.get_event_loop().create_datagram_endpoint(
            lambda: self,
            local_addr=(self._listening_ip, self._listening_port),
            proto=socket.IPPROTO_UDP,
        )

    def connection_made(self, transport):
        self._set_status(ConnectionStatus.LISTENING)
        self._transport = transport

    def datagram_received(self, data, addr):
        logger.debug(f"Received {hexlify(data)} from {addr}")
        self._set_status(ConnectionStatus.CONNECTED)
        try:
            msg = Response.parse(data)
            logger.debug(msg)
            cmd = msg.fields.value.cmd
            if cmd == "MODBUS_DATA_MSG":
                for row in msg.fields.value.data:
                    try:
                        self._on_raw_coil_value(row.coil_address, row.value)
                    except NibeException as e:
                        logger.error(str(e))
            elif cmd == "MODBUS_READ_RESP":
                row = msg.fields.value.data
                try:
                    self._on_raw_coil_value(row.coil_address, row.value)
                    with suppress(InvalidStateError, CancelledError, KeyError):
                        self._futures["read"].set_result(None)
                except NibeException as e:
                    with suppress(InvalidStateError, CancelledError, KeyError):
                        self._futures["read"].set_exception(
                            CoilReadException(str(e), e)
                        )
                    raise
            elif cmd == "MODBUS_WRITE_RESP":
                with suppress(InvalidStateError, CancelledError, KeyError):
                    self._futures["write"].set_result(msg.fields.value.data.result)
            elif cmd == "PRODUCT_INFO_MSG":
                with suppress(InvalidStateError, CancelledError, KeyError):
                    self._futures["product_info"].set_result(msg.fields.value.data)
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

    async def read_product_info(
        self, timeout: float = READ_PRODUCT_INFO_TIMEOUT
    ) -> ProductInfo:
        self._futures["product_info"] = asyncio.get_event_loop().create_future()
        try:
            result = await asyncio.wait_for(self._futures["product_info"], timeout)
            return ProductInfo(result["model"], result["version"])
        except asyncio.TimeoutError:
            raise ProductInfoReadTimeoutException(
                f"Timeout waiting for product message"
            )
        finally:
            del self._futures["product_info"]

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        async with self._send_lock:
            data = ReadRequest.build(
                dict(fields=dict(value=dict(coil_address=coil.address)))
            )

            self._futures["read"] = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data)} (read request) to {self._remote_ip}:{self._remote_write_port}"
            )
            self._transport.sendto(data, (self._remote_ip, self._remote_read_port))
            logger.debug(f"Waiting for read response for {coil.name}")

            try:
                await asyncio.wait_for(self._futures["read"], timeout)
            except asyncio.TimeoutError:
                raise CoilReadTimeoutException(
                    f"Timeout waiting for read response for {coil.name}"
                )
            finally:
                del self._futures["read"]

            return coil

    async def write_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil.value is not None, f"{coil.name} value must be set"
        async with self._send_lock:
            data = WriteRequest.build(
                dict(
                    fields=dict(
                        value=dict(coil_address=coil.address, value=coil.raw_value)
                    )
                )
            )

            self._futures["write"] = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data)} (write request) to {self._remote_ip}:{self._remote_write_port}"
            )
            self._transport.sendto(data, (self._remote_ip, self._remote_write_port))

            try:
                await asyncio.wait_for(self._futures["write"], timeout)

                result = self._futures["write"].result()

                if not result:
                    raise CoilWriteException(f"Heatpump denied writing {coil.name}")
                else:
                    logger.info(f"Write succeeded for {coil.name}")
            except asyncio.TimeoutError:
                raise CoilWriteTimeoutException(
                    f"Timeout waiting for write feedback for {coil.name}"
                )
            finally:
                del self._futures["write"]

            return coil

    def error_received(self, exc):
        logger.error(exc)

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def _set_status(self, status: ConnectionStatus):
        if status != self._status:
            self._status = status
            self.notify_event_listeners(self.CONNECTION_STATUS_EVENT, status=status)

    def _on_raw_coil_value(self, coil_address: int, raw_value: bytes):
        try:
            coil = self._heatpump.get_coil_by_address(coil_address)
        except CoilNotFoundException:
            if coil_address == 65535:  # 0xffff
                return
            raise

        coil.raw_value = raw_value
        logger.info(f"{coil.name}: {coil.value}")
        self._heatpump.notify_coil_update(coil)

    async def stop(self):
        self._transport.close()
        self._transport = None
        self._set_status(ConnectionStatus.DISCONNECTED)


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


ProductInfoData = Struct(
    "_unknown" / Bytes(1), "version" / Int16ub, "model" / GreedyString("ASCII")
)


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
            "PRODUCT_INFO_MSG": ProductInfoData,
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
    PRODUCT_INFO_MSG=0x6D,
)

Address = Enum(
    Int8ub,
    # 0x13 = 19, ?
    SMS40=0x16,
    RMU40_S1=0x19,
    RMU40_S2=0x1A,
    RMU40_S3=0x1B,
    RMU40_S4=0x1C,
    MODBUS40=0x20,
)

# fmt: off
Response = Struct(
    "start_byte" / Const(0x5C, Int8ub),
    "empty_byte" / Const(0x00, Int8ub),
    "fields" / RawCopy(
        Struct(
            "address" / Address,
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
