"""Tiny OUI → vendor lookup for Wi-Fi/BLE addresses.

The first 24 bits of a MAC / BT address are an IEEE-assigned Organizationally
Unique Identifier. The full registry is huge; this is a curated subset of common
consumer/IoT vendors — enough to annotate a scan with a likely maker (a helpful
identification cue, not authoritative). Locally-administered addresses (the
random MACs phones use for privacy) are reported as such.
"""

from __future__ import annotations

# 24-bit OUI (upper-case, no separators) -> vendor. Curated common set.
_OUI = {
    "001451": "Apple", "3C0754": "Apple", "F0989D": "Apple", "A85C2C": "Apple",
    "AC1F74": "Apple", "DCA904": "Apple", "F80377": "Apple",
    "002567": "Samsung", "5CF6DC": "Samsung", "8425DB": "Samsung", "C0BDD1": "Samsung",
    "3C5AB4": "Google", "F4F5E8": "Google", "D8EB46": "Google",
    "001A11": "Google", "AC63BE": "Amazon", "68370E": "Amazon", "44650D": "Amazon",
    "F0272D": "Amazon", "B8278D": "Microsoft", "000D3A": "Microsoft",
    "001320": "Intel", "3480B3": "Intel", "A0C589": "Intel", "8CF710": "Intel",
    "B827EB": "Raspberry Pi", "DCA632": "Raspberry Pi", "E45F01": "Raspberry Pi",
    "246F28": "Espressif (ESP32)", "3C6105": "Espressif", "A020A6": "Espressif",
    "8C858C": "Espressif", "7CDFA1": "Espressif",
    "50C7BF": "TP-Link", "A42BB0": "TP-Link", "C46E1F": "TP-Link",
    "204E7F": "Netgear", "A040A0": "Netgear", "9C3DCF": "Netgear",
    "0018F3": "ASUS", "AC220B": "ASUS", "001517": "Cisco", "00000C": "Cisco",
    "B8E937": "Sonos", "5CAAFD": "Sonos", "000E58": "Sonos",
    "001D4F": "Apple", "D0817A": "Apple", "F0D1A9": "Apple",
    "FCE998": "Fitbit", "20C6EB": "Fitbit",
}


def _norm(addr: str) -> str:
    return "".join(c for c in (addr or "") if c.isalnum()).upper()


def is_locally_administered(addr: str) -> bool:
    """True if the address is randomized/private (2nd-LSB of the first octet set)."""
    h = _norm(addr)
    if len(h) < 2:
        return False
    try:
        return bool(int(h[:2], 16) & 0x02)
    except ValueError:
        return False


def lookup(addr: str) -> str:
    """Vendor name for an address, 'random/private' for LAA, or '' if unknown."""
    h = _norm(addr)
    if len(h) < 6:
        return ""
    v = _OUI.get(h[:6])
    if v:
        return v
    if is_locally_administered(addr):
        return "random/private"
    return ""
