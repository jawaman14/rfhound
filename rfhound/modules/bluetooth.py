"""Bluetooth LE as a passive RF source (device discovery with RSSI).

Uses the host's built-in Bluetooth adapter via ``btmgmt find`` (RSSI) or
``bluetoothctl`` — **passive discovery only**. RFHound does no BLE advertising,
spoofing, pairing attacks, or jamming; it enumerates nearby devices and flags
defensive signatures (a persistent unknown device following you — e.g. an
unwanted tracker). See ``docs/LEGAL.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import proc

# Substrings that hint a device is a location tracker.
_TRACKER_HINTS = ("airtag", "tile", "smarttag", "chipolo", "trackr", "find my")


# Bluetooth Class-of-Device major device classes (bits 8–12).
_COD_MAJOR = {
    0: "misc", 1: "computer", 2: "phone", 3: "network", 4: "audio/video",
    5: "peripheral", 6: "imaging", 7: "wearable", 8: "toy", 9: "health",
}


def classify_cod(cod) -> str:
    """Major device class name from a Bluetooth Class-of-Device value."""
    try:
        val = int(cod, 16) if isinstance(cod, str) else int(cod)
    except (TypeError, ValueError):
        return ""
    return _COD_MAJOR.get((val >> 8) & 0x1F, "")


@dataclass
class BleDevice:
    addr: str
    name: str
    rssi_dbm: float
    kind: str = ""            # e.g. "tracker?"
    tech: str = "le"          # "le" (BLE) | "classic" (BR/EDR)

    @property
    def looks_like_tracker(self) -> bool:
        n = (self.name or "").lower()
        return any(h in n for h in _TRACKER_HINTS)


@dataclass
class BleFinding:
    indicator: str
    detail: str
    severity: str = "medium"


def available() -> tuple[bool, str]:
    if proc.find_tool("btmgmt"):
        return True, "btmgmt"
    if proc.find_tool("bluetoothctl"):
        return True, "bluetoothctl"
    return False, "install BlueZ (btmgmt / bluetoothctl) for Bluetooth scanning"


def _parse_btmgmt(text: str) -> list:
    devices: dict = {}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        m = re.search(r"dev_found:\s*([0-9A-Fa-f:]{17}).*?rssi\s*(-?\d+)", s)
        if m:
            addr = m.group(1).lower()
            cur = devices.setdefault(addr, BleDevice(addr, "", float(m.group(2))))
            cur.rssi_dbm = float(m.group(2))
            continue
        if cur is not None and s.lower().startswith("name"):
            cur.name = s.split(None, 1)[1].strip() if len(s.split(None, 1)) > 1 else cur.name
    out = list(devices.values())
    for d in out:
        if d.looks_like_tracker:
            d.kind = "tracker?"
    return out


def scan_ble(*, seconds: int = 8) -> list:
    """Passive BLE discovery → list[BleDevice]. Raises RuntimeError if unavailable."""
    ok, tool = available()
    if not ok:
        raise RuntimeError(tool)
    if tool == "btmgmt":
        r = proc.run(["btmgmt", "find"], check=False, timeout=seconds + 10)
        if r.returncode != 0 and not r.stdout:
            raise RuntimeError((r.stderr or "btmgmt find failed").splitlines()[0])
        return sorted(_parse_btmgmt(r.stdout), key=lambda d: d.rssi_dbm, reverse=True)
    # bluetoothctl fallback: a timed scan, then parse the [NEW]/RSSI lines.
    r = proc.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                 check=False, timeout=seconds + 10)
    devices: dict = {}
    for line in (r.stdout or "").splitlines():
        m = re.search(r"Device ([0-9A-Fa-f:]{17})\s*(.*)", line)
        if m:
            addr = m.group(1).lower()
            d = devices.setdefault(addr, BleDevice(addr, "", -100.0))
            rest = m.group(2).strip()
            if rest and not rest.startswith("RSSI"):
                d.name = rest
        rm = re.search(r"([0-9A-Fa-f:]{17}).*RSSI:\s*(?:0x[0-9a-fA-F]+ )?\(?(-?\d+)", line)
        if rm and rm.group(1).lower() in devices:
            devices[rm.group(1).lower()].rssi_dbm = float(rm.group(2))
    out = list(devices.values())
    for d in out:
        if d.looks_like_tracker:
            d.kind = "tracker?"
    return sorted(out, key=lambda d: d.rssi_dbm, reverse=True)


def analyze_ble(devices: list, *, seen_before: set | None = None) -> list:
    """Flag potential trackers and devices persisting across scans (following you)."""
    findings: list = []
    for d in devices:
        if d.looks_like_tracker:
            findings.append(BleFinding(
                "tracker", f"'{d.name}' ({d.addr}, {d.rssi_dbm:.0f} dBm) looks like a "
                f"location tracker.", "high"))
    if seen_before is not None:
        for d in devices:
            if d.addr in seen_before and not d.looks_like_tracker and d.rssi_dbm > -80:
                findings.append(BleFinding(
                    "persistent", f"{d.addr} ({d.rssi_dbm:.0f} dBm) seen across scans — "
                    f"a device staying near you.", "medium"))
    return findings


def scan_classic(*, seconds: int = 10) -> list:
    """Classic (BR/EDR) Bluetooth inquiry → list[BleDevice] (tech='classic').

    Classic inquiry (`hcitool scan`) yields address + name; RSSI is not exposed
    by a plain inquiry, so it's left None. Raises RuntimeError if unavailable.
    """
    if not proc.find_tool("hcitool"):
        raise RuntimeError("install bluez-utils (hcitool) for classic Bluetooth scanning")
    r = proc.run(["hcitool", "scan", "--flush"], check=False, timeout=seconds + 12)
    if r.returncode != 0 and not r.stdout:
        raise RuntimeError((r.stderr or "hcitool scan failed").splitlines()[0])
    out = []
    for line in (r.stdout or "").splitlines():
        m = re.search(r"([0-9A-Fa-f:]{17})\s+(.*)", line.strip())
        if m and "Scanning" not in line:
            name = m.group(2).strip()
            d = BleDevice(m.group(1).lower(), name if name != m.group(1) else "",
                          -100.0, tech="classic")
            if d.looks_like_tracker:
                d.kind = "tracker?"
            out.append(d)
    return out


def simulate_ble() -> list:
    """Synthetic BLE discovery incl. a tracker."""
    return [
        BleDevice("11:22:33:44:55:66", "AirTag", -58.0, "tracker?"),
        BleDevice("aa:11:bb:22:cc:33", "Fitbit Charge", -67.0),
        BleDevice("de:ad:be:ef:12:34", "", -74.0),
        BleDevice("77:88:99:aa:bb:cc", "JBL Speaker", -81.0),
    ]


def simulate_classic() -> list:
    """Synthetic classic (BR/EDR) inquiry results."""
    return [
        BleDevice("00:11:22:33:44:55", "Galaxy S23", -100.0, "phone", tech="classic"),
        BleDevice("66:77:88:99:aa:bb", "Bose QC45", -100.0, "audio/video", tech="classic"),
        BleDevice("cc:dd:ee:ff:00:11", "ThinkPad", -100.0, "computer", tech="classic"),
    ]
