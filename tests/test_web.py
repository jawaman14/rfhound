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


def test_security_headers(base_url):
    with urllib.request.urlopen(base_url + "/api/version", timeout=5) as r:
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"


def test_favicon_no_content(base_url):
    with urllib.request.urlopen(base_url + "/favicon.ico", timeout=5) as r:
        assert r.status == 204


def test_dashboard_has_new_controls(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        html = r.read().decode()
    # Live auto-refresh, waterfall colormap/intensity, and export controls.
    assert 'id="live"' in html and "setLive" in html
    assert 'id="wfMap"' in html and 'id="wfGain"' in html and "colormap" in html
    assert "expPeaksCsv" in html and "exportRecon" in html and "exportBands" in html


@pytest.fixture()
def auth_url():
    state = web.build_app_state(Config(), force_simulate=True, token="s3cr3t")
    handler = web._make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def test_auth_required_401(auth_url):
    try:
        get(auth_url + "/api/status")
        assert False, "expected 401"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_auth_html_shell_always_served(auth_url):
    # The HTML carries no data, so it must load even without a token.
    with urllib.request.urlopen(auth_url + "/", timeout=5) as r:
        assert r.status == 200


def test_auth_bearer_header(auth_url):
    req = urllib.request.Request(auth_url + "/api/status",
                                 headers={"Authorization": "Bearer s3cr3t"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200


def test_auth_query_param(auth_url):
    code, data = get(auth_url + "/api/status?token=s3cr3t")
    assert code == 200 and "tools" in data


def test_auth_wrong_token_401(auth_url):
    try:
        get(auth_url + "/api/status?token=nope")
        assert False, "expected 401"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_token_ok_constant_time():
    st = web.build_app_state(Config(), token="abc")
    assert st.token_ok("abc") is True
    assert st.token_ok("abd") is False
    assert st.token_ok(None) is False
    assert web.build_app_state(Config(), token=None).token_ok(None) is True


def _post(url, body, token=None):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


@pytest.fixture()
def bm_url(tmp_path, monkeypatch):
    # Isolate the config file so the test never touches the real one.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    state = web.build_app_state(Config(), force_simulate=True)
    handler = web._make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def test_bookmark_add_and_delete(bm_url):
    code, data = _post(bm_url + "/api/bookmarks/add",
                       {"name": "myfob", "freq_mhz": 433.92, "note": "car"})
    assert code == 200
    assert any(b["name"] == "myfob" and b["freq_mhz"] == 433.92 for b in data["bookmarks"])
    # It should also show up on the GET endpoint.
    _, got = get(bm_url + "/api/bookmarks")
    assert any(b["name"] == "myfob" for b in got["bookmarks"])
    # Delete it.
    code, data = _post(bm_url + "/api/bookmarks/delete", {"name": "myfob"})
    assert code == 200 and data["removed"] == 1
    assert not any(b["name"] == "myfob" for b in data["bookmarks"])


def test_bookmark_add_validation(bm_url):
    for bad in [{"name": "", "freq_mhz": 100}, {"name": "x", "freq_mhz": -1},
                {"name": "x", "freq_mhz": "nan-ish"}]:
        try:
            _post(bm_url + "/api/bookmarks/add", bad)
            assert False, "expected 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400


def test_bookmark_add_requires_token():
    state = web.build_app_state(Config(), force_simulate=True, token="tok")
    handler = web._make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    try:
        try:
            _post(url + "/api/bookmarks/add", {"name": "x", "freq_mhz": 100})
            assert False, "expected 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        httpd.shutdown()
        httpd.server_close()
