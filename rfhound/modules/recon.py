"""Automated reconnaissance survey.

Sweeps the band-plan's high-value targets one by one, records active peaks, and
suggests which decoder to point at each hit. This is the "just tell me what's
around me" workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import bandplan, console
from ..config import Config
from . import sweep as sweep_mod


@dataclass
class BandFinding:
    band: bandplan.Band
    peaks: list[sweep_mod.Peak]
    noise_floor_db: float

    @property
    def active(self) -> bool:
        return bool(self.peaks)


@dataclass
class ReconReport:
    findings: list[BandFinding] = field(default_factory=list)
    simulated: bool = False

    @property
    def active_findings(self) -> list[BandFinding]:
        return [f for f in self.findings if f.active]


def run_recon(
    cfg: Config,
    *,
    targets: list[bandplan.Band] | None = None,
    snr_db: float = 12.0,
    bin_khz: int = 100,
    simulate: bool = False,
    progress: bool = True,
) -> ReconReport:
    """Sweep each survey target band and collect findings."""
    targets = targets or bandplan.survey_targets()
    report = ReconReport(simulated=simulate)

    for band in targets:
        if progress:
            console.info(
                f"Surveying {band.name} "
                f"({band.low_hz/1e6:.1f}-{band.high_hz/1e6:.1f} MHz)…"
            )
        # hackrf_sweep needs at least a ~1 MHz span; pad narrow bands.
        low_mhz = band.low_hz / 1e6
        high_mhz = band.high_hz / 1e6
        if high_mhz - low_mhz < 1.0:
            mid = (low_mhz + high_mhz) / 2
            low_mhz, high_mhz = mid - 1.0, mid + 1.0
        result = sweep_mod.sweep(
            cfg, low_mhz, high_mhz, bin_khz=bin_khz, snr_db=snr_db, simulate=simulate
        )
        # Keep only peaks actually inside the declared band.
        peaks = [p for p in result.peaks if band.low_hz <= p.freq_hz <= band.high_hz]
        report.findings.append(
            BandFinding(band=band, peaks=peaks, noise_floor_db=result.noise_floor_db)
        )
    return report


def summarize(report: ReconReport) -> None:
    """Print a recon summary table."""
    rows = []
    for f in report.findings:
        top = max(f.peaks, key=lambda p: p.power_db) if f.peaks else None
        rows.append(
            [
                f.band.name,
                f.band.category,
                "active" if f.active else "quiet",
                f"{len(f.peaks)}",
                f"{top.freq_mhz:.3f} MHz @ {top.power_db} dB" if top else "-",
                f.band.decoder or "-",
            ]
        )
    console.table(
        "Recon survey" + (" [SIMULATED]" if report.simulated else ""),
        ["Band", "Category", "Status", "Peaks", "Strongest", "Decoder"],
        rows,
    )
