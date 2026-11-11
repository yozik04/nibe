"""Shared base for the textual apps of nibe-cli."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from textual.app import App, ReturnType

# Textual leaves the terminal in full screen raw mode if these end the process.
EXIT_SIGNALS = tuple(
    getattr(signal, name)
    for name in ("SIGTERM", "SIGHUP", "SIGINT")
    if hasattr(signal, name)
)


class SignalSafeApp(App[ReturnType]):
    """App that exits cleanly, restoring the terminal, on termination signals."""

    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in EXIT_SIGNALS:
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(signum, self.exit)

    def on_unmount(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in EXIT_SIGNALS:
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(signum)
