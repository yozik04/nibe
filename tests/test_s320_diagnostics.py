"""Read-only S320/S325 diagnostics and countdown metadata regressions."""

import pytest

from nibe.coil import CoilData
from nibe.connection.encoders import CoilDataEncoderModbus
from nibe.heatpump import HeatPump, Model


@pytest.fixture(params=[Model.S320, Model.S325])
async def heat_pump(request):
    heat_pump = HeatPump(request.param)
    await heat_pump.initialize()
    return heat_pump


@pytest.mark.parametrize(
    "address,size,name",
    [
        (31485, "u8", "compressor-status-eb101-31485"),
        (32727, "u16", "solar-energy-used-for-32727"),
        (33813, "u8", "status-33813"),
    ],
)
async def test_diagnostic_input_definition(heat_pump, address, size, name):
    coil = heat_pump.get_coil_by_address(address)
    assert coil.name == name
    assert coil.size == size
    assert coil.factor == 1
    assert not coil.is_writable
    assert not coil.is_boolean


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, "NO EFFECT"),
        (1, "HOT WATER"),
        (2, "HEATING"),
        (4, "COOLING"),
        (8, "POOL"),
        (16, "POOL 2"),
        (32, "SOLAR PV AUX"),
        (64, "ENERGY STORAGE"),
    ],
)
async def test_solar_energy_used_for(heat_pump, raw, expected):
    coil = heat_pump.get_coil_by_address(32727)
    assert CoilData.from_raw_value(coil, raw).value == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1, "PREHEATING"),
        (2, "WAITING"),
        (3, "RUNNING"),
        (4, "OFF"),
        (5, "DEFROST"),
        (6, "OFF"),
    ],
)
async def test_operational_status(heat_pump, raw, expected):
    coil = heat_pump.get_coil_by_address(33813)
    assert CoilData.from_raw_value(coil, raw).value == expected


async def test_eme_timer_is_a_countdown_not_a_cumulative_total(heat_pump):
    coil = heat_pump.get_coil_by_address(30583)
    assert coil.nature == "measurement"
    assert coil.unit == "min"
    assert coil.factor == 60
    assert not coil.is_writable
    assert CoilData.from_raw_value(coil, 360).value == 6
    assert CoilData.from_raw_value(coil, 300).value == 5


async def test_relay_status_preserves_high_byte(heat_pump):
    coil = heat_pump.get_coil_by_address(31120)
    assert coil.size == "u16"
    assert not coil.is_writable
    encoder = CoilDataEncoderModbus()
    assert encoder.decode(coil, [0x0101]).value == 0x0101


async def test_compressor_status_is_left_raw(heat_pump):
    coil = heat_pump.get_coil_by_address(31485)
    assert not coil.has_mappings
    assert CoilData.from_raw_value(coil, 3).value == 3


async def test_holding_register_at_same_offset_is_not_replaced(heat_pump):
    coil = heat_pump.get_coil_by_address(41120)
    assert coil.is_writable
    assert coil.size == "u8"
    assert coil.factor == 10
