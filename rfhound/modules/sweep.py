"""Wideband spectrum sweeping.

Drives ``hackrf_sweep`` (which retunes the radio fast enough to cover up to
~8 GHz/s), parses its CSV output into a frequency->power map, finds active
peaks above the noise floor, and correlates them against the band plan so you
immediately know *what* you found.

A ``--simulate`` mode synthesises plausible sweep data so the whole pipeline
(parsing, peak detection, rendering, reporting) works with no hardware — useful
for demos, tests and CI.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .. import bandplan, console, proc
from ..config import Config


@dataclass
class Bin:
    freq_hz: int
    power_db: float


@dataclass
class Peak:
    freq_hz: int
    power_db: float
    band: bandplan.Band | None = None

    @property
    def freq_mhz(self) -> float:
        return self.freq_hz / 1e6


@dataclass
class SweepResult:
    start_hz: int
    stop_hz: int
    bins: list[Bin] = field(default_factory=list)
    peaks: list[Peak] = field(default_factory=list)
    noise_floor_db: float = 0.0
    simulated: bool = False

    @property
    def span_mhz(self) -> float:
        return (self.stop_hz - self.start_hz) / 1e6


def _parse_hackrf_sweep_line(line: str) -> list[Bin]:
    """Parse one CSV line of hackrf_sweep output.

    Format: date, time, hz_low, hz_high, hz_bin_width, num_samples, dB, dB, ...
    Each dB value corresponds to a bin of width hz_bin_width starting at hz_low.
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 7:
        return []
    try:
        hz_low = int(parts[2])
        hz_bin_width = float(parts[4])
        powers = [float(p) for p in parts[6:]]
    except ValueError:
        return []
    bins = []
    for i, p in enumerate(powers):
        freq = int(hz_low + (i + 0.5) * hz_bin_width)
        bins.append(Bin(freq, p))
    return bins


def _detect_peaks(bins: list[Bin], *, snr_db: float) -> tuple[list[Peak], float]:
    """Find bins that stand out above the noise floor.

    Noise floor is estimated as the median power; a peak must exceed
    floor + snr_db and be a local maximum. Adjacent peaks are merged.
    """
    if not bins:
        return [], 0.0
    powers = sorted(b.power_db for b in bins)
    floor = powers[len(powers) // 2]  # median
    threshold = floor + snr_db

    ordered = sorted(bins, key=lambda b: b.freq_hz)
    candidates: list[Peak] = []
    for i, b in enumerate(ordered):
        if b.power_db < threshold:
            continue
        prev_p = ordered[i - 1].power_db if i > 0 else -999.0
        next_p = ordered[i + 1].power_db if i < len(ordered) - 1 else -999.0
        if b.power_db >= prev_p and b.power_db >= next_p:
            candidates.append(Peak(b.freq_hz, round(b.power_db, 1)))

    # Merge peaks within 200 kHz, keeping the strongest.
    candidates.sort(key=lambda p: p.freq_hz)
    merged: list[Peak] = []
    for c in candidates:
        if merged and abs(c.freq_hz - merged[-1].freq_hz) < 200_000:
            if c.power_db > merged[-1].power_db:
                merged[-1] = c
        else:
            merged.append(c)

    for p in merged:
        p.band = bandplan.find_band(p.freq_hz)
    merged.sort(key=lambda p: p.power_db, reverse=True)
    return merged, round(floor, 1)


def _simulate_sweep(start_hz: int, stop_hz: int, bin_hz: int) -> list[Bin]:
    """Generate synthetic spectrum with a noise floor and a few injected peaks."""
    rng = random.Random(1337)
    bins: list[Bin] = []
    # Inject signals at any band centers that fall in-range.
    injected = {
        b.tune_hz: rng.uniform(20, 45)
        for b in bandplan.BANDS
        if start_hz <= b.tune_hz <= stop_hz
    }
    freq = start_hz
    while freq < stop_hz:
        floor = -95 + rng.uniform(-3, 3)
        power = floor
        for center, strength in injected.items():
            # Gaussian bump around each injected signal.
            sigma = 150_000
            power = max(power, floor + strength * math.exp(-((freq - center) ** 2) / (2 * sigma**2)))
        bins.append(Bin(freq, round(power, 1)))
        freq += bin_hz
    return bins


def sweep(
    cfg: Config,
    start_mhz: float,
    stop_mhz: float,
    *,
    bin_khz: int = 100,
    snr_db: float = 12.0,
    sweeps: int = 1,
    simulate: bool = False,
) -> SweepResult:
    """Run a spectrum sweep between *start_mhz* and *stop_mhz*."""
    start_hz = int(start_mhz * 1e6)
    stop_hz = int(stop_mhz * 1e6)
    bin_hz = bin_khz * 1000

    if simulate:
        bins = _simulate_sweep(start_hz, stop_hz, bin_hz)
    else:
        proc.require_tool("hackrf_sweep")
        args = [
            "hackrf_sweep",
            "-f", f"{int(start_mhz)}:{int(stop_mhz)}",
            "-w", str(bin_hz),
            "-l", str(cfg.lna_gain),
            "-g", str(cfg.vga_gain),
            "-1",  # one sweep pass
        ]
        args += proc.hackrf_common_args(cfg, for_sweep=True)
        agg: dict[int, float] = {}
        for _ in range(max(1, sweeps)):
            captured: list[str] = []
            proc.stream(args, on_line=captured.append, timeout=30)
            for line in captured:
                for b in _parse_hackrf_sweep_line(line):
                    # Peak-hold across sweeps.
                    agg[b.freq_hz] = max(agg.get(b.freq_hz, -999.0), b.power_db)
        bins = [Bin(f, p) for f, p in sorted(agg.items())]

    peaks, floor = _detect_peaks(bins, snr_db=snr_db)
    return SweepResult(
        start_hz=start_hz,
        stop_hz=stop_hz,
        bins=bins,
        peaks=peaks,
        noise_floor_db=floor,
        simulated=simulate,
    )


def render_spectrum(result: SweepResult, width: int = 60, rows: int = 12) -> None:
    """Draw a compact terminal spectrogram of the sweep."""
    if not result.bins:
        console.warn("No spectrum data.")
        return
    # Downsample bins into `width` columns using peak-hold.
    lo, hi = result.start_hz, result.stop_hz
    span = max(1, hi - lo)
    cols = [-999.0] * width
    for b in result.bins:
        idx = min(width - 1, int((b.freq_hz - lo) / span * width))
        cols[idx] = max(cols[idx], b.power_db)
    finite = [c for c in cols if c > -999.0]
    if not finite:
        console.warn("No spectrum data.")
        return
    pmin, pmax = min(finite), max(finite)
    prange = max(1.0, pmax - pmin)
    blocks = " .:-=+*#%@"
    mid = (lo + hi) // 2
    console.print_(
        f"Spectrum {lo/1e6:.1f}-{hi/1e6:.1f} MHz  "
        f"floor {result.noise_floor_db} dB  peak {pmax:.0f} dB"
        + ("  [SIMULATED]" if result.simulated else "")
    )
    line = "".join(
        blocks[min(len(blocks) - 1, int((c - pmin) / prange * (len(blocks) - 1)))]
        if c > -999.0 else " "
        for c in cols
    )
    console.print_(f"[{line}]")
    console.print_(f" ITU range: {bandplan.itu_label(mid)}")
