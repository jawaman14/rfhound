"""Wi-Fi 2.4 & 5 GHz channel survey (receive-only).

Turns a wideband sweep of the ISM / U-NII bands into a per-channel occupancy
picture: which Wi-Fi channels are busy, how congested each one is, and which
channel is clearest to move to. This is the "how crowded is my Wi-Fi
neighbourhood?" workflow.

**Scope / philosophy.** This is a *PHY-level spectrum view* over the SDR
(HackRF) — it tells you *where the RF energy is* across the Wi-Fi channels,
which is exactly what you need to pick a clean channel or spot interference.
It is **receive-and-analyse only**: RFHound has no Wi-Fi transmit, deauth, or
jamming capability, by design (see ``docs/LEGAL.md``). It does not decode
802.11 frames or read SSIDs/BSSIDs — for frame-level work use a monitor-mode
NIC; for interference/jamming detection on these bands use ``rfhound defense
monitor`` / ``rfhound sigint jamming``.

A ``--simulate`` mode drives the synthetic sweep generator so the whole
pipeline works with no hardware — useful for demos, tests and CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import console
from ..config import Config
from . import sweep as sweep_mod


# --------------------------------------------------------------------------- #
# Channel plans
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WifiChannel:
    number: int
    band: str  # "2.4" or "5"
    center_hz: int
    width_mhz: int = 20
    dfs: bool = False  # 5 GHz DFS channel (radar-shared, TX-restricted)
    note: str = ""

    @property
    def center_mhz(self) -> float:
        return self.center_hz / 1e6

    @property
    def low_hz(self) -> int:
        return self.center_hz - self.width_mhz * 500_000

    @property
    def high_hz(self) -> int:
        return self.center_hz + self.width_mhz * 500_000


def _ch24(n: int) -> WifiChannel:
    # Channels 1..13 are spaced 5 MHz starting at 2412 MHz; ch14 is 2484 MHz.
    center = 2_484_000_000 if n == 14 else 2_412_000_000 + (n - 1) * 5_000_000
    note = "non-overlapping (1/6/11)" if n in (1, 6, 11) else ""
    if n == 14:
        note = "Japan only (802.11b)"
    return WifiChannel(n, "2.4", center, width_mhz=20, note=note)


def _ch5(n: int, *, dfs: bool = False, note: str = "") -> WifiChannel:
    # 5 GHz channel center = 5000 MHz + n * 5 MHz.
    return WifiChannel(n, "5", 5_000_000_000 + n * 5_000_000, width_mhz=20,
                       dfs=dfs, note=note)


# 2.4 GHz: channels 1-13 globally, 14 in Japan. 1/6/11 are the classic
# non-overlapping set most APs should live on.
CHANNELS_24: list[WifiChannel] = [_ch24(n) for n in range(1, 14)] + [_ch24(14)]

# 5 GHz U-NII channels (20 MHz). UNII-2A/2C are DFS (radar-shared).
CHANNELS_5: list[WifiChannel] = (
    [_ch5(n, note="U-NII-1") for n in (36, 40, 44, 48)]
    + [_ch5(n, dfs=True, note="U-NII-2A (DFS)") for n in (52, 56, 60, 64)]
    + [_ch5(n, dfs=True, note="U-NII-2C (DFS)")
       for n in (100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144)]
    + [_ch5(n, note="U-NII-3") for n in (149, 153, 157, 161, 165)]
)

# The channels an AP can move to without DFS/radar constraints.
_CLEAN_24 = (1, 6, 11)
_NON_DFS_5 = (36, 40, 44, 48, 149, 153, 157, 161, 165)


def channels_for(band: str) -> list[WifiChannel]:
    """Return the channel plan for ``"2.4"``, ``"5"`` (or ``"both"``)."""
    if band == "2.4":
        return CHANNELS_24
    if band == "5":
        return CHANNELS_5
    if band == "both":
        return CHANNELS_24 + CHANNELS_5
    raise ValueError(f"Unknown band '{band}' (use 2.4, 5 or both).")


def channel_at(freq_hz: int) -> WifiChannel | None:
    """Return the Wi-Fi channel whose 20 MHz slot contains *freq_hz*, if any."""
    best: WifiChannel | None = None
    best_dist = None
    for ch in CHANNELS_24 + CHANNELS_5:
        if ch.low_hz <= freq_hz <= ch.high_hz:
            dist = abs(freq_hz - ch.center_hz)
            if best_dist is None or dist < best_dist:
                best, best_dist = ch, dist
    return best


# --------------------------------------------------------------------------- #
# Survey
# --------------------------------------------------------------------------- #
# Sweep ranges (MHz) wide enough to cover each band's channel centers ± guard.
_BAND_RANGE_MHZ: dict[str, tuple[float, float]] = {
    "2.4": (2400.0, 2495.0),
    "5": (5150.0, 5885.0),
}


@dataclass
class ChannelLoad:
    channel: WifiChannel
    peak_db: float
    mean_db: float
    floor_db: float
    occupancy_pct: float  # % of the channel's bins above the activity threshold

    @property
    def busy(self) -> bool:
        return self.snr_db >= 10.0 or self.occupancy_pct >= 15.0

    @property
    def snr_db(self) -> float:
        return round(self.peak_db - self.floor_db, 1)

    @property
    def status(self) -> str:
        if self.busy:
            return "busy"
        if self.snr_db >= 4.0:
            return "light"
        return "clear"


@dataclass
class WifiSurvey:
    band: str
    loads: list[ChannelLoad] = field(default_factory=list)
    floor_db: float = 0.0
    simulated: bool = False

    @property
    def busy_channels(self) -> list[ChannelLoad]:
        return [ld for ld in self.loads if ld.busy]

    def recommend(self) -> tuple[ChannelLoad | None, str]:
        """Pick the clearest channel to move to.

        On 2.4 GHz we only consider the non-overlapping 1/6/11 set; on 5 GHz we
        prefer non-DFS channels (no radar hold-off) and fall back to any channel
        if every non-DFS one is congested.
        """
        if not self.loads:
            return None, "no survey data"
        if self.band == "2.4":
            pool = [ld for ld in self.loads if ld.channel.number in _CLEAN_24]
            reason = "clearest of the non-overlapping 1/6/11 channels"
        else:
            pool = [ld for ld in self.loads if ld.channel.number in _NON_DFS_5]
            reason = "clearest non-DFS channel (no radar hold-off)"
            if pool and all(ld.busy for ld in pool):
                pool = self.loads
                reason = "clearest channel (all non-DFS channels congested)"
        if not pool:
            pool = self.loads
            reason = "clearest channel"
        best = min(pool, key=lambda ld: (ld.occupancy_pct, ld.snr_db))
        return best, reason


def _occupancy(bins: list[sweep_mod.Bin], ch: WifiChannel, floor_db: float,
               snr_db: float) -> ChannelLoad | None:
    inside = [b for b in bins if ch.low_hz <= b.freq_hz <= ch.high_hz]
    if not inside:
        return None
    powers = [b.power_db for b in inside]
    threshold = floor_db + snr_db
    active = sum(1 for p in powers if p >= threshold)
    return ChannelLoad(
        channel=ch,
        peak_db=round(max(powers), 1),
        mean_db=round(sum(powers) / len(powers), 1),
        floor_db=round(floor_db, 1),
        occupancy_pct=round(100.0 * active / len(inside), 1),
    )


def survey_band(
    cfg: Config,
    band: str,
    *,
    snr_db: float = 8.0,
    bin_khz: int = 250,
    sweeps: int = 1,
    simulate: bool = False,
) -> WifiSurvey:
    """Sweep a Wi-Fi band and score per-channel occupancy (receive-only)."""
    if band not in _BAND_RANGE_MHZ:
        raise ValueError(f"Unknown band '{band}' (use 2.4 or 5).")
    low_mhz, high_mhz = _BAND_RANGE_MHZ[band]
    result = sweep_mod.sweep(
        cfg, low_mhz, high_mhz, bin_khz=bin_khz, snr_db=snr_db,
        sweeps=sweeps, simulate=simulate,
    )
    floor = result.noise_floor_db
    survey = WifiSurvey(band=band, floor_db=round(floor, 1), simulated=simulate)
    for ch in channels_for(band):
        load = _occupancy(result.bins, ch, floor, snr_db)
        if load is not None:
            survey.loads.append(load)
    return survey


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _bar(pct: float, width: int = 12) -> str:
    filled = int(round(pct / 100.0 * width))
    return "█" * filled + "·" * (width - filled)


def summarize(survey: WifiSurvey) -> None:
    """Print a per-channel occupancy table for one band."""
    label = "2.4 GHz" if survey.band == "2.4" else "5 GHz"
    title = f"Wi-Fi {label} channel survey"
    if survey.simulated:
        title += " [SIMULATED]"
    rows = []
    for ld in survey.loads:
        ch = ld.channel
        marks = []
        if ch.number in _CLEAN_24 and survey.band == "2.4":
            marks.append("★")
        if ch.dfs:
            marks.append("DFS")
        rows.append([
            f"{ch.number}{(' ' + ' '.join(marks)) if marks else ''}",
            f"{ch.center_mhz:.0f}",
            f"{_bar(ld.occupancy_pct)} {ld.occupancy_pct:.0f}%",
            f"{ld.peak_db:.0f}",
            f"{ld.snr_db:.0f}",
            ld.status,
        ])
    console.table(
        title,
        ["Ch", "Center MHz", "Occupancy", "Peak dB", "SNR dB", "Status"],
        rows,
    )
    console.print_(f"  noise floor ≈ {survey.floor_db} dB · "
                   f"{len(survey.busy_channels)}/{len(survey.loads)} channels busy")
    best, reason = survey.recommend()
    if best is not None:
        console.success(
            f"Suggested channel: {best.channel.number} "
            f"({best.channel.center_mhz:.0f} MHz) — {reason} "
            f"({best.occupancy_pct:.0f}% occupancy)"
        )
