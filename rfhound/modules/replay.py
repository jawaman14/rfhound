"""Authorized replay of a previously captured IQ file.

This is the *only* transmit path in RFHound and it is deliberately narrow:
replay an exact IQ recording you made, at the frequency it was recorded on, for
authorized testing of your own equipment. Every call goes through
:func:`safety.authorize_tx`.

RFHound intentionally provides no signal *generation*, fuzzing-over-the-air,
jamming, or brute-force transmit. If you need to craft/modulate new frames for
authorized testing, use Universal Radio Hacker deliberately and knowingly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import proc, safety
from ..config import Config
from ..exceptions import RFHoundError


@dataclass
class ReplayPlan:
    data_path: Path
    freq_hz: int
    sample_rate: int
    tx_gain: int
    command: list[str]


def _read_capture_meta(data_path: Path) -> tuple[int | None, int | None]:
    """Best-effort read of frequency & sample rate from a SigMF sidecar."""
    meta_path = data_path.with_suffix(".sigmf-meta")
    if not meta_path.exists():
        return None, None
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None
    sr = meta.get("global", {}).get("core:sample_rate")
    caps = meta.get("captures") or [{}]
    freq = caps[0].get("core:frequency")
    return freq, sr


def build_replay_plan(
    cfg: Config,
    data_path: Path,
    *,
    freq_hz: int | None = None,
    sample_rate: int | None = None,
    tx_gain: int | None = None,
) -> ReplayPlan:
    """Assemble (but do not run) a replay command, filling gaps from metadata."""
    if not data_path.exists():
        raise RFHoundError(f"Capture file not found: {data_path}")
    meta_freq, meta_sr = _read_capture_meta(data_path)
    freq = freq_hz or meta_freq
    sr = sample_rate or meta_sr or cfg.sample_rate
    if not freq:
        raise RFHoundError(
            "No frequency given and none found in the capture metadata. "
            "Pass an explicit frequency."
        )
    gain = tx_gain if tx_gain is not None else cfg.tx_gain
    command = [
        "hackrf_transfer",
        "-t", str(data_path),
        "-f", str(freq),
        "-s", str(sr),
        "-x", str(gain),
    ]
    return ReplayPlan(data_path, freq, sr, gain, command)


def replay(
    cfg: Config,
    data_path: Path,
    *,
    authorized: bool,
    freq_hz: int | None = None,
    sample_rate: int | None = None,
    tx_gain: int | None = None,
    dry_run: bool = False,
) -> ReplayPlan:
    """Replay an IQ capture. Raises SafetyError unless fully authorized."""
    plan = build_replay_plan(
        cfg, data_path, freq_hz=freq_hz, sample_rate=sample_rate, tx_gain=tx_gain
    )
    # Hard safety gate — must pass before we ever key the transmitter.
    safety.authorize_tx(cfg, plan.freq_hz, authorized=authorized)
    if dry_run:
        return plan
    proc.require_tool("hackrf_transfer")
    proc.run(plan.command, timeout=120)
    return plan
