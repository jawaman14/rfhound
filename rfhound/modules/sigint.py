"""SIGINT / EW-support tools (passive Electronic Support + Electronic Protection).

This is the collection-and-analysis side of electronic warfare — detecting,
measuring, cataloguing, characterising and locating emitters — plus the
protection side (recognising *how* you are being jammed). It is entirely
receive-and-analyse.

Intentionally **not** here: electronic attack (jamming, spoofing, deception,
DoS). RFHound characterises a jammer so you can defend; it never becomes one.

Capabilities:
  * ELINT pulse analysis — pulse width (PW), pulse repetition interval (PRI),
    duty and jitter from an IQ capture (radar/beacon-like emitters).
  * Interference / jamming characterisation — classify a jammer as barrage
    (broadband noise), spot (narrowband), multi-tone, or pulsed.
  * Emitter catalogue (Electronic Order of Battle) — a persistent list of
    observed emitters with their parameters, first/last-seen and counts.
  * Multi-node RSSI geolocation / DF — estimate an emitter's position from
    several receivers' signal-strength reports.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import bandplan


# --------------------------------------------------------------------------- #
# 1. ELINT pulse analysis
# --------------------------------------------------------------------------- #
@dataclass
class PulseProfile:
    pulses: int
    mean_pw_us: float
    mean_pri_us: float
    pri_jitter_us: float
    duty: float
    classification: str
    detail: str


def analyze_pulses(iq, sample_rate: int, *, thresh_frac: float = 0.5) -> PulseProfile:
    """Measure pulse parameters from a complex IQ array (ELINT)."""
    import numpy as np
    amp = np.abs(iq)
    if amp.size < 16 or amp.max() <= 0:
        return PulseProfile(0, 0, 0, 0, 0, "none", "no samples")
    n = amp / amp.max()
    on = n > thresh_frac
    duty = float(on.mean())
    # Edges.
    d = np.diff(on.astype(np.int8))
    rises = np.where(d == 1)[0]
    falls = np.where(d == -1)[0]
    us = 1e6 / sample_rate
    # Pair rises with the next fall to get pulse widths.
    widths = []
    for r in rises:
        nf = falls[falls > r]
        if nf.size:
            widths.append((nf[0] - r) * us)
    pris = (np.diff(rises) * us) if rises.size >= 2 else np.array([])
    mean_pw = float(np.mean(widths)) if widths else 0.0
    mean_pri = float(np.mean(pris)) if pris.size else 0.0
    jitter = float(np.std(pris)) if pris.size else 0.0

    if len(rises) >= 3 and mean_pri > 0 and jitter < 0.15 * mean_pri:
        cls = "pulsed — regular PRI (radar/beacon-like)"
    elif duty > 0.9:
        cls = "continuous wave"
    elif len(rises) >= 2:
        cls = "pulsed — irregular PRI"
    else:
        cls = "no clear pulses"
    detail = (f"{len(rises)} pulses, PW~{mean_pw:.1f}us, PRI~{mean_pri:.1f}us "
              f"(jitter {jitter:.1f}us), duty {duty:.2f}")
    return PulseProfile(len(rises), round(mean_pw, 2), round(mean_pri, 2),
                        round(jitter, 2), round(duty, 3), cls, detail)


def analyze_pulses_file(data_path: Path, *, max_samples: int = 1_000_000) -> PulseProfile:
    from . import iqtools
    meta = iqtools.read_sigmf_meta(data_path)
    iq = iqtools.load_iq(data_path, max_samples=max_samples)
    return analyze_pulses(iq, meta.sample_rate)


# --------------------------------------------------------------------------- #
# 2. Interference / jamming characterisation (Electronic Protection)
# --------------------------------------------------------------------------- #
@dataclass
class JammingProfile:
    kind: str            # none | barrage | spot | multi-tone | pulsed
    occupancy: float     # fraction of the band above the floor
    confidence: int
    detail: str


def characterize_interference(spectrum: list, floor_db: float, *, snr_db: float = 10.0,
                              pulsed_hint: bool = False) -> JammingProfile:
    """Classify the *type* of interference from a sweep's spectrum.

    - barrage: most of the band is raised (broadband noise jamming)
    - spot: one dominant narrowband carrier
    - multi-tone: several strong tones over part of the band
    - none: nominal
    """
    if not spectrum:
        return JammingProfile("none", 0.0, 0, "no data")
    thresh = floor_db + snr_db
    above = [p for p in spectrum if p > thresh]
    occ = len(above) / len(spectrum)
    peak = max(spectrum)
    # Count distinct strong tones (local maxima above threshold).
    tones = 0
    for i in range(1, len(spectrum) - 1):
        if (spectrum[i] > thresh and spectrum[i] >= spectrum[i - 1]
                and spectrum[i] >= spectrum[i + 1]):
            tones += 1

    if pulsed_hint:
        return JammingProfile("pulsed", round(occ, 3), 70,
                              "pulsed interference (from IQ pulse analysis)")
    if occ >= 0.6:
        return JammingProfile("barrage", round(occ, 3), min(95, int(60 + occ * 40)),
                              f"{occ:.0%} of the band raised above the floor — "
                              f"broadband/noise jamming.")
    if tones <= 1 and (peak - floor_db) > snr_db + 15 and occ < 0.15:
        return JammingProfile("spot", round(occ, 3), 80,
                              f"a single dominant carrier ({peak - floor_db:.0f} dB "
                              f"over floor) in an otherwise quiet band.")
    if 2 <= tones <= 12 and occ < 0.5:
        return JammingProfile("multi-tone", round(occ, 3), 60,
                              f"{tones} strong tones over part of the band.")
    return JammingProfile("none", round(occ, 3), 50, "band appears nominal.")


# --------------------------------------------------------------------------- #
# 3. Emitter catalogue (Electronic Order of Battle)
# --------------------------------------------------------------------------- #
def emitters_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else (Path.home() / ".config")
    return root / "rfhound" / "emitters.json"


@dataclass
class Emitter:
    freq_mhz: float
    itu: str
    first_seen: float
    last_seen: float
    count: int = 1
    max_power_db: float | None = None
    bandwidth_khz: float | None = None
    guess: str | None = None

    @property
    def key(self) -> str:
        return f"{self.freq_mhz:.3f}"


class EmitterCatalog:
    """Persistent Electronic Order of Battle keyed by frequency (kHz bucket)."""

    def __init__(self, path: Path | None = None, bucket_khz: int = 25):
        self.path = path or emitters_path()
        self.bucket_khz = bucket_khz
        self.data: dict[str, Emitter] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                self.data = {k: Emitter(**v) for k, v in raw.items()}
            except (json.JSONDecodeError, OSError, TypeError):
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: asdict(v) for k, v in self.data.items()}, indent=2))

    def _bucket(self, freq_mhz: float) -> str:
        step = self.bucket_khz / 1000.0
        return f"{round(freq_mhz / step) * step:.3f}"

    def ingest(self, freq_mhz: float, *, power_db: float | None = None,
               bandwidth_khz: float | None = None, guess: str | None = None,
               when: float | None = None, save: bool = True) -> Emitter:
        now = when if when is not None else time.time()
        key = self._bucket(freq_mhz)
        itu = bandplan.itu_band(int(freq_mhz * 1e6))
        itu_s = itu[0] if itu else "—"
        e = self.data.get(key)
        if e:
            e.last_seen = now
            e.count += 1
            if power_db is not None:
                e.max_power_db = max(e.max_power_db or -999, power_db)
            if bandwidth_khz is not None:
                e.bandwidth_khz = bandwidth_khz
            if guess:
                e.guess = guess
        else:
            e = Emitter(freq_mhz=round(freq_mhz, 4), itu=itu_s, first_seen=now,
                        last_seen=now, count=1, max_power_db=power_db,
                        bandwidth_khz=bandwidth_khz, guess=guess)
            self.data[key] = e
        if save:
            self.save()
        return e

    def list(self) -> list[Emitter]:
        return sorted(self.data.values(), key=lambda e: e.freq_mhz)

    def clear(self) -> int:
        n = len(self.data)
        self.data = {}
        self.save()
        return n


# --------------------------------------------------------------------------- #
# 4. Multi-node RSSI geolocation / direction finding
# --------------------------------------------------------------------------- #
@dataclass
class GeoEstimate:
    lat: float | None
    lon: float | None
    confidence: int
    n_receivers: int
    strongest: str = ""
    detail: str = ""


def geolocate(reports: list[dict]) -> GeoEstimate:
    """Estimate an emitter position from receiver RSSI reports.

    Each report: {"node": name, "lat": .., "lon": .., "rssi": dBm}. Uses an
    RSSI-power-weighted centroid — a coarse but useful fix that sharpens with
    more, well-separated receivers. (Not TDOA; single-node RSSI cannot localise.)
    """
    located = [r for r in reports if r.get("lat") is not None and r.get("lon") is not None
               and r.get("rssi") is not None]
    if not located:
        return GeoEstimate(None, None, 0, 0, "", "no positioned receivers with RSSI")
    # Weight by linear power (stronger receiver → closer → more weight).

    def weight(rssi):
        return 10 ** (rssi / 10.0)

    wsum = sum(weight(r["rssi"]) for r in located)
    lat = sum(r["lat"] * weight(r["rssi"]) for r in located) / wsum
    lon = sum(r["lon"] * weight(r["rssi"]) for r in located) / wsum
    strongest = max(located, key=lambda r: r["rssi"])
    conf = min(90, 25 + 15 * (len(located) - 1))  # more receivers → more confidence
    return GeoEstimate(round(lat, 6), round(lon, 6), conf, len(located),
                       strongest.get("node", ""),
                       f"power-weighted centroid of {len(located)} receivers")


def bearing_deg(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float:
    """Initial great-circle bearing from one point to another (degrees)."""
    p1, p2 = math.radians(from_lat), math.radians(to_lat)
    dl = math.radians(to_lon - from_lon)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return round((math.degrees(math.atan2(x, y)) + 360) % 360, 1)


def simulate_reports() -> list[dict]:
    """Three receivers around an emitter near (51.51, -0.12)."""
    return [
        {"node": "north", "lat": 51.52, "lon": -0.12, "rssi": -60},
        {"node": "east", "lat": 51.51, "lon": -0.10, "rssi": -55},
        {"node": "south", "lat": 51.50, "lon": -0.12, "rssi": -70},
    ]
