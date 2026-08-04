from rfhound.modules import sightings


def _store(tmp_path):
    return sightings.SightingsStore(path=tmp_path / "s.json")


def test_record_and_upsert(tmp_path):
    s = _store(tmp_path)
    s.record("adsb", "abc123", freq_mhz=1090.0)
    s.record("adsb", "abc123")
    got = s.get("adsb", "abc123")
    assert got.count == 2
    assert got.freq_mhz == 1090.0


def test_persist_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.record("ais", "123456789")
    s2 = sightings.SightingsStore(path=tmp_path / "s.json")
    assert s2.get("ais", "123456789") is not None


def test_list_filter_by_kind(tmp_path):
    s = _store(tmp_path)
    s.record("adsb", "a")
    s.record("ais", "b")
    assert len(s.list()) == 2
    assert len(s.list("adsb")) == 1


def test_clear_by_kind(tmp_path):
    s = _store(tmp_path)
    s.record("adsb", "a")
    s.record("ais", "b")
    removed = s.clear("adsb")
    assert removed == 1
    assert len(s.list()) == 1


def test_extract_id_variants():
    assert sightings.extract_id("adsb", {"icao": "abc"}) == "abc"
    assert sightings.extract_id("ais", {"mmsi": 123}) == "123"
    assert sightings.extract_id("rtl433", {"id": 55, "model": "TPMS"}) == "55"
    assert sightings.extract_id("adsb", {"foo": "bar"}) is None


def test_ingest_rtl433_json_line(tmp_path):
    s = _store(tmp_path)
    line = '{"model":"Toyota-TPMS","id":"3a1b","pressure_kPa":230}'
    rec = sightings.ingest_json_line(s, "rtl433", line, freq_mhz=433.92)
    assert rec is not None and rec.id == "3a1b"
    assert rec.extra.get("model") == "Toyota-TPMS"


def test_ingest_non_json_ignored(tmp_path):
    s = _store(tmp_path)
    assert sightings.ingest_json_line(s, "rtl433", "not json") is None
    assert sightings.ingest_json_line(s, "adsb", "") is None
