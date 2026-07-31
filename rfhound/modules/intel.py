"""RF intelligence & threat detection (all receive-and-analyse).

The "situational awareness" layer that makes RFHound a credible defensive
monitoring product:

  * TSCM baseline diff  — save a known-good spectrum, later diff it to surface
    new / rogue emitters (counter-surveillance bug sweeps).
  * Spoof detection     — flag ghost aircraft / impossible-kinematics / duplicate
    IDs in decoded ADS-B and AIS message streams.
  * Counter-UAS scan    — sweep common drone control/video bands and report
    detected activity (detection only — no jamming/takeover).

None of this transmits. It analyses received data and spectrum.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from .. import bandplan
from ..config import Config
from . import sweep as sweep_mod


# --------------------------------------------------------------------------- #
# TSCM: baseline spectrum + rogue-emitter diff
# --------------------------------------------------------------------------- #
@dataclass
class RogueEmitter:
    freq_hz: int
    power_db: float
    baseline_db: float | None
    delta_db: float
    band: str | None
    kind: str  # "new" or "elevated"

    @property
    def freq_mhz(self) -> float:
        return self.freq_hz / 1e6


def save_baseline(
    cfg: Config,
    start_mhz: float,
    stop_mhz: float,
    out_path: Path,
    *,
    bin_khz: int = 100,
    simulate: bool = False,
) -> Path:
    """Sweep a range and store it as a known-good baseline for later diffing."""
    result = sweep_mod.sweep(cfg, start_mhz, stop_mhz, bin_khz=bin_khz, simulate=simulate)
    doc = {
        "type": "rfhound-baseline",
        "created": time.time(),
        "start_hz": result.start_hz,
        "stop_hz": result.stop_hz,
        "bin_khz": bin_khz,
        "noise_floor_db": result.noise_floor_db,
        "bins": [[b.freq_hz, b.power_db] for b in result.bins],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc))
    return out_path


def load_baseline(path: Path) -> dict:
    doc = json.loads(Path(path).read_text())
    if doc.get("type") != "rfhound-baseline":
        raise ValueError(f"{path} is not an RFHound baseline file.")
    return doc


def diff_baseline(
    cfg: Config,
    baseline_path: Path,
    *,
    new_threshold_db: float = 10.0,
    simulate: bool = False,
) -> list[RogueEmitter]:
    """Sweep again and report emitters that are new or notably stronger than the
    baseline — the core of a counter-surveillance (TSCM) sweep.
    """
    base = load_baseline(baseline_path)
    start_mhz = base["start_hz"] / 1e6
    stop_mhz = base["stop_hz"] / 1e6
    bin_khz = base.get("bin_khz", 100)

    # Build a fast lookup of baseline power by binned frequency.
    bin_hz = bin_khz * 1000
    base_power: dict[int, float] = {}
    for freq_hz, power in base["bins"]:
        base_power[int(freq_hz) // bin_hz] = power

    if simulate:
        # Reuse the baseline but inject a rogue emitter (a "planted bug").
        result = sweep_mod.sweep(cfg, start_mhz, stop_mhz, bin_khz=bin_khz, simulate=True)
        rogue_freq = (base["start_hz"] + base["stop_hz"]) // 2
        result.peaks.insert(0, sweep_mod.Peak(rogue_freq, -35.0, bandplan.find_band(rogue_freq)))
    else:
        result = sweep_mod.sweep(cfg, start_mhz, stop_mhz, bin_khz=bin_khz, simulate=False)

    findings: list[RogueEmitter] = []
    for peak in result.peaks:
        key = peak.freq_hz // bin_hz
        base_db = base_power.get(key)
        band = peak.band.name if peak.band else None
        if base_db is None:
            findings.append(RogueEmitter(peak.freq_hz, peak.power_db, None,
                                         peak.power_db, band, "new"))
        else:
            delta = peak.power_db - base_db
            if delta >= new_threshold_db:
                findings.append(RogueEmitter(peak.freq_hz, peak.power_db, base_db,
                                             round(delta, 1), band, "elevated"))
    findings.sort(key=lambda f: f.power_db, reverse=True)
    return findings


# --------------------------------------------------------------------------- #
# Spoof detection (ADS-B / AIS)
# --------------------------------------------------------------------------- #
@dataclass
class SpoofFinding:
    entity_id: str        # ICAO hex or MMSI
    kind: str             # "ghost", "teleport", "duplicate-id", "impossible-altitude", ...
    detail: str
    severity: str = "high"


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def detect_adsb_spoofing(
    messages: list[dict],
    *,
    max_speed_kt: float = 1500.0,
    max_alt_ft: float = 60000.0,
) -> list[SpoofFinding]:
    """Analyse decoded ADS-B messages for spoofing indicators.

    Each message dict may contain: icao, t (epoch s), lat, lon, alt (ft),
    speed (kt), rssi. Detects ghost-aircraft / replay signatures:
      * the same ICAO reporting from two far-apart positions at the same time;
      * position jumps that imply an impossible ground speed (teleport);
      * impossible / out-of-range altitude.
    """
    findings: list[SpoofFinding] = []
    by_icao: dict[str, list[dict]] = {}
    for m in messages:
        icao = str(m.get("icao", "")).lower()
        if icao:
            by_icao.setdefault(icao, []).append(m)

    for icao, msgs in by_icao.items():
        msgs = sorted(msgs, key=lambda m: m.get("t", 0))
        # Altitude plausibility is per-message (doesn't need a track).
        for m in msgs:
            alt = m.get("alt")
            if alt is not None and (alt > max_alt_ft or alt < -1500):
                findings.append(SpoofFinding(
                    icao, "impossible-altitude", f"altitude {alt} ft out of plausible range."))
        # Kinematic checks need consecutive positions.
        for i in range(1, len(msgs)):
            a, b = msgs[i - 1], msgs[i]
            if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
                continue
            dt = max(1e-3, (b.get("t", 0) - a.get("t", 0)))
            dist_km = _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            speed_kt = (dist_km / 1.852) / (dt / 3600.0)
            if dt <= 2.0 and dist_km > 5.0:
                findings.append(SpoofFinding(
                    icao, "teleport",
                    f"jumped {dist_km:.0f} km in {dt:.1f}s (~{speed_kt:.0f} kt) — "
                    f"physically impossible; likely ghost/replay injection."))
            elif speed_kt > max_speed_kt:
                findings.append(SpoofFinding(
                    icao, "impossible-speed",
                    f"implied ground speed {speed_kt:.0f} kt exceeds {max_speed_kt:.0f} kt."))

    # Duplicate-ID: same ICAO, same timestamp, distant positions.
    for icao, msgs in by_icao.items():
        by_t: dict[float, list[dict]] = {}
        for m in msgs:
            if m.get("lat") is not None:
                by_t.setdefault(round(m.get("t", 0), 0), []).append(m)
        for t, group in by_t.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    d = _haversine_km(group[i]["lat"], group[i]["lon"],
                                      group[j]["lat"], group[j]["lon"])
                    if d > 10.0:
                        findings.append(SpoofFinding(
                            icao, "duplicate-id",
                            f"same ICAO reported {d:.0f} km apart at t={t:.0f} — "
                            f"two emitters using one identity."))
    return findings


def detect_ais_spoofing(
    messages: list[dict],
    *,
    max_speed_kt: float = 60.0,
) -> list[SpoofFinding]:
    """Analyse decoded AIS messages for spoofing indicators.

    Each dict may contain: mmsi, t, lat, lon, sog (speed over ground, kt).
    Flags invalid MMSI, impossible vessel speed, and teleporting tracks.
    """
    findings: list[SpoofFinding] = []
    by_mmsi: dict[str, list[dict]] = {}
    for m in messages:
        mmsi = str(m.get("mmsi", ""))
        if mmsi:
            by_mmsi.setdefault(mmsi, []).append(m)

    for mmsi, msgs in by_mmsi.items():
        if not (mmsi.isdigit() and len(mmsi) == 9):
            findings.append(SpoofFinding(mmsi, "invalid-mmsi",
                                         "MMSI is not a valid 9-digit identifier.",
                                         severity="medium"))
        msgs = sorted(msgs, key=lambda m: m.get("t", 0))
        for i in range(1, len(msgs)):
            a, b = msgs[i - 1], msgs[i]
            if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
                continue
            dt = max(1e-3, (b.get("t", 0) - a.get("t", 0)))
            dist_km = _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            speed_kt = (dist_km / 1.852) / (dt / 3600.0)
            if speed_kt > max_speed_kt * 3:
                findings.append(SpoofFinding(
                    mmsi, "teleport",
                    f"moved {dist_km:.1f} km in {dt:.0f}s (~{speed_kt:.0f} kt) — "
                    f"impossible for a vessel; likely spoofed."))
    return findings


def simulate_adsb_messages() -> list[dict]:
    """A tiny synthetic stream containing one ghost/teleport aircraft."""
    return [
        {"icao": "abc123", "t": 0, "lat": 51.5, "lon": -0.1, "alt": 35000, "speed": 450},
        {"icao": "abc123", "t": 1, "lat": 55.9, "lon": -3.2, "alt": 35000, "speed": 450},  # teleport
        {"icao": "def456", "t": 0, "lat": 40.6, "lon": -73.8, "alt": 90000},  # bad altitude
    ]


def simulate_ais_messages() -> list[dict]:
    return [
        {"mmsi": "123456789", "t": 0, "lat": 50.0, "lon": 1.0, "sog": 12},
        {"mmsi": "123456789", "t": 30, "lat": 51.0, "lon": 2.0, "sog": 12},  # teleport
        {"mmsi": "42", "t": 0, "lat": 50.0, "lon": 1.0},  # invalid mmsi
    ]


# --------------------------------------------------------------------------- #
# Counter-UAS: drone-band activity scan (detection only)
# --------------------------------------------------------------------------- #
@dataclass
class DroneHit:
    band: str
    freq_mhz: float
    power_db: float
    confidence: str


@dataclass
class HoppingReport:
    slices: int
    distinct_freqs: int
    transient_freqs: int
    persistence: float
    hopping_suspected: bool
    detail: str


def detect_frequency_hopping(
    peaks_per_slice: list[list[float]],
    *,
    tol_mhz: float = 0.2,
    transient_frac: float = 0.35,
) -> HoppingReport:
    """Detect a frequency-hopping emitter from peaks seen across time slices.

    Input is a list (one per time slice / sweep) of peak frequencies in MHz. A
    hopper shows up as many *distinct* frequencies each present only briefly
    (transient), rather than a few persistent carriers. Useful for spotting
    covert / frequency-agile transmitters.
    """
    n = len(peaks_per_slice)
    if n == 0:
        return HoppingReport(0, 0, 0, 0.0, False, "no data")
    # Bucket frequencies within tol.
    counts: dict[int, int] = {}
    for slice_peaks in peaks_per_slice:
        seen = set()
        for f in slice_peaks:
            key = round(f / tol_mhz)
            seen.add(key)
        for key in seen:
            counts[key] = counts.get(key, 0) + 1
    distinct = len(counts)
    transient = sum(1 for c in counts.values() if c <= max(1, int(n * transient_frac)))
    persistent = distinct - transient
    persistence = round((persistent / distinct) if distinct else 0.0, 2)
    # Hopping suspected: many distinct, mostly-transient frequencies, few persistent.
    suspected = (
        distinct >= max(4, int(n * 0.6))
        and transient >= max(4, int(distinct * 0.6))
        and persistence < 0.4
    )
    detail = (
        f"{distinct} distinct freqs over {n} slices; {transient} transient, "
        f"{persistent} persistent (persistence {persistence})."
    )
    return HoppingReport(n, distinct, transient, persistence, suspected, detail)


def simulate_hopping_slices(n: int = 8, *, hopping: bool = True) -> list[list[float]]:
    """Synthesise per-slice peak lists for a hopper (or a steady carrier)."""
    slices = []
    for i in range(n):
        if hopping:
            slices.append([round(433.0 + i * 0.5, 3)])  # a fresh, well-spaced hop each slice
        else:
            slices.append([433.92])  # steady carrier
    return slices


def drone_scan(cfg: Config, *, simulate: bool = False) -> list[DroneHit]:
    """Sweep common drone control/video bands and report detected activity.

    Detection only. Uses the band-plan entries tagged 'drone'. Confidence is a
    coarse function of peak strength over the local noise floor.
    """
    hits: list[DroneHit] = []
    for band in bandplan.bands_by_tag("drone"):
        low_mhz = band.low_hz / 1e6
        high_mhz = band.high_hz / 1e6
        if high_mhz - low_mhz < 1.0:
            mid = (low_mhz + high_mhz) / 2
            low_mhz, high_mhz = mid - 1.0, mid + 1.0
        result = sweep_mod.sweep(cfg, low_mhz, high_mhz, simulate=simulate)
        for p in result.peaks:
            if not (band.low_hz <= p.freq_hz <= band.high_hz):
                continue
            snr = p.power_db - result.noise_floor_db
            conf = "high" if snr > 25 else "medium" if snr > 15 else "low"
            hits.append(DroneHit(band.name, round(p.freq_mhz, 3), p.power_db, conf))
    hits.sort(key=lambda h: h.power_db, reverse=True)
    return hits
