import asyncio
import os
import signal

import pytest

from nibe.console_scripts.cli import run_tui


class FakeApp:
    def __init__(self, signum: int):
        self.signum = signum
        self.closed = asyncio.Event()

    def exit(self):
        self.closed.set()

    async def run_async(self):
        os.kill(os.getpid(), self.signum)
        await asyncio.wait_for(self.closed.wait(), 1)


@pytest.mark.skipif(os.name != "posix", reason="Needs POSIX signals")
@pytest.mark.parametrize("signum", ["SIGTERM", "SIGHUP"])
async def test_run_tui_exits_on_signal(signum: str):
    signum = getattr(signal, signum)
    previous = signal.getsignal(signum)

    await run_tui(FakeApp(signum))

    assert signal.getsignal(signum) is previous
