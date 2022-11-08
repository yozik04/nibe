import asyncio
from asyncio import CancelledError, Future, InvalidStateError
from binascii import hexlify
from contextlib import suppress
import errno
from functools import reduce
from io import BytesIO
from ipaddress import ip_address
import logging
from operator import xor
import socket
import struct
from typing import Container, Dict, Optional, Union

from construct import (
    Adapter,
    Array,
    BitStruct,
    Bytes,
    Checksum,
    ChecksumError,
    Const,
    Enum,
    EnumIntegerString,
    FixedSized,
    Flag,
    FlagsEnum,
    GreedyBytes,
    GreedyString,
    IfThenElse,
    Int8sb,
    Int8ub,
    Int16sl,
    Int16ub,
    Int16ul,
    NullTerminated,
    Pointer,
    Prefixed,
    RawCopy,
    Select,
    StringEncoded,
    Struct,
    Subconstruct,
    Switch,
    Union as UnionConstruct,
    this,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from nibe.coil import Coil
from nibe.connection import DEFAULT_TIMEOUT, READ_PRODUCT_INFO_TIMEOUT, Connection
from nibe.connection.encoders import CoilDataEncoder
from nibe.event_server import EventServer
from nibe.exceptions import (
    AddressInUseException,
    CoilNotFoundException,
    CoilReadException,
    CoilReadSendException,
    CoilReadTimeoutException,
    CoilWriteException,
    CoilWriteSendException,
    CoilWriteTimeoutException,
    DecodeException,
    NibeException,
    ProductInfoReadTimeoutException,
)
from nibe.heatpump import HeatPump, ProductInfo

from . import verify_connectivity_read_write_alarm

logger = logging.getLogger("nibe").getChild(__name__)


class ConnectionStatus(Enum):
    UNKNOWN = "unknown"
    INITIALIZING = "initializing"
    LISTENING = "listening"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

    def __str__(self):
        return self.value


class NibeGW(asyncio.DatagramProtocol, Connection, EventServer):
    CONNECTION_STATUS_EVENT = "connection_status"
    _futures: Dict[str, Future]
    _status: ConnectionStatus

    def __init__(
        self,
        heatpump: HeatPump,
        remote_ip: Optional[str] = None,
        remote_read_port: int = 9999,
        remote_write_port: int = 10000,
        listening_ip: str = "0.0.0.0",
        listening_port: int = 9999,
        read_retries: int = 3,
        write_retries: int = 3,
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

        self.coil_encoder = CoilDataEncoder(heatpump.word_swap)

        self.read_coil = retry(
            retry=retry_if_exception_type(CoilReadException),
            stop=stop_after_attempt(read_retries),
            reraise=True,
        )(self.read_coil)

        self.write_coil = retry(
            retry=retry_if_exception_type(CoilWriteException),
            stop=stop_after_attempt(write_retries),
            reraise=True,
        )(self.write_coil)

    async def start(self):
        logger.info(f"Starting UDP server on port {self._listening_port}")

        self._set_status(ConnectionStatus.INITIALIZING)

        family, type, proto, _, sockaddr = socket.getaddrinfo(
            self._listening_ip,
            self._listening_port,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP,
            family=socket.AddressFamily.AF_INET,
        )[0]

        sock = socket.socket(family, type, proto)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        try:
            if ip_address(sockaddr[0]).is_multicast:
                group_bin = socket.inet_pton(family, sockaddr[0])
                if family == socket.AF_INET:  # IPv4
                    sock.bind(("", sockaddr[1]))
                    mreq = group_bin + struct.pack("=I", socket.INADDR_ANY)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                else:
                    sock.bind(("", sockaddr[1]))
                    mreq = group_bin + struct.pack("@I", 0)
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)
            elif self._listening_ip:
                sock.bind(sockaddr)
            else:
                sock.bind(("", sockaddr[1]))
        except OSError as exception:
            if exception.errno == errno.EADDRINUSE:
                raise AddressInUseException(f"Address in use {sockaddr}")
            raise

        await asyncio.get_event_loop().create_datagram_endpoint(lambda: self, sock=sock)

    def connection_made(self, transport):
        self._set_status(ConnectionStatus.LISTENING)
        self._transport = transport

    def datagram_received(self, data: bytes, addr):
        logger.debug(f"Received {hexlify(data).decode('utf-8')} from {addr}")
        try:
            msg = Response.parse(data)

            if not self._remote_ip:
                logger.debug("Pump discovered at %s", addr)
                self._remote_ip = addr[0]

            self._set_status(ConnectionStatus.CONNECTED)

            logger.debug(msg.fields.value)
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
            elif cmd == "RMU_DATA_MSG":
                self._on_rmu_data(msg.fields.value)
            elif cmd == "PRODUCT_INFO_MSG":
                with suppress(InvalidStateError, CancelledError, KeyError):
                    self._futures["product_info"].set_result(msg.fields.value.data)
            elif not isinstance(cmd, EnumIntegerString):
                logger.debug(f"Unknown command {cmd}")
        except ChecksumError:
            logger.warning(
                f"Ignoring packet from {addr} due to checksum error: {hexlify(data).decode('utf-8')}"
            )
        except NibeException as e:
            logger.error(f"Failed handling packet from {addr}: {e}")
        except Exception as e:
            logger.exception(
                f"Unexpected exception during parsing packet data '{hexlify(data).decode('utf-8')}' from {addr}",
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
            raise ProductInfoReadTimeoutException("Timeout waiting for product message")
        finally:
            del self._futures["product_info"]

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> Coil:
        async with self._send_lock:
            assert self._transport, "Transport is closed"
            data = Request.build(
                dict(
                    fields=dict(
                        value=dict(
                            cmd="MODBUS_READ_REQ", data=dict(coil_address=coil.address)
                        )
                    )
                )
            )

            self._futures["read"] = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data).decode('utf-8')} (read request) to {self._remote_ip}:{self._remote_write_port}"
            )

            try:
                self._transport.sendto(data, (self._remote_ip, self._remote_read_port))
            except socket.gaierror:
                raise CoilReadSendException(
                    f"Unable to lookup hostname: {self._remote_ip}"
                )

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
            assert self._transport, "Transport is closed"
            data = Request.build(
                dict(
                    fields=dict(
                        value=dict(
                            cmd="MODBUS_WRITE_REQ",
                            data=dict(
                                coil_address=coil.address,
                                value=self.coil_encoder.encode(coil),
                            ),
                        )
                    )
                )
            )

            self._futures["write"] = asyncio.get_event_loop().create_future()

            logger.debug(
                f"Sending {hexlify(data).decode('utf-8')} (write request) to {self._remote_ip}:{self._remote_write_port}"
            )

            try:
                self._transport.sendto(data, (self._remote_ip, self._remote_write_port))
            except socket.gaierror:
                raise CoilWriteSendException(
                    f"Unable to lookup hostname: {self._remote_ip}"
                )

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

    @property
    def remote_ip(self) -> str:
        return self._remote_ip

    def _set_status(self, status: ConnectionStatus):
        if status != self._status:
            self._status = status
            self.notify_event_listeners(self.CONNECTION_STATUS_EVENT, status=status)

    def _on_rmu_data(self, value: Container):
        data = value.data
        self._on_coil_value(40004, data.bt1_outdoor_temperature)
        self._on_coil_value(40013, data.bt7_hw_top)

        if data.flags.use_room_sensor_s1:
            self._on_coil_value(47398, data.setpoint_or_offset_s1)
        else:
            self._on_coil_value(47011, data.setpoint_or_offset_s1)

        if data.flags.use_room_sensor_s2:
            self._on_coil_value(47397, data.setpoint_or_offset_s2)
        else:
            self._on_coil_value(47010, data.setpoint_or_offset_s2)

        if data.flags.use_room_sensor_s3:
            self._on_coil_value(47396, data.setpoint_or_offset_s3)
        else:
            self._on_coil_value(47009, data.setpoint_or_offset_s3)

        if data.flags.use_room_sensor_s4:
            self._on_coil_value(47395, data.setpoint_or_offset_s4)
        else:
            self._on_coil_value(47008, data.setpoint_or_offset_s4)

        if data.operational_mode == "MANUAL":
            self._on_coil_value(47370, data.flags.allow_additive_heating)
            self._on_coil_value(47371, data.flags.allow_heating)
            self._on_coil_value(47372, data.flags.allow_cooling)

        self._on_coil_value(48132, data.temporary_lux)
        self._on_coil_value(45001, data.alarm)
        self._on_coil_value(47137, data.operational_mode)
        self._on_coil_value(47387, data.flags.hw_production)

        if coil_address := ADDRESS_TO_ROOM_TEMP_COIL.get(value.address):
            self._on_coil_value(coil_address, data.bt50_room_temp_sX)

    def _on_raw_coil_value(self, coil_address: int, raw_value: bytes):
        try:
            coil = self._heatpump.get_coil_by_address(coil_address)
            coil.value = self.coil_encoder.decode(coil, raw_value)

            # coil.raw_value = raw_value
            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)
        except CoilNotFoundException:
            if coil_address == 65535:  # 0xffff
                return

            logger.warning(
                f"Ignoring coil {coil_address} value - coil definition not found"
            )
            return
        except DecodeException:
            logger.warning(
                f"Ignoring coil {coil_address} value - failed to decode raw value: {hexlify(raw_value).decode('utf-8')}"
            )
            return

    def _on_coil_value(self, coil_address: int, value: Union[float, int, str]):
        try:
            coil = self._heatpump.get_coil_by_address(coil_address)

            if isinstance(value, bool):
                value = 1 if value else 0

            if isinstance(value, EnumIntegerString):
                value = int(value)

            if coil.has_mappings and isinstance(value, int):
                value = coil.get_mapping_for(value)

            coil.value = value
            logger.info(f"{coil.name}: {coil.value}")
            self._heatpump.notify_coil_update(coil)

        except CoilNotFoundException:
            if coil_address == 65535:  # 0xffff
                return

            logger.warning(
                f"Ignoring coil {coil_address} value - coil definition not found"
            )
            return
        except DecodeException:
            logger.warning(
                f"Ignoring coil {coil_address} value - failed to decode value: {value}"
            )
            return

    async def verify_connectivity(self):
        """Verify that we have functioning communication."""
        await verify_connectivity_read_write_alarm(self, self._heatpump)

    async def stop(self):
        self._transport.close()
        self._transport = None
        await asyncio.sleep(0)
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
            self.subcon._build(obj, stream2, context, path)
        return obj


