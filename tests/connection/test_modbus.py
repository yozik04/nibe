from unittest.mock import AsyncMock, patch

from async_modbus import AsyncClient
import pytest

from nibe.connection.modbus import Modbus
from nibe.heatpump import HeatPump, Model


@pytest.fixture(name="modbus_client", autouse=True)
def fixture_modbus_client():
    with patch("nibe.connection.modbus.modbus_for_url") as mock_modbus_for_url:
        client = AsyncMock(AsyncClient)
        mock_modbus_for_url.return_value = client
        yield client


@pytest.fixture(name="heatpump")
def fixture_heatpump():
    heatpump = HeatPump(Model.S1255)
    heatpump.initialize()
    yield heatpump


@pytest.fixture(name="connection")
def fixture_connection(heatpump: HeatPump):
    yield Modbus(heatpump, "tcp://127.0.0.1", 0)


async def test_read_s32_coil(
    heatpump: HeatPump, connection: Modbus, modbus_client: AsyncMock
):
    coil = heatpump.get_coil_by_address(40011)
    modbus_client.read_holding_registers.return_value = [b"\x00\x00", b"\x00\x00"]
    coil = await connection.read_coil(coil)
    assert coil.value == 0
