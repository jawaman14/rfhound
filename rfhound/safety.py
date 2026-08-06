"""Transmit safety subsystem.

RFHound is receive-first. Any action that keys the transmitter (replay, signal
generation) must pass through :func:`authorize_tx`. This is a deliberate,
conservative gate — not security theatre — because unlicensed transmission is
illegal in essentially every jurisdiction.

Design rules enforced here:

* Transmit is disabled unless the operator explicitly enabled it in config and
  recorded consent to the legal terms.
* Every transmit target frequency must fall inside an operator-declared
  allow-range. There is no "allow all".
* An explicit per-invocation ``authorized=True`` flag is still required, so a
  stored config alone cannot silently transmit.

Intentionally *not* provided anywhere in RFHound: broadband jamming, continuous
noise / denial-of-service, protocol deauth floods, or rolling-code brute-force.
Those are excluded by design; see ``docs/LEGAL.md``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, TxAllowRange, config_path, save_config
from .exceptions import SafetyError

# HackRF hardware limits (Hz).
HW_MIN_HZ = 1_000_000
HW_MAX_HZ = 6_000_000_000

# Safety-of-life / GNSS bands. Transmitting here endangers navigation, aviation,
# or distress systems and is essentially never legal for an operator. These are
# HARD-refused even if the operator allow-listed a range that covers them — the
# allow-list expresses intent, but nothing overrides a safety-of-life block.
PROTECTED_BANDS = [
    (108_000_000, 137_000_000, "Aviation VHF (ILS/VOR/comms incl. 121.5 emergency)"),
    (156_700_000, 156_900_000, "Marine VHF Ch16 distress"),
    (161_900_000, 162_050_000, "AIS marine safety"),
    (406_000_000, 406_100_000, "COSPAS-SARSAT distress beacons (EPIRB/PLB/ELT)"),
    (976_000_000, 980_000_000, "Aviation UAT 978 (ADS-B)"),
    (1_087_000_000, 1_093_000_000, "ADS-B 1090 (aviation surveillance)"),
    (1_164_000_000, 1_300_000_000, "GNSS L2/L5/E6 (GPS/GLONASS/Galileo)"),
    (1_525_000_000, 1_660_500_000, "GNSS L1 / satellite (GPS/GLONASS/Galileo/Iridium/Inmarsat)"),
]


def protected_band(freq_hz: int) -> str | None:
    """Return the name of the safety-of-life band containing *freq_hz*, or None."""
    for lo, hi, name in PROTECTED_BANDS:
        if lo <= freq_hz <= hi:
            return name
    return None


CONSENT_TEXT = """\
By enabling transmit you confirm ALL of the following:
  1. You are legally authorized to transmit on the frequencies you will use
     (you hold the licence, own the spectrum, or are inside a shielded lab /
     Faraday enclosure), AND
  2. You have written permission to test any device or system you target, AND
  3. You accept full responsibility for complying with your local radio
     regulations.
RFHound will only transmit inside frequency ranges you explicitly declare.
"""


def within_hardware_range(freq_hz: int) -> bool:
    return HW_MIN_HZ <= freq_hz <= HW_MAX_HZ


def record_consent(cfg: Config, jurisdiction: str = "") -> Config:
    """Mark that the operator has accepted the transmit legal terms."""
    cfg.tx_consent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if jurisdiction:
        cfg.jurisdiction = jurisdiction
    return cfg


def enable_tx(
    cfg: Config,
    allow_ranges: list[TxAllowRange],
    *,
    jurisdiction: str = "",
    persist: bool = True,
) -> Config:
    """Enable transmit with an explicit allow-list. Records consent + saves."""
    if not allow_ranges:
        raise SafetyError(
            "Refusing to enable transmit with an empty allow-list. Declare at "
            "least one frequency range you are authorized to transmit in."
        )
    for r in allow_ranges:
        if not (within_hardware_range(r.low_hz) and within_hardware_range(r.high_hz)):
            raise SafetyError(
                f"Allow-range {r.low_hz}-{r.high_hz} Hz is outside the HackRF "
                f"hardware range ({HW_MIN_HZ}-{HW_MAX_HZ} Hz)."
            )
        if r.low_hz > r.high_hz:
            raise SafetyError(f"Allow-range low {r.low_hz} > high {r.high_hz}.")
    cfg.tx_enabled = True
    cfg.tx_allow_ranges = allow_ranges
    cfg = record_consent(cfg, jurisdiction)
    if persist:
        save_config(cfg)
    return cfg


def disable_tx(cfg: Config, *, persist: bool = True) -> Config:
    cfg.tx_enabled = False
    if persist:
        save_config(cfg)
    return cfg


def authorize_tx(cfg: Config, freq_hz: int, *, authorized: bool) -> None:
    """Raise SafetyError unless it is safe & permitted to transmit at *freq_hz*.

    All of the following must hold:
      * caller passed authorized=True for this specific action;
      * config has tx_enabled and recorded consent;
      * freq is inside the HackRF hardware range;
      * freq is inside a declared allow-range.
    """
    if not authorized:
        raise SafetyError(
            "Transmit blocked: this action requires an explicit authorization "
            "flag (e.g. --authorized on the CLI)."
        )
    if not cfg.tx_enabled:
        raise SafetyError(
            "Transmit blocked: transmit is disabled. Enable it first with "
            "'rfhound tx enable' after reading the legal terms."
        )
    if not cfg.tx_consent_at:
        raise SafetyError("Transmit blocked: legal consent has not been recorded.")
    if not within_hardware_range(freq_hz):
        raise SafetyError(
            f"Transmit blocked: {freq_hz} Hz is outside the HackRF hardware "
            f"range ({HW_MIN_HZ}-{HW_MAX_HZ} Hz)."
        )
    protected = protected_band(freq_hz)
    if protected:
        raise SafetyError(
            f"Transmit blocked: {freq_hz / 1e6:.4f} MHz is a safety-of-life band "
            f"({protected}). RFHound refuses to transmit here regardless of the "
            f"allow-list — transmitting risks lives and is not permitted."
        )
    if not cfg.is_tx_range_allowed(freq_hz):
        ranges = ", ".join(
            f"{r.low_hz}-{r.high_hz} Hz" for r in cfg.tx_allow_ranges
        ) or "(none)"
        raise SafetyError(
            f"Transmit blocked: {freq_hz} Hz is not inside any declared "
            f"allow-range. Allowed: {ranges}."
        )


# --------------------------------------------------------------------------- #
# Transmit audit log — an append-only record of every transmit attempt (real,
# blocked, or dry-run), so any use of the radio is accountable.
# --------------------------------------------------------------------------- #
def tx_audit_path() -> Path:
    return config_path().parent / "tx_audit.log"


def record_tx_event(*, freq_hz, sample_rate, gain, duration_s, authorized,
                    dry_run, outcome, reason="") -> dict:
    """Append one transmit event to the audit log (best-effort; never raises)."""
    entry = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "freq_hz": freq_hz, "freq_mhz": round(freq_hz / 1e6, 4) if freq_hz else None,
        "sample_rate": sample_rate, "tx_gain": gain,
        "duration_s": round(duration_s, 3) if duration_s is not None else None,
        "authorized": bool(authorized), "dry_run": bool(dry_run),
        "outcome": outcome, "reason": reason,
    }
    try:
        p = tx_audit_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return entry


def read_tx_audit(limit: int = 50) -> list:
    p = tx_audit_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def clear_tx_audit() -> int:
    p = tx_audit_path()
    n = len(read_tx_audit(10 ** 9))
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
    return n
