import math
import threading
from http.server import ThreadingHTTPServer

import pytest

np = pytest.importorskip("numpy")

from rfhound.modules import tdoa  # noqa: E402
from rfhound.net import hub as hub_mod  # noqa: E402
from rfhound.net import node as node_mod  # noqa: E402


@pytest.fixture()
def hub_url():
    state = hub_mod.HubState()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hub_mod.make_hub_handler(state))
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def test_iq_b64_roundtrip():
    rng = np.random.default_rng(0)
    sig = (rng.standard_normal(2048) + 1j * rng.standard_normal(2048)).astype(np.complex64)
    b64, n = tdoa.encode_iq_b64(sig)
    back = tdoa.decode_iq_b64(b64, n)
    assert back.size == n
    # Correlation of original vs decoded should peak at lag 0.
    tau = tdoa.estimate_tdoa(sig, back, 1_000_000)
    assert abs(tau) < 2e-6


def test_nodes_from_hub_reports_snippets():
    emitter = (51.512, -0.121)
    geom = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.135), (51.518, -0.145)]
    caps = tdoa.simulate_captures(emitter, geom, sample_rate=40_000_000, n_samples=16384)
    reports = []
    for i, c in enumerate(caps):
        b64, n = tdoa.encode_iq_b64(c["iq"])
        reports.append({"node_id": c["node"], "kind": "tdoa", "t": i,
                        "data": {"lat": c["lat"], "lon": c["lon"], "trigger": "T1",
                                 "iq_b64": b64, "n": n, "sample_rate": 40_000_000}})
    nodes = tdoa.nodes_from_hub_reports(reports, trigger="T1")
    fix = tdoa.geolocate_tdoa(nodes)
    assert fix.method == "tdoa"
    e1, n1 = tdoa.latlon_to_enu(fix.lat, fix.lon, emitter[0], emitter[1])
    assert math.hypot(e1, n1) < 400.0


def test_nodes_from_hub_reports_measurements():
    emitter = (51.510, -0.118)
    geom = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.130), (51.515, -0.140)]
    sim = tdoa.simulate_scenario(emitter, geom)
    reports = [{"node_id": nd.node, "kind": "tdoa", "t": i,
                "data": {"lat": nd.lat, "lon": nd.lon, "trigger": "X", "tdoa_s": nd.tdoa_s}}
               for i, nd in enumerate(sim)]
    nodes = tdoa.nodes_from_hub_reports(reports)
    assert len(nodes) == 4
    fix = tdoa.geolocate_tdoa(nodes)
    assert fix.method == "tdoa"


def test_full_hub_roundtrip(hub_url):
    emitter = (51.510, -0.118)
    geom = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.130), (51.515, -0.140)]
    caps = tdoa.simulate_captures(emitter, geom, sample_rate=20_000_000, n_samples=8192)
    for c in caps:
        b64, n = tdoa.encode_iq_b64(c["iq"])
        node_mod.push_tdoa(hub_url, c["node"], c["lat"], c["lon"], "run1",
                           iq_b64=b64, n=n, sample_rate=20_000_000)
    state = node_mod.hub_state(hub_url)
    nodes = tdoa.nodes_from_hub_reports(state["reports"], trigger="run1")
    fix = tdoa.geolocate_tdoa(nodes)
    assert fix.method == "tdoa"
    e1, n1 = tdoa.latlon_to_enu(fix.lat, fix.lon, emitter[0], emitter[1])
    assert math.hypot(e1, n1) < 500.0


def test_empty_reports():
    assert tdoa.nodes_from_hub_reports([]) == []
