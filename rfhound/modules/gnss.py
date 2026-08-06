"""GNSS interference & spoofing DETECTION (defensive / Electronic Protection).

The defensive counterpart to GNSS attacks. It ingests GNSS *observations* — per
satellite C/N0, receiver AGC, position/time, satellite elevations — and flags the
indicators of **jamming** (denial) and **spoofing** (false position/time), using
the techniques from public GNSS-interference guidance:

  * C/N0 collapse / fix loss / AGC spike            → jamming
  * abnormally high **and uniform** C/N0 across sats → spoofing
  * C/N0 that doesn't rise with satellite elevation → spoofing
  * position/time jumps (impossible speed / clock step) → spoofing / meaconing
  * a static receiver that "moves", or disagreement with a known location → spoofing

It also has a light L1 IQ check: genuine GPS sits *below* the noise floor, so
elevated power at 1575.42 MHz is itself an anomaly.

Receive-and-analyse only. RFHound never transmits on GNSS frequencies — see
``docs/LEGAL.md``. Pair with ``defense respond gps_spoof`` and, for locating a
spoofer, the multi-node TDOA module.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .intel import _haversine_km


@dataclass
class GnssObservation:
    t: float = 0.0
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    cn0: list = field(default_factory=list)          # per-sat C/N0 (dB-Hz)
    elevations: list = field(default_factory=list)   # per-sat elevation (deg), aligned with cn0
    agc: float | None = None                         # receiver AGC gain (higher => weaker RX)
    num_sats: int | None = None
    fix: bool = True


@dataclass
class GnssFinding:
    indicator: str
    detail: str
    severity: str = "high"   # high | medium | low
    kind: str = "spoofing"   # jamming | spoofing


@dataclass
class GnssReport:
    status: str              # nominal | jamming | spoofing | mixed
    confidence: int
    findings: list = field(default_factory=list)
    samples: int = 0


def _pearson(xs, ys) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    xs, ys = xs[:n], ys[:n]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def detect_gnss_interference(
    observations: list,
    *,
    known_location: tuple | None = None,
    static: bool = False,
    uniform_cn0_db: float = 2.5,
    min_cn0: float = 25.0,
    high_cn0: float = 46.0,
    max_speed_kt: float = 700.0,
    static_move_m: float = 150.0,
) -> GnssReport:
    """Analyse GNSS observations for jamming and spoofing indicators."""
    obs = sorted(observations, key=lambda o: o.t)
    findings: list = []

    # --- Jamming: fix loss, low C/N0, AGC spike ---
    agcs = [o.agc for o in obs if o.agc is not None]
    agc_baseline = statistics.median(agcs) if agcs else None
    for o in obs:
        mean_cn0 = statistics.mean(o.cn0) if o.cn0 else None
        if o.fix is False:
            findings.append(GnssFinding(
                "fix-loss", f"t={o.t:.0f}: GNSS fix lost — possible jamming.",
                "high", "jamming"))
        elif mean_cn0 is not None and mean_cn0 < min_cn0:
            findings.append(GnssFinding(
                "low-cn0", f"t={o.t:.0f}: mean C/N0 {mean_cn0:.0f} dB-Hz below "
                f"{min_cn0:.0f} — possible jamming/desense.", "high", "jamming"))
        if o.agc is not None and agc_baseline is not None and o.agc > agc_baseline * 1.5:
            findings.append(GnssFinding(
                "agc-spike", f"t={o.t:.0f}: receiver AGC spiked "
                f"({o.agc:.0f} vs ~{agc_baseline:.0f}) — jamming/desense.", "medium", "jamming"))

    # --- Spoofing: uniform+high C/N0, elevation decorrelation ---
    # Only meaningful when signal is actually present — during jamming the C/N0
    # is low and structureless, which is a denial indicator, not spoofing.
    for o in obs:
        if len(o.cn0) >= 4 and statistics.mean(o.cn0) >= min_cn0:
            sd = statistics.pstdev(o.cn0)
            mean_cn0 = statistics.mean(o.cn0)
            if sd < uniform_cn0_db and mean_cn0 > high_cn0:
                findings.append(GnssFinding(
                    "uniform-cn0", f"t={o.t:.0f}: {len(o.cn0)} sats at near-identical "
                    f"C/N0 (~{mean_cn0:.0f} dB-Hz, σ {sd:.1f}) — spoofers drive all "
                    f"channels to one power.", "high", "spoofing"))
            if o.elevations and len(o.elevations) == len(o.cn0):
                corr = _pearson(o.elevations, o.cn0)
                if corr < 0.1:
                    findings.append(GnssFinding(
                        "elevation-decorrelation", f"t={o.t:.0f}: C/N0 does not rise "
                        f"with satellite elevation (r={corr:.2f}) — inconsistent with a "
                        f"real constellation.", "medium", "spoofing"))

    # --- Spoofing: position jumps / impossible speed ---
    for i in range(1, len(obs)):
        a, b = obs[i - 1], obs[i]
        if None in (a.lat, a.lon, b.lat, b.lon):
            continue
        dt = max(1e-3, b.t - a.t)
        dist_km = _haversine_km(a.lat, a.lon, b.lat, b.lon)
        speed_kt = (dist_km / 1.852) / (dt / 3600.0)
        if speed_kt > max_speed_kt:
            findings.append(GnssFinding(
                "position-jump", f"t={b.t:.0f}: position jumped {dist_km:.1f} km in "
                f"{dt:.0f}s (~{speed_kt:.0f} kt) — spoofing/meaconing.", "high", "spoofing"))

    # --- Spoofing: static receiver moved / known-location disagreement ---
    ref = known_location
    if ref is None and static and obs and obs[0].lat is not None:
        ref = (obs[0].lat, obs[0].lon)
    if ref is not None:
        for o in obs:
            if o.lat is None:
                continue
            d_m = _haversine_km(ref[0], ref[1], o.lat, o.lon) * 1000.0
            if d_m > static_move_m:
                label = "static-moved" if static else "location-mismatch"
                findings.append(GnssFinding(
                    label, f"t={o.t:.0f}: reported position {d_m:.0f} m from the "
                    f"{'fixed receiver site' if static else 'known location'} — spoofing.",
                    "high", "spoofing"))
                break

    kinds = {f.kind for f in findings}
    if not findings:
        status = "nominal"
    elif {"jamming", "spoofing"} <= kinds:
        status = "mixed"
    else:
        status = next(iter(kinds))
    confidence = min(95, 30 + 18 * len(findings)) if findings else 0
    return GnssReport(status=status, confidence=confidence, findings=findings, samples=len(obs))


# --------------------------------------------------------------------------- #
# Light L1 IQ check (genuine GPS is below the noise floor)
# --------------------------------------------------------------------------- #
def analyze_l1_power(iq, sample_rate: int) -> dict:
    """Flag anomalous power at GPS L1: real GNSS is ~ -130 dBm, below thermal
    noise, so a strong carrier or elevated in-band power is itself suspicious.
    """
    import numpy as np
    a = np.asarray(iq)
    if a.size < 64:
        return {"anomaly": False, "note": "too few samples"}
    power = float(np.mean(np.abs(a) ** 2))
    # Spectral flatness (geometric mean / arithmetic mean of the PSD): ~1 = noise,
    # << 1 = a structured/carrier signal (a spoofer or CW jammer).
    spec = np.abs(np.fft.fft(a[: min(a.size, 8192)])) ** 2 + 1e-12
    flatness = float(np.exp(np.mean(np.log(spec))) / np.mean(spec))
    carrier = flatness < 0.2
    return {"anomaly": bool(carrier), "power": round(power, 4),
            "flatness": round(flatness, 3),
            "note": ("structured/carrier energy at L1 — possible spoofer or CW jammer"
                     if carrier else "noise-like; no obvious L1 carrier")}


# --------------------------------------------------------------------------- #
# Simulators
# --------------------------------------------------------------------------- #
def simulate_nominal() -> list:
    """A healthy constellation: C/N0 rises with elevation, stable position."""
    elevs = [10, 25, 40, 55, 70, 85]
    cn0 = [30, 35, 40, 44, 47, 49]  # correlated with elevation
    return [GnssObservation(t=float(i), lat=51.5000, lon=-0.1200, alt=30,
                            cn0=list(cn0), elevations=list(elevs), agc=40, num_sats=6, fix=True)
            for i in range(5)]


def simulate_jamming() -> list:
    obs = simulate_nominal()[:2]
    # Then C/N0 collapses and the fix is lost, AGC spikes.
    obs.append(GnssObservation(t=2.0, cn0=[18, 17, 19, 16], elevations=[10, 25, 40, 55],
                               agc=95, num_sats=4, fix=True))
    obs.append(GnssObservation(t=3.0, cn0=[], agc=110, num_sats=0, fix=False))
    return obs


def simulate_spoofing() -> list:
    elevs = [10, 25, 40, 55, 70, 85]
    uniform = [48, 48, 49, 48, 49, 48]  # high + uniform, decorrelated from elevation
    obs = [GnssObservation(t=0.0, lat=51.5000, lon=-0.1200, alt=30,
                           cn0=list(uniform), elevations=list(elevs), agc=42, fix=True)]
    # A position jump on the next fix.
    obs.append(GnssObservation(t=1.0, lat=51.9000, lon=-0.6000, alt=30,
                               cn0=list(uniform), elevations=list(elevs), agc=42, fix=True))
    return obs
