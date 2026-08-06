"""RF front-end guide: antenna / filter / LNA recommendations per band.

Sensitivity is dominated by the front end, not the SDR. This module turns the
ROADMAP's collection-hardware notes into an actionable recommendation for a
given frequency (or a whole-spectrum guide), surfaced via ``doctor --rf`` and
``at``. Guidance only — receive-side, no transmit implication.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FrontEnd:
    band: str
    antenna: str
    filter: str
    lna: str
    note: str = ""


# (low_hz, high_hz, FrontEnd). Ordered; first match wins.
_TABLE = [
    (0, 30_000_000, FrontEnd(
        "HF (<30 MHz)", "Resonant dipole / random-wire + 9:1 unun",
        "HF band-pass or a broadcast-AM notch",
        "Not usually needed (HF noise-limited)",
        "The HackRF is weak below ~30 MHz — an upconverter or an RTL-SDR in "
        "direct-sampling mode often does better here.")),
    (30_000_000, 108_000_000, FrontEnd(
        "VHF low / FM (30–108 MHz)", "Discone (wideband) or a tuned telescopic",
        "FM broadcast notch (88–108) to stop desense",
        "Optional LNA for weak VHF",
        "Strong FM broadcast is the #1 desense source here — a notch helps a lot.")),
    (108_000_000, 138_000_000, FrontEnd(
        "Airband (108–137 MHz)", "1/4-wave VHF whip or airband dipole",
        "Airband band-pass",
        "LNA helps at range",
        "AM voice; keep FM broadcast out with a filter.")),
    (138_000_000, 400_000_000, FrontEnd(
        "VHF/UHF (138–400 MHz)", "Discone or a tuned whip",
        "Band-pass for the target sub-band",
        "LNA + bias-tee for weak signals",
        "Marine (156–162) and satellite (137) live here.")),
    (400_000_000, 470_000_000, FrontEnd(
        "70cm / ISM 433 (400–470 MHz)", "Tuned 433 whip (best) or discone",
        "433 band-pass (huge help in RF-dense sites)",
        "LNA + bias-tee",
        "The busiest hobby ISM band; a band-pass sharpens weak captures.")),
    (470_000_000, 960_000_000, FrontEnd(
        "UHF / ISM 868–915 (470–960 MHz)", "Tuned 868/915 whip",
        "868 or 915 band-pass; cellular notch if near towers",
        "LNA + bias-tee",
        "Watch for strong cellular/pager desense; filter it out.")),
    (960_000_000, 1_100_000_000, FrontEnd(
        "L-band / ADS-B 1090 (960–1100 MHz)", "Resonant 1090 antenna (collinear)",
        "1090 SAW band-pass (essential in cities)",
        "1090 LNA + bias-tee (big range gain)",
        "ADS-B/UAT; a SAW filter + LNA transforms coverage.")),
    (1_100_000_000, 1_700_000_000, FrontEnd(
        "GNSS / L-band (1.1–1.7 GHz)", "Active GNSS patch (receive-only)",
        "GNSS band-pass",
        "Active antenna includes an LNA (needs bias-tee)",
        "For GNSS *monitoring* only — RFHound never transmits here.")),
    (1_700_000_000, 6_000_000_000, FrontEnd(
        "SHF / 2.4–5.8 GHz (1.7–6 GHz)", "Patch or Yagi (directional) / wideband horn",
        "Band-pass for the target",
        "Low-noise SHF LNA + bias-tee",
        "Short coax runs matter a lot at these frequencies.")),
]


def recommend(freq_mhz: float) -> FrontEnd | None:
    """Front-end recommendation for a frequency, or None if out of range."""
    hz = freq_mhz * 1e6
    for lo, hi, fe in _TABLE:
        if lo <= hz < hi:
            return fe
    return None


def guide() -> list:
    """The full band-by-band front-end table."""
    return [fe for _, _, fe in _TABLE]


GENERAL_NOTES = [
    "Antenna choice is the #1 sensitivity factor — a resonant/tuned antenna "
    "beats a generic whip by many dB.",
    "An LNA at the antenna raises weak signals above the HackRF's noise figure; "
    "power it with the bias-tee (config: antenna_power / --bias).",
    "A band-pass (or notch) filter stops strong out-of-band signals (FM, "
    "cellular, pagers) from desensitising the front end or creating images.",
    "For DF/TDOA: share an external 10 MHz reference (GPSDO) and a PPS mark "
    "across receivers; use an Opera Cake to switch antennas/filters by band.",
    "Transmit testing belongs only inside a shielded enclosure / Faraday tent.",
]
