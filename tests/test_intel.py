from rfhound.config import Config
from rfhound.modules import intel


def test_baseline_save_and_diff_detects_rogue(tmp_path):
    cfg = Config()
    base = tmp_path / "base.json"
    intel.save_baseline(cfg, 433.0, 435.0, base, simulate=True)
    assert base.exists()
    findings = intel.diff_baseline(cfg, base, simulate=True)
    # Simulated diff injects a strong rogue emitter mid-band.
    assert findings
    assert any(f.kind in ("new", "elevated") for f in findings)
    assert max(f.power_db for f in findings) > -50


def test_load_baseline_rejects_bad_file(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text('{"type": "not-a-baseline"}')
    try:
        intel.load_baseline(bad)
        assert False
    except ValueError:
        pass


def test_adsb_spoof_detects_teleport_and_altitude():
    findings = intel.detect_adsb_spoofing(intel.simulate_adsb_messages())
    kinds = {f.kind for f in findings}
    assert "teleport" in kinds
    assert "impossible-altitude" in kinds


def test_adsb_no_false_positive_on_normal_track():
    msgs = [
        {"icao": "aa", "t": 0, "lat": 51.5, "lon": -0.10, "alt": 35000},
        {"icao": "aa", "t": 10, "lat": 51.5, "lon": -0.08, "alt": 35000},
    ]
    assert intel.detect_adsb_spoofing(msgs) == []


def test_ais_spoof_detects_invalid_and_teleport():
    findings = intel.detect_ais_spoofing(intel.simulate_ais_messages())
    kinds = {f.kind for f in findings}
    assert "invalid-mmsi" in kinds
    assert "teleport" in kinds


def test_drone_scan_simulated_finds_activity():
    cfg = Config()
    hits = intel.drone_scan(cfg, simulate=True)
    assert hits
    assert all(h.confidence in ("low", "medium", "high") for h in hits)


def test_haversine_zero():
    assert intel._haversine_km(0, 0, 0, 0) == 0.0


def test_simulate_contacts_has_aircraft_and_vessels():
    contacts = intel.simulate_contacts()
    kinds = {c.kind for c in contacts}
    assert kinds == {"aircraft", "vessel"}
    assert all(c.lat is not None and c.lon is not None for c in contacts)
    # Sorted strongest RSSI first.
    rssis = [c.rssi_dbm for c in contacts]
    assert rssis == sorted(rssis, reverse=True)


def test_contacts_from_messages_keeps_latest_fix_and_defaults_rssi():
    adsb = [
        {"icao": "aa", "t": 0, "lat": 1.0, "lon": 1.0, "alt": 30000},
        {"icao": "aa", "t": 5, "lat": 2.0, "lon": 2.0, "alt": 31000, "rssi": -55.0},
        {"icao": "bb", "t": 0, "lat": 9.0},   # no lon => dropped
    ]
    ais = [{"mmsi": "m1", "t": 0, "lat": 3.0, "lon": 3.0, "sog": 8}]
    contacts = intel.contacts_from_messages(adsb=adsb, ais=ais)
    ids = {c.id: c for c in contacts}
    assert set(ids) == {"aa", "m1"}
    assert ids["aa"].lat == 2.0 and ids["aa"].rssi_dbm == -55.0   # latest kept
    assert ids["m1"].rssi_dbm == -100.0                          # default when absent
    assert "kt" in ids["m1"].detail
