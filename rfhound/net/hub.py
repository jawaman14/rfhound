"""Aggregator hub: many RFHound nodes report into one shared picture.

Lets you link multiple receivers / operators / computers: each runs RFHound as a
*node* and pushes its status and findings to a central hub over HTTP. The hub
keeps a live roster of nodes and a rolling feed of their reports, exposed as JSON
(and a tiny status page). With several geographically separated nodes this is the
foundation for distributed monitoring and RSSI-based localisation.

Transport is receive-only telemetry (JSON). Optional shared bearer token gates
writes. Bind to localhost unless you intend to expose it; put TLS/auth in front
for anything beyond a trusted LAN.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import __version__, console


class HubState:
    """Thread-safe in-memory store of nodes and recent reports."""

    def __init__(self, token: str = "", max_reports: int = 500):
        self._lock = threading.Lock()
        self.token = token
        self.max_reports = max_reports
        self.nodes: dict[str, dict] = {}
        self.reports: list[dict] = []

    def register(self, node_id: str, name: str, location: str) -> dict:
        with self._lock:
            self.nodes[node_id] = {"node_id": node_id, "name": name,
                                   "location": location, "last_seen": time.time()}
            return self.nodes[node_id]

    def add_report(self, node_id: str, kind: str, data) -> dict:
        rec = {"node_id": node_id, "kind": kind, "data": data, "t": time.time()}
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id]["last_seen"] = rec["t"]
            self.reports.append(rec)
            if len(self.reports) > self.max_reports:
                self.reports = self.reports[-self.max_reports:]
        return rec

    def snapshot(self) -> dict:
        with self._lock:
            return {"version": __version__,
                    "nodes": list(self.nodes.values()),
                    "reports": self.reports[-100:]}


_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>RFHound hub</title><meta http-equiv=refresh content=5>
<style>body{{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:2rem}}
h1{{color:#4fd1c5}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #2a3140;padding:.4rem .6rem;text-align:left}}
th{{color:#4fd1c5}}</style></head><body>
<h1>RFHound hub</h1><p>{nodes} node(s) · {reports} recent report(s) · auto-refresh 5s</p>
<h3>Nodes</h3>
<table><tr><th>Node</th><th>Name</th><th>Location</th><th>Last seen (s ago)</th></tr>
{node_rows}</table>
<h3>Recent reports</h3><table><tr><th>Node</th><th>Kind</th><th>Summary</th></tr>{report_rows}</table>
</body></html>"""


def make_hub_handler(state: HubState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"RFHoundHub/{__version__}"

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authed(self) -> bool:
            if not state.token:
                return True
            return self.headers.get("Authorization", "") == f"Bearer {state.token}"

        def _read(self) -> dict:
            n = int(self.headers.get("Content-Length", 0))
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode())
            except (json.JSONDecodeError, ValueError):
                return {}

        def do_GET(self):
            if self.path.startswith("/api/hub/state"):
                return self._json(state.snapshot())
            if self.path in ("/", "/index.html"):
                snap = state.snapshot()
                now = time.time()
                node_rows = "".join(
                    f"<tr><td>{n['node_id']}</td><td>{n['name']}</td>"
                    f"<td>{n['location']}</td><td>{int(now-n['last_seen'])}</td></tr>"
                    for n in snap["nodes"]) or "<tr><td colspan=4>none</td></tr>"
                report_rows = "".join(
                    f"<tr><td>{r['node_id']}</td><td>{r['kind']}</td>"
                    f"<td>{str(r['data'])[:80]}</td></tr>"
                    for r in reversed(snap["reports"][-20:])) or "<tr><td colspan=3>none</td></tr>"
                body = _PAGE.format(nodes=len(snap["nodes"]), reports=len(snap["reports"]),
                                    node_rows=node_rows, report_rows=report_rows).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            body = self._read()
            if self.path.startswith("/api/hub/register"):
                if not body.get("node_id"):
                    return self._json({"error": "node_id required"}, 400)
                return self._json(state.register(body["node_id"], body.get("name", ""),
                                                 body.get("location", "")))
            if self.path.startswith("/api/hub/report"):
                if not body.get("node_id") or not body.get("kind"):
                    return self._json({"error": "node_id and kind required"}, 400)
                return self._json(state.add_report(body["node_id"], body["kind"],
                                                   body.get("data")))
            return self._json({"error": "not found"}, 404)

    return Handler


def serve_hub(*, host: str = "127.0.0.1", port: int = 8787, token: str = "") -> None:
    state = HubState(token=token)
    httpd = ThreadingHTTPServer((host, port), make_hub_handler(state))
    actual = httpd.server_address[1]
    console.success(f"RFHound hub on http://{host}:{actual}")
    console.print_(f"  nodes report to POST /api/hub/report  ·  {'token required' if token else 'no auth'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.warn("Hub shutting down.")
    finally:
        httpd.server_close()
