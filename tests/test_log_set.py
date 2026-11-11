import asyncio
from datetime import date
import os
import signal
import sys

from asyncclick.testing import CliRunner
import pytest

from nibe.coil import Coil
from nibe.console_scripts.cli import cli
from nibe.heatpump import HeatPump, Model
from nibe.log_set import (
    DATABASE_VERSION,
    coil_slots,
    format_log_set,
    log_set_slots,
    parse_log_set,
)

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


async def test_editor(tmp_path, heatpump: HeatPump):
    pytest.importorskip("textual")
    from textual.widgets import Label, ListItem, SelectionList

    from nibe.console_scripts.log_set_tui import LogSetApp, OrderList

    path = tmp_path / "LOG.SET"
    app = LogSetApp(heatpump.get_coils(), [40868], path, DATABASE_VERSION)
    async with app.run_test() as pilot:
        await pilot.click("#filter")
        await pilot.press(*"40883")
        app.query_one("#registers", SelectionList).focus()
        await pilot.press("down", "space")
        assert app.query_one("#slots").content == "Slots 2/20"

        order = app.query_one("#order", OrderList)
        order.focus()
        order.index = 1
        await pilot.press("up")
        assert order.index == 0
        assert app._selected == [40868, 40883]

        await pilot.press("down", "enter", "up")
        assert order.grabbed
        assert app._selected == [40883, 40868]
        assert order.index == 0
        rows = list(order.query(ListItem))
        assert [row.has_class("-highlight") for row in rows] == [True, False]
        assert str(rows[0].query_one(Label).content).startswith("40883")
        assert str(rows[1].query_one(Label).content).startswith("40868")

        await pilot.press("space", "down")
        assert not order.grabbed
        assert order.index == 1
        await pilot.press("ctrl+s")

    assert parse_log_set(path.read_bytes()) == [40883, 40868]


async def test_editor_edges(tmp_path, heatpump: HeatPump):
    pytest.importorskip("textual")
    from textual.widgets import SelectionList

    from nibe.console_scripts.log_set_tui import LogSetApp, OrderList

    large = [coil.address for coil in heatpump.get_coils() if coil_slots(coil) == 2]
    path = tmp_path / "LOG.SET"
    app = LogSetApp(heatpump.get_coils(), large[:11], path, DATABASE_VERSION)
    async with app.run_test() as pilot:
        assert app.query_one("#slots").has_class("over")

        order = app.query_one("#order", OrderList)
        order.focus()
        order.index = None
        await pilot.press("space")
        assert not order.grabbed
        order.index = 0
        await pilot.press("space", "up")
        assert order.index == 0
        await pilot.press("down")
        assert order.index == 1
        assert app._selected[:2] == [large[1], large[0]]
        order.index = None
        await pilot.press("down")
        assert app._selected[:2] == [large[1], large[0]]
        order.index = 0

        await pilot.press("escape")
        assert app.is_running
        assert not order.grabbed

        await pilot.press("space")
        app.query_one("#filter").focus()
        await pilot.pause()
        assert not order.grabbed

        await pilot.press("ctrl+s")
        assert len(parse_log_set(path.read_bytes())) == 11

        await pilot.click("#filter")
        await pilot.press(*str(large[10]))
        app.query_one("#registers", SelectionList).focus()
        await pilot.press("down", "space", "ctrl+s")
        assert not app.query_one("#slots").has_class("over")

    assert parse_log_set(path.read_bytes()) == [large[1], large[0], *large[2:10]]


