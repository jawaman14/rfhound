import threading
from http.server import ThreadingHTTPServer

import pytest

from rfhound.net import hub as hub_mod
from rfhound.net import node as node_mod


@pytest.fixture()
def hub_url():
    state = hub_mod.HubState()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hub_mod.make_hub_handler(state))
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", state
    httpd.shutdown()
    httpd.server_close()


def test_register_and_report_roundtrip(hub_url):
    url, state = hub_url
    node_mod.register(url, "n1", name="North sensor", location="Roof A")
    node_mod.report(url, "n1", "drone", {"drone_hits": 2})
    snap = state.snapshot()
    assert any(n["node_id"] == "n1" for n in snap["nodes"])
    assert snap["reports"][-1]["kind"] == "drone"
    assert snap["reports"][-1]["data"]["drone_hits"] == 2


def test_state_endpoint(hub_url):
    import json
    import urllib.request
    url, state = hub_url
    node_mod.register(url, "n2", name="x")
    with urllib.request.urlopen(url + "/api/hub/state", timeout=5) as r:
        data = json.loads(r.read().decode())
    assert any(n["node_id"] == "n2" for n in data["nodes"])


def test_token_auth_blocks_unauthed():
    state = hub_mod.HubState(token="secret")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hub_mod.make_hub_handler(state))
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    try:
        # Wrong/no token -> 401.
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as ei:
            node_mod.register(url, "n1", token="")
        assert ei.value.code == 401
        # Correct token -> ok.
        out = node_mod.register(url, "n1", token="secret")
        assert out["node_id"] == "n1"
    finally:
        httpd.shutdown()
        httpd.server_close()
