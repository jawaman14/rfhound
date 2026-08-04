"""IQ capture to disk with a SigMF-style metadata sidecar.

Records raw 8-bit IQ via ``hackrf_transfer -r`` and writes a ``.sigmf-meta``
JSON sidecar so captures are self-describing and can be opened later in URH,
inspectrum, GNU Radio, etc.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .. import bandplan, proc
from ..config import Config


@dataclass
class Capture:
    data_path: Path
    meta_path: Path
    freq_hz: int
    sample_rate: int
    seconds: float
    num_samples: int


def _write_sigmf(meta_path: Path, freq_hz: int, sample_rate: int, note: str,
                 num_samples: int = 0) -> None:
    """Write a minimal SigMF-compatible metadata file.

    HackRF's -r output is interleaved signed 8-bit IQ => SigMF datatype "ci8".
    """
    band = bandplan.find_band(freq_hz)
    meta = {
        "global": {
            "core:datatype": "ci8",
            "core:sample_rate": sample_rate,
            "core:version": "1.0.0",
            "core:hw": "HackRF One",
            "core:description": note or (band.name if band else "RFHound capture"),
            "rfhound:band": band.name if band else None,
            "rfhound:category": band.category if band else None,
            "rfhound:num_samples": num_samples,
        },
        "captures": [
            {
                "core:sample_start": 0,
                "core:frequency": freq_hz,
                "core:datetime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        ],
        "annotations": [],
    }
    meta_path.write_text(json.dumps(meta, indent=2))


def capture_iq(
    cfg: Config,
    freq_mhz: float,
    seconds: float,
    *,
    name: str | None = None,
    sample_rate: int | None = None,
    note: str = "",
    simulate: bool = False,
) -> Capture:
    """Record *seconds* of IQ at *freq_mhz* into the configured output dir."""
    freq_hz = int(freq_mhz * 1e6)
    sr = sample_rate or cfg.sample_rate
    num_samples = int(sr * seconds)

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = name or f"capture_{int(freq_mhz)}MHz_{stamp}"
    data_path = out_dir / f"{base}.sigmf-data"
    meta_path = out_dir / f"{base}.sigmf-meta"

    if simulate:
        # Write a small placeholder so the pipeline is exercised end-to-end.
        data_path.write_bytes(b"\x00\x00" * min(num_samples, 4096))
    else:
        proc.require_tool("hackrf_transfer")
        args = [
            "hackrf_transfer",
            "-r", str(data_path),
            "-f", str(freq_hz),
            "-s", str(sr),
            "-n", str(num_samples),
            "-l", str(cfg.lna_gain),
            "-g", str(cfg.vga_gain),
        ]
        args += proc.hackrf_common_args(cfg)
        proc.run(args, timeout=seconds + 30)

    _write_sigmf(meta_path, freq_hz, sr, note, num_samples=num_samples)
    return Capture(
        data_path=data_path,
        meta_path=meta_path,
        freq_hz=freq_hz,
        sample_rate=sr,
        seconds=seconds,
        num_samples=num_samples,
    )
