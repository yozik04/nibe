from functools import reduce
from io import BytesIO
from operator import xor

from construct import (Array, Bytes, Checksum, Const, Enum, FixedSized, Flag, Int8ub,
                       Int16ul, RawCopy, Struct, Subconstruct, Switch, this,)


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


# fmt: off
Data = Dedupe5C(Switch(
    this.cmd,
    {
        "MODBUS_READ_RESP": Struct("coil_address" / Int16ul, "value" / Bytes(4)),
        "MODBUS_DATA_MSG": Array(
            lambda this: this.length // 4, Struct("coil_address" / Int16ul, "value" / Bytes(2))
        ),
        "MODBUS_WRITE_RESP": Struct("result" / Flag),
    },
    default=Bytes(this.length),
))

Command = Enum(
    Int8ub,
    RMU_DATA_MSG=0x62,
    MODBUS_DATA_MSG=0x68,
    MODBUS_READ_REQ=0x69,
    MODBUS_READ_RESP=0x6A,
    MODBUS_WRITE_REQ=0x6B,
    MODBUS_WRITE_RESP=0x6C,
)

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
