from rfhound.modules import frontend, geo


def test_frontend_recommend_bands():
    assert frontend.recommend(1090).band.startswith("L-band")
    assert "ADS-B" in frontend.recommend(1090).band
    assert frontend.recommend(433.92).band.startswith("70cm")
    assert frontend.recommend(100).band.startswith("VHF low")
    assert frontend.recommend(1575).band.startswith("GNSS")


def test_frontend_out_of_range():
    assert frontend.recommend(9000) is None


def test_frontend_guide_covers_spectrum():
    g = frontend.guide()
    assert len(g) >= 8
    assert all(fe.antenna and fe.filter and fe.lna for fe in g)
    assert frontend.GENERAL_NOTES


def test_geo_fix_geojson_structure():
    fc = geo.fix_geojson(51.5, -0.12, {"method": "tdoa", "confidence_m": 25},
                         nodes=[{"node": "n1", "lat": 51.52, "lon": -0.10},
                                {"node": "n2", "lat": None, "lon": None}])
    assert fc["type"] == "FeatureCollection"
    # emitter + one valid receiver (the None-coord node is skipped)
    assert len(fc["features"]) == 2
    em = fc["features"][0]
    assert em["properties"]["role"] == "emitter"
    assert em["geometry"]["coordinates"] == [-0.12, 51.5]  # [lon, lat]
    assert fc["features"][1]["properties"]["role"] == "receiver"


def test_geo_write(tmp_path):
    fc = geo.fix_geojson(51.5, -0.12, {"method": "rssi-centroid"})
    out = geo.write_geojson(tmp_path / "fix.geojson", fc)
    assert out.exists()
    import json
    data = json.loads(out.read_text())
    assert data["features"][0]["geometry"]["type"] == "Point"


def test_geo_kml_valid_xml(tmp_path):
    import xml.dom.minidom as minidom
    kml = geo.fix_kml(51.5, -0.12, {"method": "tdoa", "gdop": 0.8},
                      nodes=[{"node": "n1", "lat": 51.52, "lon": -0.10}])
    assert "<coordinates>-0.120000,51.500000,0</coordinates>" in kml  # lon,lat,alt
    assert "<name>n1</name>" in kml
    out = geo.write_kml(tmp_path / "fix.kml", kml)
    minidom.parse(str(out))    # parses => well-formed XML


def test_geo_kml_escapes_xml():
    kml = geo.fix_kml(51.5, -0.12, {"note": "a & b <x>"})
    assert "&amp;" in kml and "&lt;x&gt;" in kml


def test_points_geojson_multi():
    pts = [{"lat": 51.5, "lon": -0.1, "id": "a", "rssi_dbm": -60},
           {"lat": 50.9, "lon": -1.4, "id": "b", "rssi_dbm": -71},
           {"lat": None, "lon": 1.0, "id": "skip"}]     # dropped (no lat)
    fc = geo.points_geojson(pts)
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    f0 = fc["features"][0]
    assert f0["geometry"]["coordinates"] == [-0.1, 51.5]     # [lon, lat]
    assert f0["properties"]["id"] == "a" and f0["properties"]["rssi_dbm"] == -60
    assert "lat" not in f0["properties"]                     # lat/lon not duplicated


def test_points_kml_valid(tmp_path):
    import xml.dom.minidom as minidom
    pts = [{"lat": 51.5, "lon": -0.1, "label": "BAW117", "rssi_dbm": -62}]
    kml = geo.points_kml(pts)
    assert "<name>BAW117</name>" in kml
    out = geo.write_kml(tmp_path / "c.kml", kml)
    minidom.parse(str(out))
