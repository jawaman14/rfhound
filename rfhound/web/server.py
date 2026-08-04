"""RFHound web server: a browser dashboard + JSON REST API.

Built on the standard library (``http.server``) so it adds no dependencies and
runs anywhere Python does. It is **receive-and-analyse only** — there is
deliberately no transmit/replay endpoint, so exposing the dashboard never keys
the radio. Bind to localhost by default.

The REST API doubles as the integration surface for a SIEM / monitoring stack:
every panel in the UI is backed by a ``/api/...`` endpoint returning JSON.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .. import __version__, bandplan, console, device, proc
from ..config import Config, load_config
from ..modules import cellular as cellular_mod
from ..modules import classify as classify_mod
from ..modules import decode as decode_mod
from ..modules import intel as intel_mod
from ..modules import recon as recon_mod
from ..modules import sweep as sweep_mod
from ..modules import toolbox as toolbox_mod

_DASHBOARD = Path(__file__).with_name("dashboard.html")


# --------------------------------------------------------------------------- #
# JSON serialisers
# --------------------------------------------------------------------------- #
def _band_dict(b: bandplan.Band) -> dict:
    return {
        "name": b.name,
        "low_mhz": round(b.low_hz / 1e6, 4),
        "high_mhz": round(b.high_hz / 1e6, 4),
        "category": b.category,
        "region": b.region,
        "decoder": b.decoder,
        "description": b.description,
        "tags": list(b.tags),
    }


def status_dict(cfg: Config) -> dict:
    tools = [
        {"name": t.name, "installed": ok, "purpose": t.purpose}
        for t, ok, _ in proc.tool_status()
    ]
    dev = {"present": False}
    try:
        info = device.get_info()
        dev = {"present": True, "serial": info.serial, "firmware": info.firmware,
               "board": info.board_id}
    except Exception:
        pass
    return {
        "version": __version__,
        "rich": console.have_rich(),
        "device": dev,
        "tools": tools,
        "tx_enabled": cfg.tx_enabled,
        "hardware": {
            "amp_enable": cfg.amp_enable,
            "antenna_power": cfg.antenna_power,
            "lna_gain": cfg.lna_gain,
            "vga_gain": cfg.vga_gain,
            "sample_rate": cfg.sample_rate,
            "device_serial": cfg.device_serial or None,
        },
    }


def sweep_dict(cfg: Config, start_mhz: float, stop_mhz: float, *,
               simulate: bool, width: int = 256) -> dict:
    result = sweep_mod.sweep(cfg, start_mhz, stop_mhz, simulate=simulate)
    # Downsample spectrum into `width` columns (peak-hold) for the waterfall.
    lo, hi = result.start_hz, result.stop_hz
    span = max(1, hi - lo)
    cols = [None] * width
    for b in result.bins:
        idx = min(width - 1, int((b.freq_hz - lo) / span * width))
        cols[idx] = b.power_db if cols[idx] is None else max(cols[idx], b.power_db)
    finite = [c for c in cols if c is not None]
    floor = result.noise_floor_db
    spectrum = [floor if c is None else round(c, 1) for c in cols]
    itu = bandplan.itu_band((lo + hi) // 2)
    return {
        "start_mhz": lo / 1e6,
        "stop_mhz": hi / 1e6,
        "itu_band": itu[0] if itu else None,
        "itu_label": bandplan.itu_label((lo + hi) // 2),
        "noise_floor_db": floor,
        "min_db": round(min(finite), 1) if finite else floor,
        "max_db": round(max(finite), 1) if finite else floor,
        "spectrum": spectrum,
        "simulated": result.simulated,
        "peaks": [
            _peak_dict(result, p) for p in result.peaks[:25]
        ],
    }


def _peak_dict(result, p) -> dict:
    bw = classify_mod.estimate_bandwidth_khz(result, p.freq_hz)
    guess = classify_mod.classify(p.freq_mhz, bandwidth_khz=bw)[0]
    return {"freq_mhz": round(p.freq_mhz, 4), "power_db": p.power_db,
            "band": p.band.name if p.band else None,
            "decoder": (p.band.decoder if p.band else None) or guess.decoder,
            "bandwidth_khz": bw,
            "guess": guess.name, "confidence": guess.likelihood}


def recon_dict(cfg: Config, *, simulate: bool) -> dict:
    report = recon_mod.run_recon(cfg, simulate=simulate, progress=False)
    findings = []
    for f in report.findings:
        top = max(f.peaks, key=lambda p: p.power_db) if f.peaks else None
        findings.append({
            "band": f.band.name,
            "category": f.band.category,
            "active": f.active,
            "peaks": len(f.peaks),
            "strongest_mhz": round(top.freq_mhz, 4) if top else None,
            "strongest_db": top.power_db if top else None,
            "decoder": f.band.decoder,
        })
    return {"simulated": report.simulated, "findings": findings,
            "active": len(report.active_findings), "total": len(report.findings)}


def drone_dict(cfg: Config, *, simulate: bool) -> dict:
    hits = intel_mod.drone_scan(cfg, simulate=simulate)
    return {"simulated": simulate, "hits": [
        {"band": h.band, "freq_mhz": h.freq_mhz, "power_db": h.power_db,
         "confidence": h.confidence} for h in hits]}


def spoof_dict(protocol: str, *, simulate: bool, messages=None) -> dict:
    if protocol == "adsb":
        msgs = messages or (intel_mod.simulate_adsb_messages() if simulate else [])
        findings = intel_mod.detect_adsb_spoofing(msgs)
    else:
        msgs = messages or (intel_mod.simulate_ais_messages() if simulate else [])
        findings = intel_mod.detect_ais_spoofing(msgs)
    return {"protocol": protocol, "simulated": simulate, "findings": [
        {"id": f.entity_id, "kind": f.kind, "detail": f.detail, "severity": f.severity}
        for f in findings]}


def imsi_dict(*, simulate: bool) -> dict:
    obs = cellular_mod.simulate_observations() if simulate else []
    alerts = cellular_mod.detect_rogue_bts(obs)
    return {"simulated": simulate, "score": cellular_mod.score(alerts),
            "alerts": [{"cid": a.cid, "indicator": a.indicator, "detail": a.detail,
                        "severity": a.severity} for a in alerts]}


def hop_dict(*, simulate: bool) -> dict:
    slices = intel_mod.simulate_hopping_slices(hopping=True) if simulate else []
    r = intel_mod.detect_frequency_hopping(slices)
    return {"simulated": simulate, "hopping_suspected": r.hopping_suspected,
            "distinct": r.distinct_freqs, "detail": r.detail}


def at_dict(freq_mhz: float) -> dict:
    tb = toolbox_mod.at_frequency(freq_mhz)
    if not tb:
        return {"found": False, "freq_mhz": freq_mhz}
    return {"found": True, "freq_mhz": freq_mhz, "band": tb.band.name,
            "category": tb.band.category, "description": tb.band.description,
            "range_mhz": [tb.band.low_hz / 1e6, tb.band.high_hz / 1e6],
            "decoders": tb.decoders, "detectors": tb.detectors,
            "gnuradio": tb.gnuradio, "commands": tb.commands}


def decoders_dict() -> dict:
    out = []
    for r in decode_mod.list_recipes():
        available, _ = decode_mod.check_recipe(r)
        out.append({"id": r.id, "name": r.name, "category": r.category,
                    "default_mhz": round(r.default_freq_hz / 1e6, 3),
                    "ready": available, "note": r.note})
    return {"recipes": out}


# --------------------------------------------------------------------------- #
# App state + request routing
# --------------------------------------------------------------------------- #
class AppState:
    def __init__(self, cfg: Config, *, force_simulate: bool = False):
        self.cfg = cfg
        self.force_simulate = force_simulate

    def wants_simulate(self, qs: dict) -> bool:
        if self.force_simulate:
            return True
        val = qs.get("simulate", ["0"])[0]
        return val in ("1", "true", "yes")


def build_app_state(cfg: Config | None = None, *, force_simulate: bool = False) -> AppState:
    return AppState(cfg or load_config(), force_simulate=force_simulate)


def _make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"RFHound/{__version__}"

        def log_message(self, *args):  # keep the console quiet
            pass

        def _send_json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self):
            try:
                body = _DASHBOARD.read_bytes()
            except OSError:
                body = b"<h1>RFHound</h1><p>dashboard.html missing</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            sim = state.wants_simulate(qs)
            cfg = state.cfg
            try:
                if path in ("/", "/index.html"):
                    return self._send_html()
                if path == "/api/version":
                    return self._send_json({"version": __version__})
                if path == "/api/status":
                    return self._send_json(status_dict(cfg))
                if path == "/api/bands":
                    return self._send_json({"bands": [_band_dict(b) for b in bandplan.BANDS]})
                if path == "/api/decoders":
                    return self._send_json(decoders_dict())
                if path == "/api/bookmarks":
                    return self._send_json({"bookmarks": cfg.bookmarks})
                if path == "/api/sightings":
                    from ..modules import sightings as sightings_mod
                    store = sightings_mod.SightingsStore()
                    return self._send_json({"sightings": [
                        {"kind": s.kind, "id": s.id, "count": s.count,
                         "freq_mhz": s.freq_mhz, "last_seen": s.last_seen}
                        for s in store.list()[:200]]})
                if path == "/api/sweep":
                    start = float(qs.get("start", ["430"])[0])
                    stop = float(qs.get("stop", ["440"])[0])
                    return self._send_json(sweep_dict(cfg, start, stop, simulate=sim))
                if path == "/api/recon":
                    return self._send_json(recon_dict(cfg, simulate=sim))
                if path == "/api/defense/drone":
                    return self._send_json(drone_dict(cfg, simulate=sim))
                if path == "/api/defense/spoof/adsb":
                    return self._send_json(spoof_dict("adsb", simulate=sim))
                if path == "/api/defense/spoof/ais":
                    return self._send_json(spoof_dict("ais", simulate=sim))
                if path == "/api/defense/imsi":
                    return self._send_json(imsi_dict(simulate=sim))
                if path == "/api/defense/hop":
                    return self._send_json(hop_dict(simulate=sim))
                if path == "/api/at":
                    freq = float(qs.get("freq", ["100"])[0])
                    return self._send_json(at_dict(freq))
                if path == "/api/classify":
                    freq = float(qs.get("freq", ["100"])[0])
                    bw = qs.get("bw", [None])[0]
                    mod = qs.get("mod", [None])[0]
                    matches = classify_mod.classify(
                        freq, bandwidth_khz=float(bw) if bw else None, modulation=mod)
                    return self._send_json({"freq_mhz": freq, "matches": [
                        {"name": m.name, "likelihood": m.likelihood, "decoder": m.decoder,
                         "category": m.category} for m in matches[:8]]})
                return self._send_json({"error": "not found", "path": path}, code=404)
            except Exception as exc:  # never leak a stack trace to the client
                return self._send_json({"error": str(exc)}, code=500)

    return Handler


def serve(cfg: Config | None = None, *, host: str = "127.0.0.1", port: int = 8000,
          force_simulate: bool = False) -> None:
    """Start the dashboard/API server (blocking)."""
    state = build_app_state(cfg, force_simulate=force_simulate)
    handler = _make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    actual = httpd.server_address[1]
    console.success(f"RFHound dashboard on http://{host}:{actual}")
    console.print_("  REST API under /api/…  ·  receive-only  ·  Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.warn("Shutting down.")
    finally:
        httpd.server_close()
