import json

import pytest

np = pytest.importorskip("numpy")

from rfhound.modules import iqtools  # noqa: E402


def _write_iq(tmp_path, complex_signal, sample_rate=2_000_000, center_hz=433_920_000):
    """Write a complex signal as HackRF ci8 with a SigMF sidecar."""
    base = tmp_path / "cap"
    data = base.with_suffix(".sigmf-data")
    inter = np.empty(complex_signal.size * 2, dtype=np.int8)
    inter[0::2] = np.clip(np.real(complex_signal) * 120, -127, 127).astype(np.int8)
    inter[1::2] = np.clip(np.imag(complex_signal) * 120, -127, 127).astype(np.int8)
    inter.tofile(str(data))
    meta = {"global": {"core:sample_rate": sample_rate},
            "captures": [{"core:frequency": center_hz}]}
    base.with_suffix(".sigmf-meta").write_text(json.dumps(meta))
    return data


def test_load_and_meta(tmp_path):
    t = np.arange(20000) / 2_000_000
    sig = np.exp(2j * np.pi * 50_000 * t)  # tone at +50 kHz
    data = _write_iq(tmp_path, sig)
    meta = iqtools.read_sigmf_meta(data)
    assert meta.sample_rate == 2_000_000
    assert meta.center_hz == 433_920_000
    iq = iqtools.load_iq(data)
    assert iq.dtype == np.complex64 and iq.size > 1000


def test_bandwidth_narrow_tone(tmp_path):
    t = np.arange(40000) / 2_000_000
    sig = np.exp(2j * np.pi * 10_000 * t)  # very narrow tone
    data = _write_iq(tmp_path, sig)
    a = iqtools.analyze(data)
    # A pure tone occupies a small fraction of the 2 MHz span.
    assert a.bandwidth_khz < 400


def test_detect_ook(tmp_path):
    t = np.arange(40000) / 2_000_000
    carrier = np.exp(2j * np.pi * 30_000 * t)
    gate = (np.sin(2 * np.pi * 500 * t) > 0).astype(float)  # on/off keying
    data = _write_iq(tmp_path, carrier * gate)
    a = iqtools.analyze(data)
    assert a.modulation.modulation == "ook"
    assert a.modulation.continuity == "burst"


def test_detect_fm_or_fsk_continuous(tmp_path):
    t = np.arange(40000) / 2_000_000
    # Constant-amplitude frequency-varying signal.
    inst = np.cumsum(20_000 + 5_000 * np.sin(2 * np.pi * 300 * t)) / 2_000_000
    sig = np.exp(2j * np.pi * inst)
    data = _write_iq(tmp_path, sig)
    a = iqtools.analyze(data)
    assert a.modulation.modulation in ("fm", "fsk", "psk")
    assert a.modulation.continuity == "continuous"


def test_noise_low_confidence(tmp_path):
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(20000) + 1j * rng.standard_normal(20000)) * 0.05
    data = _write_iq(tmp_path, noise.astype(np.complex64))
    a = iqtools.analyze(data)
    # Random noise should not be confidently a clean modulation.
    assert a.modulation.modulation in ("noise", "ook", "fsk", "fm", "psk")
