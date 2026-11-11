"""Live view of the coil values a heat pump sends, built on textual."""

from __future__ import annotations

from datetime import datetime
import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable, Footer, Header, Log

from ..coil import CoilData
from .tui_app import SignalSafeApp

COLUMNS = ("Address", "Title", "Value", "Unit", "Seen", "Count")


class _LogHandler(logging.Handler):
    """Send log records to the app, so they don't write over the screen."""

    def __init__(self, app: MonitorApp) -> None:
        super().__init__()
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%H:%M:%S"
            )
        )
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        self._app.post_message(MonitorApp.LogLine(self.format(record)))


class MonitorApp(SignalSafeApp[None]):
    """Last value of each coil, with logging output below once there is any."""

    TITLE = "NIBE monitor"
    CSS = """
    #values { height: 2fr; }
    #log { height: 1fr; border-top: solid $primary; display: none; }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("escape", "quit", "Quit", show=False, priority=True),
    ]

    class CoilUpdated(Message):
        """A coil value was received."""

        def __init__(self, data: CoilData) -> None:
            super().__init__()
            self.data = data

    class LogLine(Message):
        """A log record to show in the log."""

        def __init__(self, line: str) -> None:
            super().__init__()
            self.line = line

    def __init__(self) -> None:
        super().__init__()
        self._counts: dict[int, int] = {}
        self._log_handler = _LogHandler(self)
        self._root_handlers: list[logging.Handler] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="values", cursor_type="row", zebra_stripes=True)
        yield Log(id="log", max_lines=1000)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#values", DataTable)
        for column in COLUMNS:
            table.add_column(column, key=column.lower())

        root = logging.getLogger()
        self._root_handlers = root.handlers[:]
        root.handlers = [self._log_handler]

    def on_unmount(self) -> None:
        logging.getLogger().handlers = self._root_handlers

    def update_coil(self, data: CoilData) -> None:
        """Show a received coil value, for HeatPump.COIL_UPDATE_EVENT."""
        self.post_message(self.CoilUpdated(data))

    def on_monitor_app_coil_updated(self, event: CoilUpdated) -> None:
        coil = event.data.coil
        seen = datetime.now().strftime("%H:%M:%S")
        value = "" if event.data.value is None else str(event.data.value)
        count = self._counts.get(coil.address, 0) + 1
        self._counts[coil.address] = count

        table = self.query_one("#values", DataTable)
        key = str(coil.address)
        if count == 1:
            table.add_row(
                coil.address, coil.title, value, coil.unit or "", seen, count, key=key
            )
            table.sort("address")
        else:
            table.update_cell(key, "value", value, update_width=True)
            table.update_cell(key, "seen", seen)
            table.update_cell(key, "count", count, update_width=True)

    def on_monitor_app_log_line(self, event: LogLine) -> None:
        log = self.query_one("#log", Log)
        log.display = True
        log.write_line(event.line)
