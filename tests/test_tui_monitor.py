import asyncio
import logging
from types import SimpleNamespace

import asyncclick as click
import pytest
from textual.widgets import DataTable, Log

from nibe.coil import CoilData
from nibe.console_scripts.cli import monitor
from nibe.console_scripts.tui_monitor import MonitorApp
from nibe.heatpump import HeatPump, Model


@pytest.fixture(name="heatpump")
def fixture_heatpump() -> HeatPump:
    heatpump = HeatPump(Model.F1155)
    asyncio.run(heatpump.initialize())
    return heatpump


def _data(heatpump: HeatPump, address: int, value) -> CoilData:
    return CoilData(heatpump.get_coil_by_address(address), value)


UPDATES = ((43086, "HEAT"), (40004, -3.5), (40004, -3.6), (47394, None))


async def test_monitor_app(heatpump: HeatPump):
    root_handlers = logging.getLogger().handlers[:]
    app = MonitorApp()
    async with app.run_test() as pilot:
        for address, value in UPDATES:
            app.update_coil(_data(heatpump, address, value))
        await pilot.pause()

        table = app.query_one("#values", DataTable)
        rows = [table.get_row(row.key) for row in table.ordered_rows]
        assert [row[:4] + row[5:] for row in rows] == [
            [40004, "BT1 Outdoor Temperature", "-3.6", "°C", 2],
            [43086, "Prio", "HEAT", "", 1],
            [47394, "Use room sensor S1", "", "", 1],
        ]

        log = app.query_one("#log", Log)
        assert not log.display
        assert log.line_count == 0

        logging.getLogger("nibe").warning("Failed to parse a block")
        await pilot.pause()
        assert log.display
        assert [line.split(" ", 1)[1] for line in log.lines] == [
            "[WARNING ] Failed to parse a block"
        ]

    assert logging.getLogger().handlers == root_handlers


async def test_monitor_command(heatpump: HeatPump, monkeypatch: pytest.MonkeyPatch):
    received: list[CoilData] = []

    async def run_async(self: MonitorApp) -> None:
        heatpump.notify_coil_update(_data(heatpump, 40004, 1.5))

    monkeypatch.setattr(
        MonitorApp, "update_coil", lambda self, data: received.append(data)
    )
    monkeypatch.setattr(MonitorApp, "run_async", run_async)

    ctx = click.Context(monitor, obj=SimpleNamespace(heatpump=heatpump))
    async with ctx:
        await ctx.invoke(monitor)

    assert [(data.coil.address, data.value) for data in received] == [(40004, 1.5)]
