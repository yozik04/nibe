"""Interactive editor for LOG.SET files, built on textual."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import contextlib
from pathlib import Path
import signal

from rich.segment import Segment
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    SelectionList,
)
from textual.widgets.option_list import OptionDoesNotExist

from ..coil import Coil
from ..log_set import MODBUS40_SLOTS, coil_slots, format_log_set, log_set_slots

# Textual leaves the terminal in full screen raw mode if these end the process.
EXIT_SIGNALS = tuple(
    getattr(signal, name)
    for name in ("SIGTERM", "SIGHUP", "SIGINT")
    if hasattr(signal, name)
)


def _prompt(coil: Coil) -> str:
    prompt = f"{coil.address}  {coil.title}"
    if coil_slots(coil) > 1:
        prompt += " (32 bit)"
    return prompt


class FilterInput(Input):
    """Filter box, where up and down move on to the registers."""

    BINDINGS = [
        Binding("down", "app.focus('registers')", "Registers", show=False),
        Binding("up", "app.focus('registers')", "Registers", show=False),
    ]


class RegisterList(SelectionList[int]):
    """Selection list that leaves the box of unselected registers empty."""

    def render_line(self, y: int) -> Strip:
        line = super().render_line(y)
        try:
            selection = self.get_option_at_index(self.scroll_offset.y + y)
        except OptionDoesNotExist:
            return line
        segments = list(line)
        if (
            selection.value in self.selected
            or len(segments) < 2
            or segments[1].text != "X"
        ):
            return line
        segments[1] = Segment(" ", segments[1].style)
        return Strip(segments, line.cell_length)


class OrderList(ListView):
    """List of the chosen registers, where enter or space grabs one to move it."""

    BINDINGS = [
        Binding("enter", "select_cursor", "Grab", show=False),
        Binding("space", "select_cursor", "Grab"),
    ]

    class Move(Message):
        """Move the grabbed register by delta rows."""

        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    grabbed = False

    def set_grabbed(self, grabbed: bool) -> None:
        self.grabbed = grabbed
        self.set_class(grabbed, "grabbed")

    def action_select_cursor(self) -> None:
        if self.index is not None:
            self.set_grabbed(not self.grabbed)

    def action_cursor_up(self) -> None:
        if self.grabbed:
            self.post_message(self.Move(-1))
        else:
            super().action_cursor_up()

    def action_cursor_down(self) -> None:
        if self.grabbed:
            self.post_message(self.Move(1))
        else:
            super().action_cursor_down()

    def on_blur(self) -> None:
        self.set_grabbed(False)


class SaveScreen(ModalScreen[bool]):
    """Ask whether to save unsaved changes before closing."""

    CSS = """
    SaveScreen { align: center middle; }
    #dialog { width: auto; height: auto; padding: 1 2; border: thick $primary; }
    """
    BINDINGS = [
        Binding("s", "dismiss(True)", "Save"),
        Binding("d", "dismiss(False)", "Don't save"),
    ]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Save changes to {self._path}?")
            yield Label("[b]s[/b] save · [b]d[/b] don't save · [b]esc[/b] close")
        yield Footer()


class LogSetApp(App[None]):
    """Toggle the registers of a LOG.SET file and set their order."""

    TITLE = "LOG.SET"
    CSS = """
    #available { width: 3fr; }
    #chosen { width: 2fr; }
    #slots { padding: 0 1; }
    #slots.over { color: $error; text-style: bold; }
    OrderList.grabbed > ListItem.-highlight { background: $warning 50%; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("left", "focus('registers')", "Registers", show=False),
        Binding("right", "focus('order')", "Order", show=False),
        Binding("ctrl+c", "close", "Close", priority=True),
        Binding("escape", "close", "Close", show=False, priority=True),
    ]

    def __init__(
        self,
        coils: Iterable[Coil],
        selected: Iterable[int],
        path: Path,
        database_version: str,
    ) -> None:
        super().__init__()
        self._coils = {coil.address: coil for coil in coils}
        self._selected = [address for address in selected if address in self._coils]
        self._saved = list(self._selected)
        self._path = path
        self._database_version = database_version

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterInput(
            placeholder="Filter by address or title",
            select_on_focus=False,
            id="filter",
        )
        with Horizontal():
            with Vertical(id="available"):
                yield RegisterList(id="registers")
            with Vertical(id="chosen"):
                yield Label(id="slots")
                yield OrderList(id="order")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self._path)
        self._show_registers("")
        self._show_order()
        loop = asyncio.get_running_loop()
        for signum in EXIT_SIGNALS:
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(signum, self.exit)

    def on_unmount(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in EXIT_SIGNALS:
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(signum)

    def _show_registers(self, text: str) -> None:
        registers = self.query_one("#registers", SelectionList)
        registers.clear_options()
        text = text.lower()
        registers.add_options(
            (_prompt(coil), coil.address, coil.address in self._selected)
            for coil in self._coils.values()
            if text in str(coil.address) or text in coil.title.lower()
        )

    def _show_order(self) -> None:
        coils = [self._coils[address] for address in self._selected]
        slots = log_set_slots(coils)
        label = self.query_one("#slots", Label)
        label.update(f"Slots {slots}/{MODBUS40_SLOTS}")
        label.set_class(slots > MODBUS40_SLOTS, "over")

        order = self.query_one("#order", OrderList)
        order.clear()
        order.extend(ListItem(Label(_prompt(coil))) for coil in coils)

    def action_focus(self, widget_id: str) -> None:
        self.query_one(f"#{widget_id}").focus()

    def on_key(self, event: events.Key) -> None:
        """Send typing in the lists to the filter box."""
        if isinstance(self.screen, SaveScreen):
            return
        filter_input = self.query_one("#filter", FilterInput)
        if self.focused is filter_input:
            return
        if event.key == "backspace":
            filter_input.focus()
            filter_input.action_end()
            filter_input.action_delete_left()
        elif event.is_printable and event.character and event.character != " ":
            filter_input.focus()
            filter_input.action_end()
            filter_input.insert_text_at_cursor(event.character)
        else:
            return
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._show_registers(event.value)

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled
    ) -> None:
        address = event.selection.value
        if address in self._selected:
            self._selected.remove(address)
        else:
            self._selected.append(address)
        self._show_order()

    def on_order_list_move(self, event: OrderList.Move) -> None:
        order = self.query_one("#order", OrderList)
        index = order.index
        if index is None:
            return
        target = index + event.delta
        if not 0 <= target < len(self._selected):
            return
        selected = self._selected
        selected[index], selected[target] = selected[target], selected[index]
        for row in (index, target):
            label = order.children[row].query_one(Label)
            label.update(_prompt(self._coils[selected[row]]))
        order.index = target

    def action_close(self) -> None:
        if isinstance(self.screen, SaveScreen):
            self.exit()
            return
        order = self.query_one("#order", OrderList)
        if order.grabbed:
            order.set_grabbed(False)
            return
        if self._selected == self._saved:
            self.exit()
            return

        def close(save: bool | None) -> None:
            if save:
                self.action_save()
            self.exit()

        self.push_screen(SaveScreen(self._path), close)

    def action_save(self) -> None:
        coils = [self._coils[address] for address in self._selected]
        self._path.write_bytes(
            format_log_set(coils, database_version=self._database_version)
        )
        self._saved = list(self._selected)
        slots = log_set_slots(coils)
        if slots > MODBUS40_SLOTS:
            self.notify(
                f"Saved {self._path}. MODBUS40 only sends the first"
                f" {MODBUS40_SLOTS} of {slots} slots.",
                severity="warning",
            )
        else:
            self.notify(f"Saved {self._path}")
