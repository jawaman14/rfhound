"""IQ capture analysis: measure real bandwidth and detect modulation.

Where the sweep-based classifier guesses from frequency alone, this measures the
*actual* signal from a recorded IQ file — occupied bandwidth (from the power
spectrum) and a modulation-detection pass (OOK/ASK, FSK, PSK, analog-FM, or
noise) from amplitude/phase statistics. Feed the results into
:func:`rfhound.modules.classify.classify` for a sharper answer.

NumPy is required only for this module (``pip install rfhound[iq]``). It is
imported lazily so the rest of RFHound needs no heavy dependencies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


def _np():
    try:
        import numpy as np
        return np
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "IQ analysis needs NumPy. Install it with: pip install 'rfhound[iq]' "
            "(or: pip install numpy)."
        ) from exc


@dataclass
class IQMeta:
    sample_rate: int
    center_hz: int | None


def read_sigmf_meta(data_path: Path) -> IQMeta:
    meta_path = Path(data_path).with_suffix(".sigmf-meta")
    sr, cf = 8_000_000, None
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text())
            sr = int(m.get("global", {}).get("core:sample_rate", sr))
            caps = m.get("captures") or [{}]
            cf = caps[0].get("core:frequency")
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return IQMeta(sample_rate=sr, center_hz=cf)


def load_iq(data_path: Path, *, max_samples: int = 1_000_000):
    """Load interleaved signed-8-bit IQ (HackRF 'ci8') into a complex array."""
    np = _np()
    raw = np.fromfile(str(data_path), dtype=np.int8, count=max_samples * 2)
    if raw.size < 2:
        raise RuntimeError(f"{data_path} has no IQ samples.")
    if raw.size % 2:
        raw = raw[:-1]
    iq = raw.astype(np.float32).view()
    i = iq[0::2] / 128.0
    q = iq[1::2] / 128.0
    return (i + 1j * q).astype(np.complex64)


def measure_bandwidth_khz(iq, sample_rate: int, *, occupancy: float = 0.99) -> float:
    """Occupied bandwidth via the 99%-power span of the averaged spectrum."""
    np = _np()
    n = 4096 if iq.size >= 4096 else 1 << int(np.log2(max(2, iq.size)))
    # Average periodogram over segments (Bartlett).
    segs = max(1, iq.size // n)
    acc = np.zeros(n)
    win = np.hanning(n)
    for k in range(segs):
        seg = iq[k * n:(k + 1) * n]
        if seg.size < n:
            break
        spec = np.fft.fftshift(np.fft.fft(seg * win))
        acc += (spec.real ** 2 + spec.imag ** 2)
    psd = acc / max(1, segs)
    total = psd.sum()
    if total <= 0:
        return 0.0
    # Find the smallest contiguous span holding `occupancy` of the power.
    cumulative = np.cumsum(psd)
    target = occupancy * total
    lo_i, hi_i, best = 0, n - 1, n
    j = 0
    for i in range(n):
        while j < n and (cumulative[j] - (cumulative[i - 1] if i > 0 else 0)) < target:
            j += 1
        if j >= n:
            break
        if j - i < best:
            best, lo_i, hi_i = j - i, i, j
    bw_hz = (hi_i - lo_i) / n * sample_rate
    return round(bw_hz / 1000.0, 1)


@dataclass
class ModResult:
    modulation: str          # ook | fsk | psk | fm | noise
    confidence: int          # 0..100
    continuity: str          # burst | continuous
    duty: float              # fraction of samples "on"
    snr_db: float
    features: dict = field(default_factory=dict)


def detect_modulation(iq, sample_rate: int) -> ModResult:
    """Heuristic modulation-detection pass from amplitude/phase statistics."""
    np = _np()
    amp = np.abs(iq)
    if amp.size < 64 or amp.max() <= 0:
        return ModResult("noise", 0, "continuous", 0.0, 0.0)
    amp_n = amp / (amp.max() + 1e-9)

    # Signal-present detector: spectral peak-to-median (works for constant-
    # envelope signals where amplitude statistics alone look like noise).
    nfft = 4096 if iq.size >= 4096 else 1 << max(1, int(np.log2(iq.size)))
    spec = np.fft.fft(iq[:nfft] * np.hanning(nfft))
    psd = spec.real ** 2 + spec.imag ** 2
    med = np.median(psd) + 1e-12
    snr_db = float(10 * np.log10((psd.max() + 1e-12) / med))

    # Duty / on-off: fraction of samples above a mid threshold.
    on = amp_n > 0.5
    duty = float(on.mean())
    continuity = "burst" if duty < 0.85 else "continuous"

    # Amplitude coefficient of variation (high for OOK/ASK, low for FM/PSK/FSK).
    amp_cv = float(amp.std() / (amp.mean() + 1e-9))

    # Instantaneous frequency (for FSK/FM discrimination).
    phase = np.unwrap(np.angle(iq))
    inst_freq = np.diff(phase)
    if inst_freq.size:
        ifq = inst_freq[np.isfinite(inst_freq)]
        # Bimodality of instantaneous frequency → FSK.
        med = np.median(ifq)
        pos = ifq[ifq > med]
        neg = ifq[ifq <= med]
        sep = abs(pos.mean() - neg.mean()) / (ifq.std() + 1e-9) if ifq.size else 0.0
        if_spread = float(ifq.std())
    else:
        sep, if_spread = 0.0, 0.0

    features = {"amp_cv": round(amp_cv, 3), "duty": round(duty, 3),
                "freq_bimodality": round(float(sep), 3),
                "if_spread": round(if_spread, 4), "snr_db": round(snr_db, 1)}

    # Decision tree.
    if snr_db < 6:
        return ModResult("noise", 30, continuity, duty, snr_db, features)
    if amp_cv > 0.7 or duty < 0.6:
        conf = min(95, int(60 + amp_cv * 40))
        return ModResult("ook", conf, continuity, duty, snr_db, features)
    if sep > 0.9 and if_spread > 0:
        return ModResult("fsk", min(90, int(55 + sep * 30)), continuity, duty, snr_db, features)
    if if_spread > 0.2:
        return ModResult("fm", 65, continuity, duty, snr_db, features)
    return ModResult("psk", 60, continuity, duty, snr_db, features)


@dataclass
class IQAnalysis:
    path: str
    sample_rate: int
    center_mhz: float | None
    bandwidth_khz: float
    modulation: ModResult


def analyze(data_path: Path, *, max_samples: int = 1_000_000) -> IQAnalysis:
    """Full analysis of an IQ capture: bandwidth + modulation + metadata."""
    meta = read_sigmf_meta(data_path)
    iq = load_iq(data_path, max_samples=max_samples)
    bw = measure_bandwidth_khz(iq, meta.sample_rate)
    mod = detect_modulation(iq, meta.sample_rate)
    return IQAnalysis(
        path=str(data_path), sample_rate=meta.sample_rate,
        center_mhz=(meta.center_hz / 1e6) if meta.center_hz else None,
        bandwidth_khz=bw, modulation=mod,
    )
