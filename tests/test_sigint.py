import pytest

from rfhound.modules import sigint


# --- interference characterisation (no numpy) ---
def test_barrage_jamming():
    spectrum = [-40.0] * 100  # whole band raised
    prof = sigint.characterize_interference(spectrum, floor_db=-90)
    assert prof.kind == "barrage"
    assert prof.occupancy > 0.6


def test_spot_jamming():
    spectrum = [-90.0] * 51
    spectrum[25] = -30.0
    prof = sigint.characterize_interference(spectrum, floor_db=-90)
    assert prof.kind == "spot"


def test_no_jamming():
    spectrum = [-89.0, -90.0, -91.0] * 20
    prof = sigint.characterize_interference(spectrum, floor_db=-90)
    assert prof.kind == "none"


# --- emitter catalogue ---
def test_emitter_catalog_ingest_and_upsert(tmp_path):
    cat = sigint.EmitterCatalog(path=tmp_path / "e.json")
    cat.ingest(433.920, power_db=-60, guess="ISM")
    cat.ingest(433.921, power_db=-55, guess="ISM")   # same 25 kHz bucket
    cat.ingest(1090.0, power_db=-50, guess="ADS-B")
    lst = cat.list()
    assert len(lst) == 2
    ism = next(e for e in lst if e.freq_mhz < 500)
    assert ism.count == 2 and ism.max_power_db == -55
    assert ism.itu == "UHF"


def test_emitter_catalog_persist(tmp_path):
    cat = sigint.EmitterCatalog(path=tmp_path / "e.json")
    cat.ingest(162.0, guess="AIS")
    cat2 = sigint.EmitterCatalog(path=tmp_path / "e.json")
    assert cat2.list()[0].guess == "AIS"


# --- geolocation / DF ---
def test_geolocate_centroid():
    est = sigint.geolocate(sigint.simulate_reports())
    assert est.lat is not None
    assert 51.50 <= est.lat <= 51.52
    assert est.n_receivers == 3
    assert est.confidence > 0


def test_geolocate_no_positioned_receivers():
    est = sigint.geolocate([{"node": "x", "rssi": -60}])
    assert est.lat is None


def test_bearing_north_east():
    assert 0 <= sigint.bearing_deg(0, 0, 1, 0) <= 1        # due north
    assert 89 <= sigint.bearing_deg(0, 0, 0, 1) <= 91      # due east


# --- ELINT pulse analysis (needs numpy) ---
np = pytest.importorskip("numpy")


def test_pulse_regular_pri():
    sr = 1_000_000
    n = 100_000
    amp = np.zeros(n)
    # 10 pulses, 50 us wide, every 1000 us (regular PRI).
    pw = int(50e-6 * sr)
    pri = int(1000e-6 * sr)
    for k in range(10):
        s = k * pri
        amp[s:s + pw] = 1.0
    iq = amp.astype(np.complex64)
    prof = sigint.analyze_pulses(iq, sr)
    assert prof.pulses >= 8
    assert "regular PRI" in prof.classification
    assert abs(prof.mean_pri_us - 1000) < 50


def test_pulse_continuous_wave():
    sr = 1_000_000
    iq = np.ones(50_000, dtype=np.complex64)
    prof = sigint.analyze_pulses(iq, sr)
    assert prof.classification == "continuous wave"
