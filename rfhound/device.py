"""HackRF device detection and info via ``hackrf_info``."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import proc
from .exceptions import DependencyMissingError, DeviceError


@dataclass
class HackRFInfo:
    found: bool
    serial: str | None = None
    board_id: str | None = None
    firmware: str | None = None
    part_id: str | None = None
    raw: str = ""


def get_info() -> HackRFInfo:
    """Query the attached HackRF. Raises DeviceError if none is present."""
    try:
        result = proc.run(["hackrf_info"], timeout=15, check=False)
    except DependencyMissingError:
        raise
    out = (result.stdout or "") + (result.stderr or "")

    if "No HackRF boards found" in out or "hackrf_open() failed" in out:
        raise DeviceError(
            "No HackRF detected. Check USB connection and permissions "
            "(you may need udev rules / to be in the 'plugdev' group)."
        )
    if result.returncode != 0 and "Serial number" not in out:
        raise DeviceError(f"hackrf_info failed:\n{out.strip()}")

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, out)
        return m.group(1).strip() if m else None

    return HackRFInfo(
        found=True,
        serial=grab(r"Serial number:\s*(\S+)"),
        board_id=grab(r"Board ID Number:\s*(.+)"),
        firmware=grab(r"Firmware Version:\s*(.+)"),
        part_id=grab(r"Part ID Number:\s*(.+)"),
        raw=out.strip(),
    )


def is_present() -> bool:
    """Best-effort check that a HackRF is attached (never raises)."""
    try:
        return get_info().found
    except (DeviceError, DependencyMissingError):
        return False
