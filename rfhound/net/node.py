"""Node client: push this receiver's status and findings to a hub."""

from __future__ import annotations

import json
import urllib.request


def _post(hub_url: str, path: str, payload: dict, token: str = "", timeout: float = 15) -> dict:
    url = hub_url.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def register(hub_url: str, node_id: str, *, name: str = "", location: str = "",
             token: str = "") -> dict:
    return _post(hub_url, "/api/hub/register",
                 {"node_id": node_id, "name": name, "location": location}, token)


def report(hub_url: str, node_id: str, kind: str, data, *, token: str = "") -> dict:
    return _post(hub_url, "/api/hub/report",
                 {"node_id": node_id, "kind": kind, "data": data}, token)


def hub_state(hub_url: str, *, token: str = "", timeout: float = 15) -> dict:
    """Fetch the hub's aggregated state (nodes + recent reports)."""
    url = hub_url.rstrip("/") + "/api/hub/state"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def push_tdoa(hub_url: str, node_id: str, lat: float, lon: float, trigger: str, *,
              iq_b64: str | None = None, n: int | None = None,
              sample_rate: int | None = None, tdoa_s: float | None = None,
              rssi: float | None = None, token: str = "") -> dict:
    """Push a TDOA contribution for a collection *trigger*: either an IQ snippet
    (``iq_b64``+``n``+``sample_rate``) or a pre-computed ``tdoa_s``."""
    data: dict = {"lat": lat, "lon": lon, "trigger": trigger}
    if iq_b64 is not None:
        data.update({"iq_b64": iq_b64, "n": n, "sample_rate": sample_rate})
    if tdoa_s is not None:
        data["tdoa_s"] = tdoa_s
    if rssi is not None:
        data["rssi"] = rssi
    return _post(hub_url, "/api/hub/report",
                 {"node_id": node_id, "kind": "tdoa", "data": data}, token)
