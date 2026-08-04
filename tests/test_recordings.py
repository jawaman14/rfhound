import json

import pytest

from rfhound.config import Config
from rfhound.modules import capture as capture_mod
from rfhound.modules import recordings


def test_capture_writes_num_samples(tmp_path):
    cfg = Config(output_dir=str(tmp_path))
    cap = capture_mod.capture_iq(cfg, 433.92, 1.0, simulate=True)
    meta = json.loads(cap.meta_path.read_text())
    assert meta["global"]["rfhound:num_samples"] == cap.num_samples


def test_list_recordings(tmp_path):
    cfg = Config(output_dir=str(tmp_path))
    capture_mod.capture_iq(cfg, 433.92, 1.0, name="a", simulate=True)
    capture_mod.capture_iq(cfg, 1090.0, 2.0, name="b", simulate=True)
    recs = recordings.list_recordings(tmp_path)
    names = {r.name for r in recs}
    assert {"a", "b"} <= names
    a = next(r for r in recs if r.name == "a")
    assert abs(a.freq_mhz - 433.92) < 0.01


def test_find_recording_by_name_variants(tmp_path):
    cfg = Config(output_dir=str(tmp_path))
    capture_mod.capture_iq(cfg, 433.92, 1.0, name="x", simulate=True)
    assert recordings.find_recording(tmp_path, "x") is not None
    assert recordings.find_recording(tmp_path, "x.sigmf-data") is not None
    assert recordings.find_recording(tmp_path, "nope") is None


def test_list_empty_dir(tmp_path):
    assert recordings.list_recordings(tmp_path / "none") == []


# --- classification needs numpy + a real IQ signal ---
np = pytest.importorskip("numpy")


def _write_real_capture(tmp_path, name="sig"):
    sr, center = 2_000_000, 433_920_000
    t = np.arange(60000) / sr
    carrier = np.exp(2j * np.pi * 30_000 * t)
    gate = (np.sin(2 * np.pi * 400 * t) > 0).astype(float)  # OOK
    sig = carrier * gate
    inter = np.empty(sig.size * 2, dtype=np.int8)
    inter[0::2] = np.clip(sig.real * 120, -127, 127).astype(np.int8)
    inter[1::2] = np.clip(sig.imag * 120, -127, 127).astype(np.int8)
    data = tmp_path / f"{name}.sigmf-data"
    inter.tofile(str(data))
    meta = {"global": {"core:sample_rate": sr, "rfhound:num_samples": sig.size},
            "captures": [{"core:frequency": center}]}
    (tmp_path / f"{name}.sigmf-meta").write_text(json.dumps(meta))
    return data


def test_classify_recording_writes_metadata(tmp_path):
    data = _write_real_capture(tmp_path)
    r = recordings.classify_recording(data, Config())
    assert r.modulation == "ook"
    assert r.decoder == "rtl433"          # 433.92 OOK → rtl_433
    assert r.guess_confidence > 50
    # Persisted into the sidecar.
    g = json.loads(data.with_suffix(".sigmf-meta").read_text())["global"]
    assert g["rfhound:guess"] == r.guess
    assert g["rfhound:decode_settings"]["decoder"] == "rtl433"


def test_decode_settings_from_recording(tmp_path):
    data = _write_real_capture(tmp_path, "y")
    recordings.classify_recording(data, Config())
    rec = recordings.find_recording(tmp_path, "y")
    ds = recordings.decode_settings(rec)
    assert ds["decoder"] == "rtl433"
    assert ds["sample_rate"] == 2_000_000
