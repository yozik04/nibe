import asyncio
from datetime import date

from asyncclick.testing import CliRunner
import pytest

from nibe.coil import Coil
from nibe.console_scripts.cli import cli
from nibe.heatpump import HeatPump, Model
from nibe.log_set import coil_slots, format_log_set, log_set_slots, parse_log_set

# Written by NIBE tools for F1245, with registers 40883 and 40868.
REFERENCE = (
    b"[NIBL;20261111;8310]\r\n"
    b"Divisors\t\t1\t1\r\n"
    b"Date\tTime\t+Adjust Affect system6\t+Adjust AUX Port [1]\r\n"
    b"40883\r\n"
    b"40868"
)


@pytest.fixture(name="heatpump")
def fixture_heatpump() -> HeatPump:
    heatpump = HeatPump(Model.F1245)
    asyncio.run(heatpump.initialize())
    return heatpump


def test_format_matches_reference(heatpump: HeatPump):
    coils = [heatpump.get_coil_by_address(address) for address in (40883, 40868)]
    assert format_log_set(coils, created=date(2026, 11, 11)) == REFERENCE


def test_format_divisor_and_unit(heatpump: HeatPump):
    coil = heatpump.get_coil_by_address(40004)
    assert format_log_set([coil], created=date(2026, 11, 11)).split(b"\r\n") == [
        b"[NIBL;20261111;8310]",
        b"Divisors\t\t10",
        "Date\tTime\tBT1 Outdoor Temperature [°C]".encode("latin-1"),
        b"40004",
    ]


def test_format_replaces_characters_outside_latin1():
    coil = Coil(1, "test-1", "Flow → room", "u8")
    assert b"Flow ? room" in format_log_set([coil])


def test_parse_reference():
    assert parse_log_set(REFERENCE) == [40883, 40868]


def test_parse_rejects_other_files():
    with pytest.raises(ValueError):
        parse_log_set(b"Date\tTime\r\n40004")


def test_slots():
    small = Coil(1, "small-1", "Small", "s16")
    large = Coil(2, "large-2", "Large", "u32")
    assert coil_slots(small) == 1
    assert coil_slots(large) == 2
    assert log_set_slots([small, large, large]) == 5


async def test_cli_log_set(tmp_path):
    output = tmp_path / "LOG.SET"
    result = await CliRunner().invoke(
        cli, ["log-set", "F1245", "40883", "40868", "-o", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert "Wrote 2 registers (2 slots)" in result.output
    assert output.read_bytes().split(b"\r\n")[1:] == REFERENCE.split(b"\r\n")[1:]


async def test_cli_log_set_warns_above_slots(tmp_path):
    heatpump = HeatPump(Model.F1245)
    await heatpump.initialize()
    addresses = [
        str(coil.address) for coil in heatpump.get_coils() if coil_slots(coil) == 2
    ][:11]
    output = tmp_path / "LOG.SET"
    result = await CliRunner().invoke(
        cli, ["log-set", "F1245", *addresses, "-o", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert "only sends the first 20" in result.output
    assert len(parse_log_set(output.read_bytes())) == 11


async def test_cli_log_set_unknown_address(tmp_path):
    output = tmp_path / "LOG.SET"
    result = await CliRunner().invoke(
        cli, ["log-set", "F1245", "12345", "-o", str(output)]
    )
    assert result.exit_code == 2
    assert "12345 not found" in result.output
    assert not output.exists()
