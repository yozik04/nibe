"""Shared base for the textual apps of nibe-cli."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import Any

from textual.app import App, ReturnType

# Textual leaves the terminal in full screen raw mode if these end the process.
EXIT_SIGNALS = tuple(
    getattr(signal, name)
    for name in ("SIGTERM", "SIGHUP", "SIGINT")
    if hasattr(signal, name)
)


class SignalSafeApp(App[ReturnType]):
    """App that exits cleanly, restoring the terminal, on termination signals."""

    _previous_handlers: dict[int, Any] = {}

    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        self._previous_handlers = {}
        for signum in EXIT_SIGNALS:
            previous = signal.getsignal(signum)
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(signum, self.exit)
                self._previous_handlers[signum] = previous

    def on_unmount(self) -> None:
        loop = asyncio.get_running_loop()
        for signum, previous in self._previous_handlers.items():
            loop.remove_signal_handler(signum)
            if previous is not None:
                signal.signal(signum, previous)