ProductInfoData = Struct(
    "_unknown" / Bytes(1), "version" / Int16ub, "model" / GreedyString("ASCII")
)


class FixedPoint(Adapter):
    def __init__(self, subcon, scale, offset, ndigits=1) -> None:
        super().__init__(subcon)
        self._offset = offset
        self._scale = scale
        self._ndigits = ndigits

    def _decode(self, obj, context, path):
        return round(obj * self._scale + self._offset, self._ndigits)

    def _encode(self, obj, context, path):
        return (obj - self._offset) / self._scale


StringData = Struct(
    "unknown" / Int8ub,
    "id" / Int16ul,
    "string" / StringEncoded(NullTerminated(GreedyBytes), "ISO-8859-1"),
)

RmuData = Struct(
    "flags"
    / Pointer(
        15,
        BitStruct(
            "unknown_8000" / Flag,
            "unknown_4000" / Flag,
            "unknown_2000" / Flag,
            "unknown_1000" / Flag,
            "unknown_0800" / Flag,
            "allow_cooling" / Flag,
            "allow_heating" / Flag,
            "allow_additive_heating" / Flag,
            "use_room_sensor_s4" / Flag,
            "use_room_sensor_s3" / Flag,
            "use_room_sensor_s2" / Flag,
            "use_room_sensor_s1" / Flag,
            "unknown_0008" / Flag,
            "unknown_0004" / Flag,
            "unknown_0002" / Flag,
            "hw_production" / Flag,
        ),
    ),
    "bt1_outdoor_temperature" / FixedPoint(Int16sl, 0.1, -0.5),
    "bt7_hw_top" / FixedPoint(Int16sl, 0.1, -0.5),
    "setpoint_or_offset_s1"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s1,
        FixedPoint(Int8ub, 0.1, 5.0),
        FixedPoint(Int8sb, 0.1, 0),
    ),
    "setpoint_or_offset_s2"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s2,
        FixedPoint(Int8ub, 0.1, 5.0),
        FixedPoint(Int8sb, 0.1, 0),
    ),
    "setpoint_or_offset_s3"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s3,
        FixedPoint(Int8ub, 0.1, 5.0),
        FixedPoint(Int8sb, 0.1, 0),
    ),
    "setpoint_or_offset_s4"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s4,
        FixedPoint(Int8ub, 0.1, 5.0),
        FixedPoint(Int8sb, 0.1, 0),
    ),
    "bt50_room_temp_sX" / FixedPoint(Int16sl, 0.1, -0.5),
    "temporary_lux" / Int8ub,
    "hw_time_hour" / Int8ub,
    "hw_time_min" / Int8ub,
    "fan_mode" / Int8ub,
    "operational_mode" / Int8ub,
    "_flags" / Bytes(2),
    "clock_time_hour" / Int8ub,
    "clock_time_min" / Int8ub,
    "alarm" / Int8ub,
    "unknown4" / Bytes(1),
    "fan_time_hour" / Int8ub,
    "fan_time_min" / Int8ub,
    "unknown5" / GreedyBytes,
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
            "MODBUS_ADDRESS_MSG": Struct("address" / Int8ub),
            "PRODUCT_INFO_MSG": ProductInfoData,
            "RMU_DATA_MSG": RmuData,
            "STRING_MSG": StringData,
        },
        default=Bytes(this.length),
    )
)