async def test_cli_log_set_edit(tmp_path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("textual")
    from nibe.console_scripts import log_set_tui

    started = {}

    class FakeApp:
        def __init__(self, coils, selected, path, database_version):
            started.update(selected=selected, path=path, version=database_version)

        async def run_async(self):
            started["ran"] = True

    monkeypatch.setattr(log_set_tui, "LogSetApp", FakeApp)
    output = tmp_path / "LOG.SET"
    output.write_bytes(REFERENCE)
    result = await CliRunner().invoke(
        cli, ["log-set-edit", "F1245", "-o", str(output), "--database-version", "1"]
    )
    assert result.exit_code == 0, result.output
    assert started == {
        "selected": [40883, 40868],
        "path": output,
        "version": "1",
        "ran": True,
    }


async def test_cli_log_set_edit_without_textual(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "nibe.console_scripts.log_set_tui", None)
    result = await CliRunner().invoke(cli, ["log-set-edit", "F1245"])
    assert result.exit_code == 1
    assert "pip install nibe[tui]" in result.output


@pytest.mark.parametrize(
    ("changed", "keys", "saved"),
    [
        pytest.param(False, ["ctrl+c"], False, id="unchanged_ctrl_c"),
        pytest.param(False, ["escape"], False, id="unchanged_escape"),
        pytest.param(True, ["ctrl+c", "s"], True, id="save"),
        pytest.param(True, ["ctrl+c", "d"], False, id="dont_save"),
        pytest.param(True, ["ctrl+c", "ctrl+c"], False, id="ctrl_c_twice"),
        pytest.param(True, ["escape", "escape"], False, id="escape_twice"),
    ],
)
async def test_editor_close(tmp_path, heatpump: HeatPump, changed, keys, saved):
    pytest.importorskip("textual")
    from textual.widgets import SelectionList

    from nibe.console_scripts.log_set_tui import LogSetApp

    path = tmp_path / "LOG.SET"
    app = LogSetApp(heatpump.get_coils(), [], path, DATABASE_VERSION)
    async with app.run_test() as pilot:
        if changed:
            app.query_one("#registers", SelectionList).focus()
            await pilot.press("down", "space")
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        assert not app.is_running

    assert path.exists() is saved


async def test_editor_unselected_box_is_empty(tmp_path, heatpump: HeatPump):
    pytest.importorskip("textual")
    from nibe.console_scripts.log_set_tui import LogSetApp, RegisterList

    coils = heatpump.get_coils()
    app = LogSetApp(coils, [coils[1].address], tmp_path / "LOG.SET", "8310")
    async with app.run_test():
        registers = app.query_one("#registers", RegisterList)
        assert list(registers.render_line(0))[1].text == " "
        assert list(registers.render_line(1))[1].text == "X"
        assert list(registers.render_line(10_000)) == list(
            super(RegisterList, registers).render_line(10_000)
        )


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="Needs POSIX signals")
@pytest.mark.parametrize("signum", ["SIGTERM", "SIGHUP", "SIGINT"])
async def test_editor_exits_on_signal(tmp_path, heatpump: HeatPump, signum: str):
    pytest.importorskip("textual")
    from nibe.console_scripts.log_set_tui import LogSetApp

    signum = getattr(signal, signum)
    app = LogSetApp(heatpump.get_coils(), [], tmp_path / "LOG.SET", "8310")
    async with app.run_test() as pilot:
        assert signal.getsignal(signum) not in (signal.SIG_DFL, signal.SIG_IGN)
        os.kill(os.getpid(), signum)
        await pilot.pause(0.2)
        assert not app.is_running

    assert signal.getsignal(signum) is not signal.SIG_IGN


async def test_editor_left_right(tmp_path, heatpump: HeatPump):
    pytest.importorskip("textual")
    from textual.widgets import Input, SelectionList

    from nibe.console_scripts.log_set_tui import LogSetApp, OrderList

    app = LogSetApp(heatpump.get_coils(), [40868], tmp_path / "LOG.SET", "8310")
    async with app.run_test() as pilot:
        registers = app.query_one("#registers", SelectionList)
        order = app.query_one("#order", OrderList)
        registers.focus()
        await pilot.press("right")
        assert app.focused is order
        await pilot.press("left")
        assert app.focused is registers

        filter_input = app.query_one("#filter", Input)
        filter_input.focus()
        await pilot.press(*"408", "left")
        assert app.focused is filter_input
        assert filter_input.cursor_position == 2


@pytest.mark.parametrize("start", ["registers", "order"])
async def test_editor_type_to_filter(tmp_path, heatpump: HeatPump, start: str):
    pytest.importorskip("textual")
    from nibe.console_scripts.log_set_tui import FilterInput, LogSetApp, RegisterList

    app = LogSetApp(heatpump.get_coils(), [40868], tmp_path / "LOG.SET", "8310")
    async with app.run_test() as pilot:
        filter_input = app.query_one("#filter", FilterInput)
        registers = app.query_one("#registers", RegisterList)

        app.query_one(f"#{start}").focus()
        await pilot.press(*"4088")
        assert app.focused is filter_input
        assert filter_input.value == "4088"

        await pilot.press("down")
        assert app.focused is registers
        assert all("4088" in str(option.prompt) for option in registers.options)

        filter_input.focus()
        await pilot.press("up")
        assert app.focused is registers

        await pilot.press("3", "backspace")
        assert filter_input.value == "4088"

        await pilot.press("down")
        registers.focus()
        await pilot.press("space")
        assert app.focused is registers
        assert filter_input.value == "4088"

        await pilot.press("backspace")
        assert app.focused is filter_input
        assert filter_input.value == "408"
