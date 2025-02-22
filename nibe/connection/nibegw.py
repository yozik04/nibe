import asyncio
from asyncio import CancelledError, Future, InvalidStateError
from binascii import hexlify
from contextlib import suppress
from dataclasses import dataclass
import errno
from functools import reduce
import io
from io import BytesIO
from ipaddress import ip_address
import logging
from operator import xor
import socket
import struct
from typing import Any, Dict, Literal, Optional, Union

from construct import (
    Adapter,
    BitStruct,
    Bytes,
    Checksum,
    Const,
    ConstructError,
    Container,
    Enum,
    EnumIntegerString,
    Flag,
    FlagsEnum,
    FocusedSeq,
    GreedyBytes,
    GreedyRange,
    GreedyString,
    IfThenElse,
    Int8sb,
    Int8ub,
    Int16sl,
    Int16ub,
    Int16ul,
    NullTerminated,
    Peek,
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

from nibe.coil import Coil, CoilData
from nibe.connection import DEFAULT_TIMEOUT, READ_PRODUCT_INFO_TIMEOUT, Connection
from nibe.connection.encoders import CoilDataEncoderNibeGw
from nibe.connection.mixins import ConnectionStatus, ConnectionStatusMixin
from nibe.event_server import EventServer
from nibe.exceptions import (
    AddressInUseException,
    CoilNotFoundException,
    CoilWriteSendException,
    DecodeException,
    NibeException,
    ProductInfoReadTimeoutException,
    ReadException,
    ReadIOException,
    ReadSendException,
    ReadTimeoutException,
    WriteDeniedException,
    WriteIOException,
    WriteTimeoutException,
)
from nibe.heatpump import HeatPump, ProductInfo

from . import verify_connectivity_read_write_alarm
from .encoders import is_hitting_integer_limit

logger = logging.getLogger("nibe").getChild(__name__)


@dataclass
class CoilAction:
    coil: Coil
    future: Future


class NibeGW(asyncio.DatagramProtocol, Connection, EventServer, ConnectionStatusMixin):
    """NibeGW connection."""

    PRODUCT_INFO_EVENT = "product_info"
    _futures: Dict[str, Future]
    _registered_reads: Dict[str, CoilAction]

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
        table_processing_mode: Literal["permissive", "strict"] = "permissive",
    ) -> None:
        super().__init__()

        self._heatpump = heatpump
        self._listening_ip = listening_ip
        self._listening_port = listening_port

        self._remote_ip = remote_ip
        self._remote_read_port = remote_read_port
        self._remote_write_port = remote_write_port

        self._table_processing_mode = table_processing_mode

        self._transport = None

        self._send_lock = asyncio.Lock()
        self._futures = {}
        self._registered_reads = {}

        self.coil_encoder = CoilDataEncoderNibeGw(heatpump.word_swap)

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

    async def start(self):
        logger.info(f"Starting UDP server on port {self._listening_port}")

        self.status = ConnectionStatus.INITIALIZING

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

        if self._heatpump.word_swap is None:
            await self.detect_word_swap()

    def connection_made(self, transport):
        """Callback when connection is made."""
        self.status = ConnectionStatus.LISTENING
        self._transport = transport

    def datagram_received(self, data: bytes, addr):
        """Callback when data is received."""
        logger.debug(f"Received {hexlify(data).decode('utf-8')} from {addr}")

        try:
            with io.BytesIO(bytes(data)) as stream:
                while block := Block.parse_stream(stream):
                    self._on_block(block, addr)
        except ConstructError as e:
            logger.warning(
                f"Ignoring packet from {addr} due to parse error: {hexlify(data).decode('utf-8')}: {e}"
            )
        except NibeException as e:
            logger.error(f"Failed handling packet from {addr}: {e}")
        except Exception:
            logger.exception(
                f"Unexpected exception during parsing packet data '{hexlify(data).decode('utf-8')}' from {addr}"
            )

    def _on_block(self, block: Container[Any], addr) -> None:
        if block.start_byte == "RESPONSE":
            self._on_response(block, addr)
        else:
            logger.debug(block)

    def _on_response(self, msg: Container[Any], addr) -> None:
        if not self._remote_ip:
            logger.debug("Pump discovered at %s", addr)
            self._remote_ip = addr[0]

        self.status = ConnectionStatus.CONNECTED

        logger.debug(msg.fields.value)
        cmd = msg.fields.value.cmd
        if cmd == "MODBUS_DATA_MSG":
            data: dict[int, bytes] = {
                row.coil_address: row.value
                for row in msg.fields.value.data
                if row.coil_address != 0xFFFF
            }
            self._on_raw_coil_set(data)
        elif cmd == "MODBUS_READ_RESP":
            row = msg.fields.value.data
            self._on_raw_coil_value(row.coil_address, row.value)
        elif cmd == "MODBUS_WRITE_RESP":
            with suppress(InvalidStateError, CancelledError, KeyError):
                self._futures["write"].set_result(msg.fields.value.data.result)
        elif cmd == "RMU_DATA_MSG":
            self._on_rmu_data(msg.fields.value)
        elif cmd == "PRODUCT_INFO_MSG":
            data = msg.fields.value.data
            product_info = ProductInfo(data["model"], data["version"])
            with suppress(InvalidStateError, CancelledError, KeyError):
                self._futures["product_info"].set_result(product_info)
            self.notify_event_listeners(
                self.PRODUCT_INFO_EVENT, product_info=product_info
            )
        elif not isinstance(cmd, EnumIntegerString):
            logger.debug(f"Unknown command {cmd}")

    async def read_product_info(
        self, timeout: float = READ_PRODUCT_INFO_TIMEOUT
    ) -> ProductInfo:
        self._futures["product_info"] = asyncio.get_event_loop().create_future()
        try:
            return await asyncio.wait_for(self._futures["product_info"], timeout)
        except asyncio.TimeoutError:
            raise ProductInfoReadTimeoutException("Timeout waiting for product message")
        finally:
            del self._futures["product_info"]

    async def detect_word_swap(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Read word swap setting."""
        try:
            coil = self._heatpump.get_coil_by_address(48852)
            assert coil.is_boolean, "Coil is not boolean"
            coil_data = await self.read_coil(coil, timeout)
            self.coil_encoder.word_swap = coil_data.value == "ON"
            self._heatpump.word_swap = self.coil_encoder.word_swap
            logger.info(f"Word swap setting detected: {coil_data.value}")
        except Exception as e:
            logger.warning(f"Failed to detect word swap setting: {e}")

    async def read_coil(self, coil: Coil, timeout: float = DEFAULT_TIMEOUT) -> CoilData:
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

            future = self._register_coil_read_request(coil)

            logger.debug(
                f"Sending {hexlify(data).decode('utf-8')} (read request) to {self._remote_ip}:{self._remote_write_port}"
            )

            try:
                self._transport.sendto(data, (self._remote_ip, self._remote_read_port))
            except socket.gaierror:
                raise ReadSendException(f"Unable to lookup hostname: {self._remote_ip}")

            logger.debug(f"Waiting for read response for {coil.name}")

            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                raise ReadTimeoutException(
                    f"Timeout waiting for read response for {coil.name}"
                )
            except DecodeException as e:
                raise ReadException(
                    f"Failed decoding response for {coil.name}: {e}"
                ) from e

    def _register_coil_read_request(self, coil: Coil) -> Future:
        read = self._registered_reads.get(str(coil.address))
        if read is not None and not read.future.done():
            return read.future

        future = asyncio.get_event_loop().create_future()
        self._registered_reads[str(coil.address)] = CoilAction(coil, future)
        return future

    def _on_coil_read_success(self, coil_data):
        logger.info(coil_data)

        read = self._registered_reads.get(str(coil_data.coil.address))
        if read is not None and not read.future.done():
            read.future.set_result(coil_data)

        self._heatpump.notify_coil_update(coil_data)

    def _on_coil_read_error(
        self, coil_address, value: Union[bytes, float, int, str], exception: Exception
    ):
        if coil_address == 65535:  # 0xffff
            return

        read = self._registered_reads.get(str(coil_address))
        if read is not None and not read.future.done():
            read.future.set_exception(exception)

        if isinstance(exception, CoilNotFoundException):
            logger.warning(f"Ignoring coil {coil_address} - coil definition not found")
        elif isinstance(exception, DecodeException):
            str_value = (
                hexlify(value).decode("utf-8") if isinstance(value, bytes) else value
            )
            logger.warning(
                f"Ignoring coil {coil_address} value {str_value} - failed to decode"
            )
        elif isinstance(exception, NibeException):
            logger.error(f"Failed handling read for {coil_address}: {exception}")

    async def write_coil(
        self, coil_data: CoilData, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        coil = coil_data.coil
        assert coil.is_writable, f"{coil.name} is not writable"
        assert coil_data.value is not None, f"{coil.name} value must be set"
        async with self._send_lock:
            assert self._transport, "Transport is closed"
            data = Request.build(
                dict(
                    fields=dict(
                        value=dict(
                            cmd="MODBUS_WRITE_REQ",
                            data=dict(
                                coil_address=coil.address,
                                value=self.coil_encoder.encode(coil_data),
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
                    raise WriteDeniedException(f"Heatpump denied writing {coil.name}")
                else:
                    logger.info(f"Write succeeded for {coil.name}")
            except asyncio.TimeoutError:
                raise WriteTimeoutException(
                    f"Timeout waiting for write feedback for {coil.name}"
                )
            finally:
                del self._futures["write"]

    def error_received(self, exc):
        """Handle errors from the transport"""
        logger.error(exc)

    @property
    def remote_ip(self) -> Optional[str]:
        """Get the remote IP address"""
        return self._remote_ip

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

    def _on_raw_coil_value(self, coil_address: int, raw_value: bytes) -> None:
        try:
            coil = self._heatpump.get_coil_by_address(coil_address)
            coil_data = self.coil_encoder.decode(coil, raw_value)
            self._on_coil_read_success(coil_data)
        except NibeException as e:
            self._on_coil_read_error(coil_address, raw_value, e)

    def _on_raw_coil_set(self, data: dict[int, bytes]) -> None:
        successful_coil_data = []
        decode_exception_occurred = False
        while data:
            coil_address = min(data.keys())
            raw_value = data.pop(coil_address)
            try:
                coil = self._heatpump.get_coil_by_address(coil_address)
                if coil.size in ("u32", "s32"):
                    raw_value = raw_value + data.pop(coil_address + 1, b"")
                coil_data = self.coil_encoder.decode(coil, raw_value)
                successful_coil_data.append(coil_data)
            except DecodeException as e:
                self._on_coil_read_error(coil_address, raw_value, e)
                decode_exception_occurred = True
            except NibeException as e:
                self._on_coil_read_error(coil_address, raw_value, e)

        if self._table_processing_mode == "permissive" or (
            self._table_processing_mode == "strict" and not decode_exception_occurred
        ):
            for coil_data in successful_coil_data:
                self._on_coil_read_success(coil_data)

    def _on_coil_value(self, coil_address: int, value: Union[float, int, str]) -> None:
        try:
            coil = self._heatpump.get_coil_by_address(coil_address)

            if isinstance(value, bool):
                value = 1 if value else 0

            if isinstance(value, EnumIntegerString):
                value = int(value)

            if coil.has_mappings and isinstance(value, int):
                coil_data = CoilData.from_mapping(coil, value)
            else:
                coil_data = CoilData(coil, value)

            self._on_coil_read_success(coil_data)
        except NibeException as e:
            self._on_coil_read_error(coil_address, value, e)

    async def verify_connectivity(self):
        await verify_connectivity_read_write_alarm(self, self._heatpump)

    async def stop(self):
        if self._transport:
            self._transport.close()
            self._transport = None
        await asyncio.sleep(0)
        self.status = ConnectionStatus.DISCONNECTED


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


class FixedPointStrange(Adapter):
    """Strange fixed point calculation

    The pump seems to apply the offset in reverse when
    crossing over to negative values. My guess it's some
    bug in firmware that was never resolved, and can't
    be fixed.
    """

    def __init__(self, subcon, scale, offset, size, ndigits=1) -> None:
        super().__init__(subcon)
        self._offset = offset
        self._scale = scale
        self._ndigits = ndigits
        self._size = size

    def _decode(self, obj, context, path):
        value = obj
        if value >= self._offset:
            value += self._offset
        else:
            value -= self._offset

        # For now skip limit checks, since we don't know
        # how the pump handles these for this special case
        # for negative offsets, we could never reach the
        # integer limits after offset has been applied.

        return round(value * self._scale, self._ndigits)

    def _encode(self, obj, context, path):
        val = obj / self._scale
        if val >= 0:
            val -= self._offset
        else:
            val += self._offset
        return val


class FixedPoint(Adapter):
    def __init__(self, subcon, scale, offset, size, ndigits=1) -> None:
        super().__init__(subcon)
        self._offset = offset
        self._scale = scale
        self._ndigits = ndigits
        self._size = size

    def _decode(self, obj, context, path):
        value = obj + self._offset

        # Limits seem to be applied after offset
        # have been applied. This may possible depend
        # on the sign of the offset, but that is unknown
        # at the moment.
        if is_hitting_integer_limit(self._size, value):
            return None

        return round(value * self._scale, self._ndigits)

    def _encode(self, obj, context, path):
        return obj / self._scale - self._offset


StartCode = Enum(
    Int8ub,
    RESPONSE=0x5C,
    REQUEST=0xC0,
    ACK=0x06,
    NAK=0x15,
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
    HEATPUMP_REQ=0xF7,
)


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
    "bt1_outdoor_temperature" / FixedPointStrange(Int16sl, 0.1, -5, "s16"),
    "bt7_hw_top" / FixedPoint(Int16sl, 0.1, -5, "s16"),
    "setpoint_or_offset_s1"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s1,
        FixedPoint(Int8ub, 0.1, 50, "u8"),
        FixedPoint(Int8sb, 1.0, 0, "s8"),
    ),
    "setpoint_or_offset_s2"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s2,
        FixedPoint(Int8ub, 0.1, 50, "u8"),
        FixedPoint(Int8sb, 1.0, 0, "s8"),
    ),
    "setpoint_or_offset_s3"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s3,
        FixedPoint(Int8ub, 0.1, 50, "u8"),
        FixedPoint(Int8sb, 1.0, 0, "s8"),
    ),
    "setpoint_or_offset_s4"
    / IfThenElse(
        lambda this: this.flags.use_room_sensor_s4,
        FixedPoint(Int8ub, 0.1, 50, "u8"),
        FixedPoint(Int8sb, 1.0, 0, "s8"),
    ),
    "bt50_room_temp_sX" / FixedPoint(Int16sl, 0.1, -5, "s16"),
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

ModbusDataValue = Struct("coil_address" / Int16ul, "value" / Bytes(2))
ModbusData = GreedyRange(ModbusDataValue)
ModbusReadResp = Struct("coil_address" / Int16ul, "value" / Bytes(4))
ModbusWriteResp = Struct("result" / Flag)
ModbusAddressMsg = Struct("address" / Int8ub)

ResponseTypes = {
    "MODBUS_READ_RESP": ModbusReadResp,
    "MODBUS_DATA_MSG": ModbusData,
    "MODBUS_WRITE_RESP": ModbusWriteResp,
    "MODBUS_ADDRESS_MSG": ModbusAddressMsg,
    "PRODUCT_INFO_MSG": ProductInfoData,
    "RMU_DATA_MSG": RmuData,
    "STRING_MSG": StringData,
}

Address = Enum(
    Int16ub,
    ECS_S2=0x02,
    # 0x13 = 19, ?
    SMS40=0x16,
    RMU40_S1=0x19,
    RMU40_S2=0x1A,
    RMU40_S3=0x1B,
    RMU40_S4=0x1C,
    MODBUS40=0x20,
    HEATPUMP_1=0x41C9,
    HEATPUMP_2=0x42C9,
    HEATPUMP_3=0x43C9,
    HEATPUMP_4=0x44C9,
    HEATPUMP_5=0x45C9,
    HEATPUMP_6=0x46C9,
    HEATPUMP_7=0x47C9,
    HEATPUMP_8=0x48C9,
)

RmuWriteIndex = Enum(
    Int8ub,
    TEMPORARY_LUX=0x02,
    OPERATIONAL_MODE=0x04,
    FUNCTIONS=0x05,
    TEMPERATURE=0x06,
    SETPOINT_S1=0x09,
    SETPOINT_S2=0x11,
    SETPOINT_S3=0x13,
    SETPOINT_S4=0x15,
)

ADDRESS_TO_ROOM_TEMP_COIL = {
    Address.RMU40_S1: 40033,
    Address.RMU40_S2: 40032,
    Address.RMU40_S3: 40031,
    Address.RMU40_S4: 40030,
}


# fmt: off

ResponseData = Struct(
    "address" / Address,
    "cmd" / Command,
    "data" / Prefixed(Int8ub,
        Dedupe5C(
            Switch(
                this.cmd, ResponseTypes,
                default=GreedyBytes,
            )
        )
    ),
)

Response = Struct(
    "start_byte" / Const("RESPONSE", StartCode),
    "fields" / RawCopy(ResponseData),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
)

AccessoryVersionReq = UnionConstruct(None,
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
)

RmuWriteReqTypes = {
    "TEMPORARY_LUX": Int8ub,
    "TEMPERATURE": FixedPoint(Int16ul, 0.1, -7.0, size="s16"),
    "FUNCTIONS": FlagsEnum(
        Int8ub,
        allow_additive_heating=0x01,
        allow_heating=0x02,
        allow_cooling=0x04,
    ),
    "OPERATIONAL_MODE": Int8ub,
    "SETPOINT_S1": FixedPoint(Int16sl, 0.1, 0.0, size="s16"),
    "SETPOINT_S2": FixedPoint(Int16sl, 0.1, 0.0, size="s16"),
    "SETPOINT_S3": FixedPoint(Int16sl, 0.1, 0.0, size="s16"),
    "SETPOINT_S4": FixedPoint(Int16sl, 0.1, 0.0, size="s16"),
}

RmuWriteReq = Struct(
    "index" / RmuWriteIndex,
    "value" / Switch(
        this.index,
        RmuWriteReqTypes,
        default=Select(
            Int16ul,
            Int8ub,
        )
    )
)

ModbusReadReq = Struct(
    "coil_address" / Int16ul,
)

ModbusWriteReq = Struct(
    "coil_address" / Int16ul,
    "value" / Bytes(4),
)

RequestTypes = {
    "ACCESSORY_VERSION_REQ": AccessoryVersionReq,
    "RMU_WRITE_REQ": RmuWriteReq,
    "MODBUS_READ_REQ": ModbusReadReq,
    "MODBUS_WRITE_REQ": ModbusWriteReq
}

RequestData = Struct(
    Const("REQUEST", StartCode),
    "cmd" / Command,
    "data" / Prefixed(Int8ub,
        Switch(
            this.cmd,
            RequestTypes,
            default=GreedyBytes,
        )
    )
)

Request = Struct(
    "start_byte" / Peek(StartCode),
    "fields" / RawCopy(RequestData),
    "checksum" / Checksum(Int8ub, xor8, this.fields.data),
)

AckData = Struct(Const("ACK", StartCode))
Ack = Struct(
    "start_byte" / Peek(StartCode),
    "fields" / RawCopy(AckData)
)

NakData = Struct(Const("NAK", StartCode))
Nak = Struct(
    "start_byte" / Peek(StartCode),
    "fields" / RawCopy(NakData)
)

BlockTypes = {
    "RESPONSE": Response,
    "REQUEST": Request,
    "ACK": Ack,
    "NAK": Nak,
}

Block = FocusedSeq(
    "data",
    "start_byte" / Peek(StartCode),
    "data" / Switch(
        this.start_byte,
        BlockTypes
    ),
)

# fmt: on
