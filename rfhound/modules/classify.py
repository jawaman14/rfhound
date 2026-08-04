"""Signal auto-matching / classification.

Given what a sweep can measure about an unknown emitter — its **frequency**, and
optionally its **bandwidth** and **modulation** — this ranks the likely signal
types with a confidence score and points you at the decoder to try.

It's a heuristic (frequency allocation + typical bandwidth + modulation), not a
neural classifier, so it's explainable: every guess comes with the reasons that
produced its score. Pair it with `rfhound at <freq>` to go from "what is this?"
to "how do I decode it?".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import bandplan


@dataclass
class Signature:
    name: str
    decoder: str | None
    category: str
    freqs: list             # list of (low_mhz, high_mhz)
    bw_khz: tuple | None     # (min, max) typical occupied bandwidth
    mods: tuple              # lowercase modulation names
    note: str = ""

    def contains(self, freq_mhz: float) -> bool:
        return any(lo <= freq_mhz <= hi for lo, hi in self.freqs)

    def narrowest_span(self, freq_mhz: float) -> float:
        spans = [hi - lo for lo, hi in self.freqs if lo <= freq_mhz <= hi]
        return min(spans) if spans else 1e9


# Curated signal signatures. Frequencies are regional; treated as candidates.
SIGNATURES: list[Signature] = [
    Signature("FM broadcast", None, "broadcast", [(87.5, 108.0)], (120, 200),
              ("wfm", "fm"), "Wideband FM; strong, easy first demod."),
    Signature("Aircraft VHF voice (AM)", None, "aviation", [(118.0, 137.0)], (6, 12),
              ("am",), "AM aircraft voice / navaids."),
    Signature("ACARS", "acars", "aviation", [(129.0, 137.0)], (2, 5),
              ("am", "msk"), "Aircraft text messaging ~131 MHz."),
    Signature("NOAA APT weather sat", "noaa_apt", "satellite", [(137.0, 138.0)], (30, 40),
              ("fm",), "Polar weather-sat image downlink."),
    Signature("APRS / packet", "aprs", "amateur", [(144.0, 148.0)], (10, 16),
              ("fsk", "afsk"), "AFSK1200 position/telemetry."),
    Signature("AIS (marine)", "ais", "maritime", [(161.9, 162.05)], (20, 30),
              ("gmsk", "fsk"), "Ship position beacons at 161.975/162.025."),
    Signature("POCSAG/FLEX pager", "pocsag", "paging", [(137.0, 160.0), (929.0, 932.0)],
              (10, 25), ("fsk",), "Often unencrypted paging."),
    Signature("Marine/LMR voice", None, "voice", [(150.0, 174.0), (380.0, 470.0)], (11, 25),
              ("fm",), "Land-mobile / marine NBFM voice."),
    Signature("DMR/P25 digital voice", "dsd", "voice", [(380.0, 470.0)], (7, 14),
              ("fsk", "c4fm", "psk"), "Digital voice (if unencrypted)."),
    Signature("TETRA", "tetra", "voice", [(380.0, 430.0)], (20, 28),
              ("psk",), "TETRA trunked (if unencrypted)."),
    Signature("ISM remote/sensor (OOK)", "rtl433", "ism",
              [(314.9, 315.1), (433.05, 434.79), (863.0, 870.0), (902.0, 928.0)],
              (10, 200), ("ook", "ask"), "Fobs, doorbells, weather/PIR sensors, TPMS."),
    Signature("ISM sensor (FSK)", "rtl433", "ism",
              [(314.9, 315.1), (433.05, 434.79), (863.0, 870.0), (902.0, 928.0)],
              (20, 250), ("fsk", "gfsk"), "Many IoT/telemetry sensors."),
    Signature("LoRa", None, "iot", [(433.05, 434.79), (863.0, 870.0), (902.0, 928.0)],
              (125, 500), ("chirp", "css"), "Chirp-spread-spectrum long-range IoT."),
    Signature("Smart meter (ERT)", "ert", "ism", [(902.0, 928.0)], (30, 120),
              ("ook", "fsk"), "Utility metering ~912 MHz."),
    Signature("GSM (2G)", None, "cellular", [(925.0, 960.0), (1805.0, 1880.0)], (200, 200),
              ("gmsk",), "Legacy cellular downlink; 200 kHz carriers."),
    Signature("ADS-B UAT (978)", "uat978", "aviation", [(977.0, 979.0)], (1000, 1300),
              ("pulse",), "US GA ADS-B on 978 MHz."),
    Signature("ADS-B 1090ES", "adsb", "aviation", [(1089.0, 1091.0)], (1000, 2000),
              ("pulse", "ppm"), "Aircraft position/ID at 1090 MHz."),
    Signature("GPS L1", None, "gnss", [(1575.0, 1576.0)], (2000, 20000),
              ("bpsk",), "GNSS downlink; receive-only."),
    Signature("Iridium", "iridium", "satellite", [(1616.0, 1626.5)], (30, 40),
              ("qpsk",), "L-band satphone bursts."),
    Signature("DECT cordless", None, "voice", [(1880.0, 1930.0)], (1728, 1728),
              ("gfsk",), "Cordless phone."),
    Signature("Bluetooth / BLE", None, "ism", [(2400.0, 2483.5)], (1000, 2000),
              ("gfsk",), "1-2 MHz hopping channels."),
    Signature("Wi-Fi (2.4)", None, "ism", [(2400.0, 2483.5)], (20000, 40000),
              ("ofdm",), "20/40 MHz OFDM."),
    Signature("Drone FPV video", None, "cuas", [(1150.0, 1300.0), (5645.0, 5945.0)],
              (6000, 20000), ("fm", "ofdm"), "Analog/HD FPV downlink."),
    Signature("Wi-Fi (5)", None, "ism", [(5150.0, 5850.0)], (20000, 80000),
              ("ofdm",), "5 GHz OFDM."),
]


@dataclass
class Match:
    name: str
    decoder: str | None
    category: str
    likelihood: int          # 0..100
    reasons: list = field(default_factory=list)
    note: str = ""


def classify(freq_mhz: float, *, bandwidth_khz: float | None = None,
             modulation: str | None = None) -> list[Match]:
    """Rank likely signal types for an emitter at *freq_mhz*.

    Optional *bandwidth_khz* and *modulation* (e.g. "ook", "fsk", "ofdm")
    sharpen the ranking. Returns matches sorted by likelihood, highest first.
    """
    mod = modulation.lower().strip() if modulation else None
    out: list[Match] = []
    for sig in SIGNATURES:
        if not sig.contains(freq_mhz):
            continue
        score = 45.0
        reasons = [f"frequency falls in {sig.name} allocation"]

        # Specificity: a narrow, dedicated allocation is a stronger cue.
        span = sig.narrowest_span(freq_mhz)
        if span <= 2:
            score += 22
            reasons.append("narrow dedicated band")
        elif span <= 20:
            score += 12
        else:
            score += 4

        # Bandwidth agreement.
        if bandwidth_khz is not None and sig.bw_khz:
            lo, hi = sig.bw_khz
            if lo * 0.5 <= bandwidth_khz <= hi * 2.0:
                score += 25
                reasons.append(f"bandwidth ~{bandwidth_khz:.0f} kHz fits {lo}-{hi} kHz")
            else:
                score -= 22
                reasons.append(f"bandwidth ~{bandwidth_khz:.0f} kHz unlike {lo}-{hi} kHz")

        # Modulation agreement.
        if mod:
            if mod in sig.mods:
                score += 20
                reasons.append(f"modulation '{mod}' matches")
            else:
                score -= 15
                reasons.append(f"modulation '{mod}' not typical")

        score = max(0, min(100, int(round(score))))
        out.append(Match(sig.name, sig.decoder, sig.category, score, reasons, sig.note))

    if not out:
        band = bandplan.find_band(int(freq_mhz * 1e6))
        if band:
            out.append(Match(band.name, band.decoder, band.category, 30,
                             ["only a broad band-plan match at this frequency"],
                             band.description))
        else:
            out.append(Match("Unknown", None, "unknown", 0,
                             ["frequency is outside the known band plan"], ""))

    out.sort(key=lambda m: m.likelihood, reverse=True)
    # Light normalisation so the field reads like a probability spread.
    return out


def estimate_bandwidth_khz(result, peak_freq_hz: int, *, db_down: float = 6.0) -> float | None:
    """Estimate a peak's occupied bandwidth from sweep bins (−db_down threshold).

    Walks outward from the peak bin while power stays within *db_down* of the
    peak, returning the span in kHz. Returns None if the sweep is too coarse.
    """
    bins = sorted(result.bins, key=lambda b: b.freq_hz)
    if len(bins) < 3:
        return None
    # Find the nearest bin to the peak.
    idx = min(range(len(bins)), key=lambda i: abs(bins[i].freq_hz - peak_freq_hz))
    peak_db = bins[idx].power_db
    thresh = peak_db - db_down
    lo = hi = idx
    while lo > 0 and bins[lo - 1].power_db >= thresh:
        lo -= 1
    while hi < len(bins) - 1 and bins[hi + 1].power_db >= thresh:
        hi += 1
    span_hz = bins[hi].freq_hz - bins[lo].freq_hz
    if span_hz <= 0:
        # single-bin peak: use the bin width as a lower bound
        if len(bins) >= 2:
            span_hz = abs(bins[1].freq_hz - bins[0].freq_hz)
        else:
            return None
    return round(span_hz / 1000.0, 1)


def best_guess(freq_mhz: float, bandwidth_khz: float | None = None) -> Match:
    """Convenience: the single most-likely match."""
    return classify(freq_mhz, bandwidth_khz=bandwidth_khz)[0]
