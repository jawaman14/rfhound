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

from datetime import datetime, timezone

from .config import Config, TxAllowRange, save_config
from .exceptions import SafetyError

# HackRF hardware limits (Hz).
HW_MIN_HZ = 1_000_000
HW_MAX_HZ = 6_000_000_000

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
    if not cfg.is_tx_range_allowed(freq_hz):
        ranges = ", ".join(
            f"{r.low_hz}-{r.high_hz} Hz" for r in cfg.tx_allow_ranges
        ) or "(none)"
        raise SafetyError(
            f"Transmit blocked: {freq_hz} Hz is not inside any declared "
            f"allow-range. Allowed: {ranges}."
        )
