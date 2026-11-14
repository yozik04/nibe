import asyncio
import os
import signal

from asyncclick.testing import CliRunner
import pytest
from textual.widgets import Input, Label, ListItem, SelectionList

from nibe.console_scripts import tui_log_set
from nibe.console_scripts.cli import cli
from nibe.console_scripts.tui_log_set import (
    FilterInput,
    LogSetApp,
    OrderList,
    RegisterList,
)
from nibe.heatpump import HeatPump, Model
from nibe.log_set import DATABASE_VERSION, coil_slots, format_log_set, parse_log_set


@pytest.fixture(name="heatpump")
def fixture_heatpump() -> HeatPump:
    heatpump = HeatPump(Model.F1245)
    asyncio.run(heatpump.initialize())
    return heatpump


async def test_editor(tmp_path, heatpump: HeatPump):
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


async def test_cli_log_set_edit(
    tmp_path, heatpump: HeatPump, monkeypatch: pytest.MonkeyPatch
):
    started = {}

    class FakeApp:
        def __init__(self, coils, selected, path, database_version):
            started.update(selected=selected, path=path, version=database_version)

        async def run_async(self):
            started["ran"] = True

    monkeypatch.setattr(tui_log_set, "LogSetApp", FakeApp)
    output = tmp_path / "LOG.SET"
    output.write_bytes(
        format_log_set([heatpump.get_coil_by_address(a) for a in (40883, 40868)])
    )
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


@pytest.mark.parametrize(
    ("changed", "keys", "saved"),
    [
        pytest.param(False, ["ctrl+c"], False, id="unchanged_ctrl_c"),
        pytest.param(False, ["escape"], False, id="unchanged_escape"),
        pytest.param(True, ["ctrl+c", "s"], True, id="save"),
        pytest.param(True, ["ctrl+c", "d"], False, id="dont_save"),
        pytest.param(True, ["ctrl+c", "ctrl+c"], False, id="ctrl_c_twice"),
        pytest.param(True, ["escape", "escape"], False, id="escape_twice"),
        pytest.param(True, ["ctrl+q", "s"], True, id="ctrl_q_save"),
        pytest.param(False, ["ctrl+q"], False, id="unchanged_ctrl_q"),
    ],
)
async def test_editor_close(tmp_path, heatpump: HeatPump, changed, keys, saved):
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


async def test_editor_save_failure(tmp_path, heatpump: HeatPump):
    path = tmp_path / "missing" / "LOG.SET"
    app = LogSetApp(heatpump.get_coils(), [], path, DATABASE_VERSION)
    async with app.run_test() as pilot:
        app.query_one("#registers", SelectionList).focus()
        await pilot.press("down", "space", "ctrl+s")
        await pilot.press("ctrl+c", "s")
        await pilot.pause()
        assert app.is_running
        assert app._selected != app._saved

    assert not path.exists()


async def test_editor_duplicates(tmp_path, heatpump: HeatPump):
    path = tmp_path / "LOG.SET"
    app = LogSetApp(heatpump.get_coils(), [40868, 40883, 40868], path, "8310")
    async with app.run_test() as pilot:
        assert app._selected == [40868, 40883]
        await pilot.click("#filter")
        await pilot.press(*"40868")
        app.query_one("#registers", SelectionList).focus()
        await pilot.press("down", "space", "ctrl+s")

    assert parse_log_set(path.read_bytes()) == [40883]


@pytest.mark.parametrize(
    ("content", "mode"),
    [
        pytest.param(
            b"[NIBL;20240101;8310]\r\nDivisors\t\t1\r\nDate\tTime\tUnknown\r\n1",
            0o644,
            id="unknown_address",
        ),
        pytest.param(b"", 0o644, id="malformed"),
        pytest.param(
            b"",
            0o000,
            id="unreadable",
            marks=pytest.mark.skipif(
                os.name != "posix" or os.geteuid() == 0, reason="Needs file modes"
            ),
        ),
    ],
)
async def test_cli_log_set_edit_bad_output(tmp_path, content: bytes, mode: int):
    output = tmp_path / "LOG.SET"
    output.write_bytes(content)
    output.chmod(mode)
    result = await CliRunner().invoke(cli, ["log-set-edit", "F1245", "-o", str(output)])
    assert result.exit_code == 2
    assert "--output" in result.output


async def test_editor_unselected_box_is_empty(tmp_path, heatpump: HeatPump):
    coils = heatpump.get_coils()
    app = LogSetApp(coils, [coils[1].address], tmp_path / "LOG.SET", "8310")
    async with app.run_test():
        registers = app.query_one("#registers", RegisterList)
        assert list(registers.render_line(0))[1].text == " "
        assert list(registers.render_line(1))[1].text == "X"
        assert list(registers.render_line(10_000)) == list(
            super(RegisterList, registers).render_line(10_000)
        )


@pytest.mark.skipif(os.name != "posix", reason="Needs POSIX signals")
@pytest.mark.parametrize("signum", ["SIGTERM", "SIGHUP", "SIGINT"])
async def test_editor_exits_on_signal(tmp_path, heatpump: HeatPump, signum: str):
    signum = getattr(signal, signum)
    previous = signal.getsignal(signum)
    app = LogSetApp(heatpump.get_coils(), [], tmp_path / "LOG.SET", "8310")
    async with app.run_test() as pilot:
        assert signal.getsignal(signum) not in (signal.SIG_DFL, signal.SIG_IGN)
        os.kill(os.getpid(), signum)
        await pilot.pause(0.2)
        assert not app.is_running

    assert signal.getsignal(signum) is previous


@pytest.mark.skipif(os.name != "posix", reason="Needs POSIX signals")
async def test_editor_restores_signal_handlers(tmp_path, heatpump: HeatPump):
    def handler(signum, frame):
        pass

    received = []
    loop = asyncio.get_running_loop()
    previous = signal.signal(signal.SIGHUP, handler)
    loop.add_signal_handler(signal.SIGTERM, received.append, "SIGTERM")
    try:
        app = LogSetApp(heatpump.get_coils(), [], tmp_path / "LOG.SET", "8310")
        async with app.run_test():
            assert signal.getsignal(signal.SIGHUP) is not handler
        assert signal.getsignal(signal.SIGHUP) is handler

        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.1)
        assert received == ["SIGTERM"]
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        signal.signal(signal.SIGHUP, previous)


async def test_editor_left_right(tmp_path, heatpump: HeatPump):
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
