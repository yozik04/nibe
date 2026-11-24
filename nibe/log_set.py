"""Create and read LOG.SET files for MODBUS40.

LOG.SET is read from a USB stick by F series pumps. It selects the registers
MODBUS40 sends without being asked, in the order of the file.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .coil import Coil

DATABASE_VERSION = "8310"
MODBUS40_SLOTS = 20
ENCODING = "latin-1"
NEWLINE = "\r\n"


def coil_slots(coil: Coil) -> int:
    """Return the number of MODBUS40 slots a coil takes, 2 for 32 bit coils."""
    return 2 if coil.size in ("u32", "s32") else 1


def log_set_slots(coils: Iterable[Coil]) -> int:
    """Return the number of MODBUS40 slots the coils take."""
    return sum(coil_slots(coil) for coil in coils)


def _label(coil: Coil) -> str:
    if coil.unit:
        return f"{coil.title} [{coil.unit}]"
    return coil.title


def format_log_set(
    coils: Iterable[Coil],
    *,
    created: date | None = None,
    database_version: str = DATABASE_VERSION,
) -> bytes:
    """Return the content of a LOG.SET file logging the coils, in order.

    MODBUS40 only sends the first MODBUS40_SLOTS slots, see log_set_slots.
    """
    coils = list(coils)
    created = created or date.today()
    rows = [
        [f"[NIBL;{created:%Y%m%d};{database_version}]"],
        ["Divisors", "", *(str(coil.factor) for coil in coils)],
        ["Date", "Time", *(_label(coil) for coil in coils)],
        *([str(coil.address)] for coil in coils),
    ]
    text = NEWLINE.join("\t".join(row) for row in rows)
    return text.encode(ENCODING, errors="replace")


def parse_log_set(data: bytes) -> list[int]:
    """Return the coil addresses in a LOG.SET file, in order."""
    lines = data.decode(ENCODING).splitlines()
    if not lines or not lines[0].startswith("[NIBL"):
        raise ValueError("Not a LOG.SET file")
    return [int(line.split("\t")[0]) for line in lines[3:] if line.strip()]
