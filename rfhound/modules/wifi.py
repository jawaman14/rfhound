"""Wi-Fi as a passive RF source (2.4/5 GHz APs with RSSI).

Uses the host's built-in Wi-Fi adapter via ``iw`` (RSSI in dBm) or ``nmcli``
(signal %, converted approximately) — **passive scanning only**. RFHound does no
Wi-Fi transmission, deauth, injection, monitor-mode attack, or evil-twin
creation; it only enumerates APs and flags defensive signatures (evil-twin,
open networks, rogue vs a baseline). See ``docs/LEGAL.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import proc


@dataclass
class WifiAp:
    bssid: str
    ssid: str
    rssi_dbm: float
    channel: int | None = None
    freq_mhz: float | None = None
    security: str = ""

    @property
    def band(self) -> str:
        if self.freq_mhz is None:
            return "?"
        if self.freq_mhz < 2500:
            return "2.4GHz"
        if self.freq_mhz < 5900:
            return "5GHz"
        return "6GHz"


@dataclass
class WifiFinding:
    indicator: str
    detail: str
    severity: str = "medium"


def available() -> tuple[bool, str]:
    """Is a Wi-Fi scan tool present? (Adapter presence is checked at scan time.)"""
    if proc.find_tool("iw"):
        return True, "iw"
    if proc.find_tool("nmcli"):
        return True, "nmcli"
    return False, "install 'iw' or NetworkManager (nmcli) for Wi-Fi scanning"


def _chan_from_freq(freq_mhz: float | None) -> int | None:
    if not freq_mhz:
        return None
    if 2412 <= freq_mhz <= 2472:
        return int((freq_mhz - 2407) / 5)
    if freq_mhz == 2484:
        return 14
    if 5000 <= freq_mhz <= 5900:
        return int((freq_mhz - 5000) / 5)
    return None


def _parse_iw(text: str) -> list:
    aps, cur = [], None
    for line in text.splitlines():
        m = re.match(r"BSS ([0-9a-fA-F:]{17})", line.strip())
        if m:
            if cur:
                aps.append(cur)
            cur = WifiAp(bssid=m.group(1).lower(), ssid="", rssi_dbm=-100.0)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("signal:"):
            try:
                cur.rssi_dbm = float(s.split()[1])
            except (ValueError, IndexError):
                pass
        elif s.startswith("freq:"):
            try:
                cur.freq_mhz = float(s.split()[1])
                cur.channel = _chan_from_freq(cur.freq_mhz)
            except (ValueError, IndexError):
                pass
        elif s.startswith("SSID:"):
            cur.ssid = s[5:].strip()
        elif "RSN" in s or "WPA" in s:
            cur.security = cur.security or ("WPA2/3" if "RSN" in s else "WPA")
    if cur:
        aps.append(cur)
    for a in aps:
        if not a.security:
            a.security = "open"
    return aps


def _parse_nmcli(text: str) -> list:
    # `nmcli -t -f BSSID,SSID,CHAN,FREQ,SIGNAL,SECURITY dev wifi list`
    # -t escapes colons in fields with a backslash; unescape.
    aps = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = re.split(r"(?<!\\):", line)
        parts = [p.replace("\\:", ":") for p in parts]
        if len(parts) < 6:
            continue
        bssid, ssid, chan, freq, signal, security = parts[:6]
        try:
            pct = float(signal)
        except ValueError:
            pct = 0.0
        aps.append(WifiAp(
            bssid=bssid.lower(), ssid=ssid,
            rssi_dbm=round(pct / 2.0 - 100.0, 1),   # rough %→dBm
            channel=int(chan) if chan.isdigit() else None,
            freq_mhz=float(freq.split()[0]) if freq else None,
            security=(security or "open")))
    return aps


def scan_wifi(*, iface: str | None = None, timeout: int = 20) -> list:
    """Passive Wi-Fi scan → list[WifiAp]. Raises RuntimeError if no tool/adapter."""
    ok, tool = available()
    if not ok:
        raise RuntimeError(tool)
    if tool == "iw":
        dev = iface or "wlan0"
        r = proc.run(["iw", "dev", dev, "scan"], check=False, timeout=timeout)
        if r.returncode != 0:
            # Fall back to nmcli if iw failed (needs root / wrong iface).
            if proc.find_tool("nmcli"):
                tool = "nmcli"
            else:
                raise RuntimeError((r.stderr or "iw scan failed").splitlines()[0])
        else:
            return sorted(_parse_iw(r.stdout), key=lambda a: a.rssi_dbm, reverse=True)
    cmd = ["nmcli", "-t", "-f", "BSSID,SSID,CHAN,FREQ,SIGNAL,SECURITY", "dev", "wifi", "list"]
    r = proc.run(cmd, check=False, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "nmcli scan failed").splitlines()[0])
    return sorted(_parse_nmcli(r.stdout), key=lambda a: a.rssi_dbm, reverse=True)


def analyze_wifi(aps: list, *, baseline_bssids: set | None = None) -> list:
    """Flag defensive Wi-Fi signatures: evil-twin, open nets, rogue vs baseline."""
    findings: list = []
    by_ssid: dict = {}
    for a in aps:
        if a.ssid:
            by_ssid.setdefault(a.ssid, set()).add(a.bssid)
    for ssid, bssids in by_ssid.items():
        if len(bssids) > 1:
            findings.append(WifiFinding(
                "evil-twin?", f"SSID '{ssid}' advertised by {len(bssids)} different "
                f"BSSIDs — possible evil-twin / rogue AP.", "high"))
    for a in aps:
        if a.security == "open" and a.ssid:
            findings.append(WifiFinding(
                "open-network", f"'{a.ssid}' ({a.bssid}) is open (no encryption).", "low"))
    if baseline_bssids is not None:
        for a in aps:
            if a.bssid not in baseline_bssids:
                findings.append(WifiFinding(
                    "new-ap", f"'{a.ssid or '(hidden)'}' ({a.bssid}) not in the baseline — "
                    f"new/rogue AP.", "medium"))
    return findings


def simulate_wifi() -> list:
    """A synthetic scan incl. an evil-twin pair and an open network."""
    return [
        WifiAp("aa:bb:cc:00:00:01", "HomeNet", -42.0, 6, 2437.0, "WPA2/3"),
        WifiAp("aa:bb:cc:00:00:02", "Cafe-Guest", -55.0, 11, 2462.0, "open"),
        WifiAp("de:ad:be:ef:00:01", "HomeNet", -71.0, 1, 2412.0, "open"),   # evil-twin
        WifiAp("aa:bb:cc:00:00:05", "Office-5G", -63.0, 36, 5180.0, "WPA2/3"),
    ]
