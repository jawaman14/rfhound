"""The safe action registry the LLM copilot is allowed to call.

Every action here is receive-and-analyse. There is deliberately **no** transmit,
replay, capture, tx-enable, or shell/eval action — the model physically cannot
key the radio or run code through this surface. The only "authoring" action,
``draft_mod``, writes to a *pending* directory for human review and never loads
or executes the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .. import bandplan, device
from ..config import Config
from ..modules import cellular as cellular_mod
from ..modules import decode as decode_mod
from ..modules import intel as intel_mod
from ..modules import recon as recon_mod
from ..modules import response as response_mod
from ..modules import sweep as sweep_mod
from ..plugins import mods_dir


@dataclass
class Action:
    name: str
    description: str
    params: dict           # {param: "type: description"}
    handler: Callable[[Config, dict], Any]


def _sim(cfg: Config, params: dict) -> bool:
    """Simulate if explicitly asked, globally configured, or no hardware present."""
    if params.get("simulate") or getattr(cfg, "simulate_mode", False):
        return True
    return not device.is_present()


def _status(cfg: Config, p: dict) -> dict:
    return {"device_present": device.is_present(), "tx_enabled": cfg.tx_enabled}


def _list_bands(cfg: Config, p: dict) -> dict:
    cat = p.get("category")
    bands = bandplan.bands_by_category(cat) if cat else bandplan.BANDS
    return {"bands": [{"name": b.name, "low_mhz": b.low_hz / 1e6,
                       "high_mhz": b.high_hz / 1e6, "category": b.category,
                       "decoder": b.decoder} for b in bands]}


def _find_band(cfg: Config, p: dict) -> dict:
    b = bandplan.find_band(int(float(p["freq_mhz"]) * 1e6))
    return {"band": None if not b else {"name": b.name, "category": b.category,
            "description": b.description, "decoder": b.decoder}}


def _sweep(cfg: Config, p: dict) -> dict:
    r = sweep_mod.sweep(cfg, float(p["start_mhz"]), float(p["stop_mhz"]), simulate=_sim(cfg, p))
    return {"simulated": r.simulated, "noise_floor_db": r.noise_floor_db,
            "peaks": [{"freq_mhz": round(pk.freq_mhz, 4), "power_db": pk.power_db,
                       "band": pk.band.name if pk.band else None} for pk in r.peaks[:15]]}


def _recon(cfg: Config, p: dict) -> dict:
    rep = recon_mod.run_recon(cfg, simulate=_sim(cfg, p), progress=False)
    return {"simulated": rep.simulated, "active": len(rep.active_findings),
            "findings": [{"band": f.band.name, "active": f.active, "peaks": len(f.peaks)}
                         for f in rep.findings]}


def _list_decoders(cfg: Config, p: dict) -> dict:
    return {"recipes": [{"id": r.id, "name": r.name, "category": r.category}
                        for r in decode_mod.list_recipes()]}


def _drone(cfg: Config, p: dict) -> dict:
    hits = intel_mod.drone_scan(cfg, simulate=_sim(cfg, p))
    return {"hits": [{"band": h.band, "freq_mhz": h.freq_mhz,
                      "confidence": h.confidence} for h in hits]}


def _spoof(cfg: Config, p: dict) -> dict:
    proto = p.get("protocol", "adsb")
    sim = _sim(cfg, p)
    if proto == "adsb":
        msgs = intel_mod.simulate_adsb_messages() if sim else p.get("messages", [])
        f = intel_mod.detect_adsb_spoofing(msgs)
    else:
        msgs = intel_mod.simulate_ais_messages() if sim else p.get("messages", [])
        f = intel_mod.detect_ais_spoofing(msgs)
    return {"protocol": proto, "findings": [{"id": x.entity_id, "kind": x.kind} for x in f]}


def _imsi(cfg: Config, p: dict) -> dict:
    obs = cellular_mod.simulate_observations() if _sim(cfg, p) else []
    alerts = cellular_mod.detect_rogue_bts(obs)
    return {"score": cellular_mod.score(alerts),
            "alerts": [{"indicator": a.indicator, "severity": a.severity} for a in alerts]}


def _hop(cfg: Config, p: dict) -> dict:
    slices = intel_mod.simulate_hopping_slices(hopping=True) if _sim(cfg, p) else p.get("slices", [])
    r = intel_mod.detect_frequency_hopping(slices)
    return {"hopping_suspected": r.hopping_suspected, "detail": r.detail}


def _respond(cfg: Config, p: dict) -> dict:
    pb = response_mod.get_playbook(p["threat"])
    if not pb:
        return {"error": f"unknown threat; options: {response_mod.list_threats()}"}
    return {"threat": pb.threat, "immediate": pb.immediate, "mitigations": pb.mitigations,
            "escalation": pb.escalation}


def _draft_mod(cfg: Config, p: dict) -> dict:
    """Write proposed mod code to mods/pending/ for HUMAN review. Never loaded."""
    name = "".join(c for c in p.get("name", "draft") if c.isalnum() or c in "_-") or "draft"
    pending = mods_dir() / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    path = pending / f"{name}.py"
    header = ("# DRAFT mod proposed by the LLM copilot — REVIEW before moving to mods/\n"
              f"# {p.get('description', '')}\n")
    path.write_text(header + str(p.get("code", "")))
    return {"drafted": str(path), "note": "Saved to pending/ for human review; NOT loaded or executed."}


ACTIONS: dict[str, Action] = {
    "status": Action("status", "Get device/tx status.", {}, _status),
    "list_bands": Action("list_bands", "List known bands, optionally by category.",
                         {"category": "string?: e.g. ism, aviation"}, _list_bands),
    "find_band": Action("find_band", "Identify the band at a frequency.",
                        {"freq_mhz": "number: frequency in MHz"}, _find_band),
    "sweep": Action("sweep", "Sweep a spectrum range and return peaks.",
                    {"start_mhz": "number", "stop_mhz": "number", "simulate": "bool?"}, _sweep),
    "recon": Action("recon", "Survey high-value bands for activity.",
                    {"simulate": "bool?"}, _recon),
    "list_decoders": Action("list_decoders", "List available decoder recipes.", {}, _list_decoders),
    "drone_scan": Action("drone_scan", "Counter-UAS scan of drone bands.",
                         {"simulate": "bool?"}, _drone),
    "spoof_check": Action("spoof_check", "Detect ADS-B/AIS spoofing.",
                          {"protocol": "string: adsb|ais", "simulate": "bool?"}, _spoof),
    "imsi_catcher_check": Action("imsi_catcher_check",
                                 "Detect rogue base station / IMSI-catcher indicators.",
                                 {"simulate": "bool?"}, _imsi),
    "hop_detect": Action("hop_detect", "Detect frequency-hopping emitters.",
                         {"simulate": "bool?"}, _hop),
    "respond": Action("respond", "Get the defensive playbook for a threat.",
                      {"threat": "string: jamming|gps_spoof|adsb_spoof|ais_spoof|drone|"
                                 "rogue_emitter|replay"}, _respond),
    "draft_mod": Action("draft_mod",
                        "Draft a mod (custom band/decoder/detector) to a pending "
                        "folder for HUMAN review. Never loaded or executed automatically.",
                        {"name": "string", "description": "string", "code": "string: python"},
                        _draft_mod),
}


def run_action(name: str, cfg: Config, params: dict | None = None) -> dict:
    if name not in ACTIONS:
        return {"error": f"unknown or disallowed action '{name}'"}
    try:
        result = ACTIONS[name].handler(cfg, params or {})
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:  # never let a bad call crash the agent loop
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_schemas(flavor: str = "anthropic") -> list[dict]:
    """Return tool/function schemas for the given API flavor."""
    tools = []
    for a in ACTIONS.values():
        props = {}
        required = []
        for pname, desc in a.params.items():
            optional = "?" in desc or "bool?" in desc
            ptype = "number" if desc.startswith("number") else "boolean" if "bool" in desc else "string"
            props[pname] = {"type": ptype, "description": desc}
            if not optional:
                required.append(pname)
        schema = {"type": "object", "properties": props, "required": required}
        if flavor == "anthropic":
            tools.append({"name": a.name, "description": a.description, "input_schema": schema})
        else:  # openai-compatible
            tools.append({"type": "function", "function": {
                "name": a.name, "description": a.description, "parameters": schema}})
    return tools
