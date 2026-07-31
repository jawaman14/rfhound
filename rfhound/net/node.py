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
