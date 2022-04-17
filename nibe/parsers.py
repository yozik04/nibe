from functools import reduce
from operator import xor

from construct import (Array, Bytes, Checksum, Const, Enum, FixedSized, Flag, Int8ub,
                       Int16ul, RawCopy, Struct, Switch, this,)


def xor8(data: bytes):
    return reduce(xor, data)


# fmt: off
Data = Switch(
    this.cmd,
    {
        "MODBUS_READ_RESP": Struct("coil_address" / Int16ul, "value" / Bytes(4)),
        "MODBUS_DATA_MSG": Array(
            lambda this: this.length // 4, Struct("coil_address" / Int16ul, "value" / Bytes(2))
        ),
        "MODBUS_WRITE_RESP": Struct("result" / Flag),
    },
    default=Bytes(this.length),
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
