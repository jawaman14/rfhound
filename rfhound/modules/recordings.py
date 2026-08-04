"""Recordings catalog — captures that remember how to decode themselves.

A capture is IQ + a SigMF sidecar. This adds a light management layer: after (or
after the fact) it runs the signal classifier over the IQ and writes the result
back into the sidecar — measured bandwidth, detected modulation, the best-guess
signal type, and the **decode settings** (which decoder, at what frequency and
sample rate). So a recording carries everything needed to replay or decode it
later, and ``recordings list`` shows a catalog with the classification.

Classification needs NumPy (``pip install rfhound[iq]``). Listing does not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from . import classify as classify_mod


@dataclass
class RecordingInfo:
    name: str
    data_path: Path
    meta_path: Path
    freq_mhz: float | None
    sample_rate: int | None
    num_samples: int | None
    guess: str | None = None
    guess_confidence: int | None = None
    modulation: str | None = None
    bandwidth_khz: float | None = None
    decoder: str | None = None

    @property
    def seconds(self) -> float | None:
        if self.sample_rate and self.num_samples:
            return round(self.num_samples / self.sample_rate, 3)
        return None


def _read_meta(meta_path: Path) -> dict:
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_meta(meta_path: Path, meta: dict) -> None:
    meta_path.write_text(json.dumps(meta, indent=2))


def _info_from_meta(data_path: Path, meta_path: Path) -> RecordingInfo:
    meta = _read_meta(meta_path)
    g = meta.get("global", {})
    caps = meta.get("captures") or [{}]
    freq = caps[0].get("core:frequency")
    return RecordingInfo(
        name=data_path.stem,
        data_path=data_path,
        meta_path=meta_path,
        freq_mhz=(freq / 1e6) if freq else None,
        sample_rate=g.get("core:sample_rate"),
        num_samples=g.get("rfhound:num_samples"),
        guess=g.get("rfhound:guess"),
        guess_confidence=g.get("rfhound:guess_confidence"),
        modulation=g.get("rfhound:modulation"),
        bandwidth_khz=g.get("rfhound:bandwidth_khz"),
        decoder=g.get("rfhound:suggested_decoder"),
    )


def list_recordings(output_dir: str | Path) -> list[RecordingInfo]:
    out = Path(output_dir)
    if not out.exists():
        return []
    recs = []
    for meta_path in sorted(out.glob("*.sigmf-meta")):
        data_path = meta_path.with_suffix(".sigmf-data")
        recs.append(_info_from_meta(data_path, meta_path))
    return recs


def find_recording(output_dir: str | Path, name: str) -> RecordingInfo | None:
    name = name.replace(".sigmf-data", "").replace(".sigmf-meta", "")
    for r in list_recordings(output_dir):
        if r.name == name:
            return r
    return None


@dataclass
class ClassifyResult:
    bandwidth_khz: float
    modulation: str
    mod_confidence: int
    guess: str
    guess_confidence: int
    decoder: str | None
    freq_mhz: float | None
    sample_rate: int


def classify_recording(data_path: Path, cfg: Config | None = None) -> ClassifyResult:
    """Run the classifier over a recording's IQ and write it into the sidecar."""
    from . import iqtools  # lazy: needs numpy
    data_path = Path(data_path)
    a = iqtools.analyze(data_path)
    center = a.center_mhz
    matches = classify_mod.classify(center or 0.0, bandwidth_khz=a.bandwidth_khz,
                                    modulation=a.modulation.modulation)
    best = matches[0]
    result = ClassifyResult(
        bandwidth_khz=a.bandwidth_khz,
        modulation=a.modulation.modulation,
        mod_confidence=a.modulation.confidence,
        guess=best.name,
        guess_confidence=best.likelihood,
        decoder=best.decoder,
        freq_mhz=center,
        sample_rate=a.sample_rate,
    )
    # Persist into the SigMF sidecar under rfhound: keys.
    meta_path = data_path.with_suffix(".sigmf-meta")
    meta = _read_meta(meta_path)
    g = meta.setdefault("global", {})
    g["rfhound:bandwidth_khz"] = result.bandwidth_khz
    g["rfhound:modulation"] = result.modulation
    g["rfhound:mod_confidence"] = result.mod_confidence
    g["rfhound:guess"] = result.guess
    g["rfhound:guess_confidence"] = result.guess_confidence
    g["rfhound:suggested_decoder"] = result.decoder
    g["rfhound:decode_settings"] = {
        "decoder": result.decoder,
        "freq_mhz": result.freq_mhz,
        "sample_rate": result.sample_rate,
    }
    _write_meta(meta_path, meta)
    return result


def decode_settings(rec: RecordingInfo) -> dict:
    """The stored decode settings for a recording (decoder + freq + rate)."""
    meta = _read_meta(rec.meta_path)
    return meta.get("global", {}).get("rfhound:decode_settings", {
        "decoder": rec.decoder, "freq_mhz": rec.freq_mhz, "sample_rate": rec.sample_rate})
