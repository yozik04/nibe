from typing import List, Union
from unittest.mock import AsyncMock, patch

from async_modbus import AsyncClient
import pytest

from nibe.coil import Coil
from nibe.connection.modbus import Modbus
from nibe.heatpump import HeatPump, Model


@pytest.fixture(name="modbus_client", autouse=True)
def fixture_modbus_client():
    with patch("nibe.connection.modbus.modbus_for_url") as mock_modbus_for_url:
        client = AsyncMock(AsyncClient)
        mock_modbus_for_url.return_value = client
        yield client


@pytest.fixture(name="heatpump", scope="module")
def fixture_heatpump():
    heatpump = HeatPump(Model.S1255)
    heatpump.initialize()
    yield heatpump


@pytest.fixture(name="connection")
def fixture_connection(heatpump: HeatPump):
    yield Modbus(heatpump, "tcp://127.0.0.1", 0)


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [b"\x01\x00", b"\x00\x00"], 1),
        ("u16", [b"\x01\x00"], 1),
        ("u8", [b"\x01\x00"], 1),
    ],
)
async def test_read_holding_register_coil(
    connection: Modbus,
    modbus_client: AsyncMock,
    size: str,
    raw: List[bytes],
    value: Union[int, float, str],
):
    coil = Coil(40001, "test", "test", size, 1)
    modbus_client.read_holding_registers.return_value = raw
    coil = await connection.read_coil(coil)
    assert coil.value == value
    modbus_client.read_holding_registers.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [b"\x01\x00", b"\x00\x00"], 1),
        ("u16", [b"\x01\x00"], 1),
        ("u8", [b"\x01\x00"], 1),
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
    coil.value = value
    coil = await connection.write_coil(coil)
    modbus_client.write_registers.assert_called_with(
        slave_id=0, starting_address=1, values=raw
    )


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u32", [b"\x01\x00", b"\x00\x00"], 1),
        ("u16", [b"\x01\x00"], 1),
        ("u8", [b"\x01\x00"], 1),
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
    coil = await connection.read_coil(coil)
    assert coil.value == value
    modbus_client.read_input_registers.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [b"\x01"], 1),
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
    coil = await connection.read_coil(coil)
    assert coil.value == value
    modbus_client.read_discrete_inputs.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [b"\x01"], 1),
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
    coil = await connection.read_coil(coil)
    assert coil.value == value
    modbus_client.read_coils.assert_called()


@pytest.mark.parametrize(
    ("size", "raw", "value"),
    [
        ("u8", [b"\x01"], 1),
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
    coil.value = value
    coil = await connection.write_coil(coil)
    modbus_client.write_coils.assert_called_with(
        slave_id=0, starting_address=1, values=raw
    )
