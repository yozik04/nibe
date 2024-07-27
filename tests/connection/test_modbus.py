import asyncio
from typing import List, Union
from unittest.mock import AsyncMock, patch

from async_modbus import AsyncClient
import pytest

from nibe.coil import Coil, CoilData
from nibe.connection.modbus import Modbus
from nibe.exceptions import ReadException, ReadExceptionGroup, WriteException
from nibe.heatpump import HeatPump, Model


@pytest.fixture(name="modbus_client", autouse=True)
def fixture_modbus_client():
    with patch("nibe.connection.modbus.modbus_for_url") as mock_modbus_for_url:
        client = AsyncMock(AsyncClient)
        mock_modbus_for_url.return_value = client
        yield client


@pytest.fixture(name="heatpump")
async def fixture_heatpump():
    heatpump = HeatPump(Model.S1255)
    heatpump.word_swap = True
    await heatpump.initialize()
    yield heatpump


@pytest.fixture(name="connection")
def fixture_connection(heatpump: HeatPump):
    yield Modbus(heatpump, "tcp://127.0.0.1", 0)


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [1, 0], 0x00000001),
        ("u32", [0, 32768], 0x80000000),
        ("u16", [1], 0x0001),
        ("u16", [32768], 0x8000),
        ("u8", [1], 0x01),
        ("u8", [128], 0x80),
    ],
)
async def test_read_holding_register_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[int],
    value: Union[int, float, str],
):
    coil = Coil(40001, "test", "test", size, 1)
    modbus_client.read_holding_registers.return_value = raw
    coil_data = await connection.read_coil(coil)
    assert coil_data.value == value
    modbus_client.read_holding_registers.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [1, 0], 0x00000001),
        ("u32", [0, 32768], 0x80000000),
        ("u16", [1], 0x0001),
        ("u16", [32768], 0x8000),
        ("u8", [1], 0x01),
        ("u8", [128], 0x80),
    ],
)
async def test_write_holding_register(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(40002, "test", "test", size, 1, write=True)
    coil_data = CoilData(coil, value)
    await connection.write_coil(coil_data)
    modbus_client.write_registers.assert_called_with(
        slave_id=0, starting_address=1, values=raw
    )


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [1, 0], 0x00000001),
        ("u32", [0, 32768], 0x80000000),
        ("s32", [0xFFF6, 0xFFFF], -0xA),
        ("u16", [1], 0x0001),
        ("u16", [32768], 0x8000),
        ("s16", [0xFFF6], -0xA),
        ("u8", [1], 0x01),
        ("u8", [128], 0x80),
    ],
)
async def test_read_input_register_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(30001, "test", "test", size, 1)
    modbus_client.read_input_registers.return_value = raw
    coil_data = await connection.read_coil(coil)
    assert coil_data.value == value
    modbus_client.read_input_registers.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [1], 0x01),
        ("u8", [0], 0x00),
    ],
)
async def test_read_discrete_input_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(10001, "test", "test", size, 1)
    modbus_client.read_discrete_inputs.return_value = raw
    coil_data = await connection.read_coil(coil)
    assert coil_data.value == value
    modbus_client.read_discrete_inputs.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [1], 0x01),
        ("u8", [0], 0x00),
    ],
)
async def test_read_coil_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(1, "test", "test", size, 1)
    modbus_client.read_coils.return_value = raw
    coil_data = await connection.read_coil(coil)
    assert coil_data.value == value
    modbus_client.read_coils.assert_called()


async def test_read_coil_out_of_range(
    connection: Modbus,
    modbus_client: AsyncMock,
):
    coil = Coil(1, "test", "test", "u8", 1, min=1, max=2)
    modbus_client.read_coils.return_value = bytes([0])
    with pytest.raises(ReadException):
        await connection.read_coil(coil)


async def test_read_coils_failed_read(
    connection: Modbus,
    modbus_client: AsyncMock,
):
    coil = Coil(1, "test", "test", "u8", 1, min=1, max=2)
    modbus_client.read_coils.side_effect = asyncio.IncompleteReadError(bytes([]), 9)
    with pytest.raises(ReadExceptionGroup):
        async for coil in connection.read_coils([coil]):
            pass


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [1], 0x01),
        ("u8", [0], 0x00),
        ("s8", [0xFFF6], -0xA),
        ("s16", [0xFFF6], -0xA),
        ("s32", [0xFFF6, 0xFFFF], -0xA),
    ],
)
async def test_write_coil_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(2, "test", "test", size, 1, write=True)
    coil_data = CoilData(coil, value)
    await connection.write_coil(coil_data)
    modbus_client.write_coils.assert_called_with(
        slave_id=0, starting_address=1, values=raw
    )


async def test_write_coil_failed_read(
    connection: Modbus,
    modbus_client: AsyncMock,
):
    coil = Coil(1, "test", "test", "u8", 1, min=1, max=2, write=True)
    coil_data = CoilData(coil, 1)
    modbus_client.write_coils.side_effect = asyncio.IncompleteReadError(bytes([]), 9)
    with pytest.raises(WriteException):
        await connection.write_coil(coil_data)