Command = Enum(
    Int8ub,
    RMU_WRITE_REQ=0x60,
    RMU_DATA_MSG=0x62,
    RMU_DATA_REQ=0x63,
    MODBUS_DATA_MSG=0x68,
    MODBUS_READ_REQ=0x69,
    MODBUS_READ_RESP=0x6A,
    MODBUS_WRITE_REQ=0x6B,
    MODBUS_WRITE_RESP=0x6C,
    MODBUS_ADDRESS_MSG=0x6E,
    PRODUCT_INFO_MSG=0x6D,
    ACCESSORY_VERSION_REQ=0xEE,
    ECS_DATA_REQ=0x90,
    ECS_DATA_MSG_1=0x55,
    ECS_DATA_MSG_2=0xA0,
    STRING_MSG=0xB1,
)

Address = Enum(
    Int8ub,
    ECS_S2=0x02,
    # 0x13 = 19, ?
    SMS40=0x16,
    RMU40_S1=0x19,
    RMU40_S2=0x1A,
    RMU40_S3=0x1B,
    RMU40_S4=0x1C,
    MODBUS40=0x20,
)

RmuWriteIndex = Enum(
    Int8ub,
    TEMPORARY_LUX=0x02,
    OPERATIONAL_MODE=0x04,
    FUNCTIONS=0x05,
    TEMPERATURE=0x06,
)

