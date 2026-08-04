import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from rfhound.config import Config
from rfhound.web import server as web


@pytest.fixture()
def base_url():
    state = web.build_app_state(Config(), force_simulate=True)
    handler = web._make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def test_dashboard_served(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        body = r.read().decode()
    assert r.status == 200
    assert "RFHound" in body
    assert "<canvas" in body


def test_version(base_url):
    code, data = get(base_url + "/api/version")
    assert code == 200
    assert "version" in data


def test_status(base_url):
    code, data = get(base_url + "/api/status")
    assert code == 200
    assert "tools" in data and "device" in data and "hardware" in data


def test_bands(base_url):
    code, data = get(base_url + "/api/bands")
    assert code == 200
    assert any("ADS-B" in b["name"] for b in data["bands"])


def test_bookmarks_endpoint(base_url):
    code, data = get(base_url + "/api/bookmarks")
    assert code == 200
    assert "bookmarks" in data


def test_dashboard_has_smeter_and_bookmarks(base_url):
    import urllib.request
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        html = r.read().decode()
    assert "S-METER" in html and "smeterFill" in html
    assert 'id="bookmarks"' in html and "loadBookmarks" in html


def test_sweep_has_smeter_fields(base_url):
    code, data = get(base_url + "/api/sweep?start=433&stop=435")
    assert code == 200
    assert "max_db" in data and "noise_floor_db" in data  # S-meter inputs


def test_sweep_simulated(base_url):
    code, data = get(base_url + "/api/sweep?start=433&stop=435")
    assert code == 200
    assert data["simulated"] is True
    assert len(data["spectrum"]) == 256
    assert data["peaks"]


def test_recon_simulated(base_url):
    code, data = get(base_url + "/api/recon")
    assert code == 200
    assert data["simulated"] is True
    assert data["findings"]


def test_drone_simulated(base_url):
    code, data = get(base_url + "/api/defense/drone")
    assert code == 200
    assert data["hits"]


def test_spoof_adsb_simulated(base_url):
    code, data = get(base_url + "/api/defense/spoof/adsb")
    assert code == 200
    assert any(f["kind"] == "teleport" for f in data["findings"])


def test_imsi_simulated(base_url):
    code, data = get(base_url + "/api/defense/imsi")
    assert code == 200
    assert data["alerts"] and data["score"] > 0


def test_hop_simulated(base_url):
    code, data = get(base_url + "/api/defense/hop")
    assert code == 200
    assert data["hopping_suspected"] is True


def test_at_endpoint(base_url):
    code, data = get(base_url + "/api/at?freq=433.92")
    assert code == 200
    assert data["found"] is True
    assert "rtl433" in data["decoders"]


def test_404(base_url):
    try:
        get(base_url + "/api/nope")
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404