ADDRESS_TO_ROOM_TEMP_COIL = {
    Address.RMU40_S1: 40033,
    Address.RMU40_S2: 40032,
    Address.RMU40_S3: 40031,
    Address.RMU40_S4: 40030,
}


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


RequestData = Switch(
    this.cmd,
    {
        "ACCESSORY_VERSION_REQ": UnionConstruct(None,
            # Modbus and RMU seem to disagree on how to interpret this
            # data, at least from how it looks in the service info screen
            # on the pump.
            "modbus" / Struct(
                "version" / Int16ul,
                "unknown" / Int8ub,
            ),
            "rmu" / Struct(
                "unknown" / Int8ub,
                "version" / Int16ul,
            ),
        ),
        "RMU_WRITE_REQ": Struct(
            "index" / RmuWriteIndex,
            "value" / Switch(
                lambda this: this.index,
                {
                    "TEMPORARY_LUX": Int8ub,
                    "TEMPERATURE": FixedPoint(Int16ul, 0.1, -0.7),
                    "FUNCTIONS": FlagsEnum(
                        Int8ub,
                        allow_additive_heating=0x01,
                        allow_heating=0x02,
                        allow_cooling=0x04,
                    ),
                    "OPERATIONAL_MODE": Int8ub,
                },
                default=Select(
                    Int16ul,
                    Int8ub,
                )
            )
        ),
        "MODBUS_READ_REQ": Struct(
            "coil_address" / Int16ul,
        ),
        "MODBUS_WRITE_REQ": Struct(
            "coil_address" / Int16ul,
            "value" / Bytes(4),
        )
    },
    default=Bytes(this.length),
)

Request = Struct(
    "fields" / RawCopy(
        Struct(
            "start_byte" / Const(0xC0, Int8ub),
            "cmd" / Command,
            "data" / Prefixed(Int8ub, RequestData)
        )
    ),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
).compile()
# fmt: on
