"""Automation engine: run RF tasks on a schedule, with triggers and alerting.

Define named automations (survey every 5 min, watch a band for jamming, scan for
drones, check for rogue base stations…). A runner executes each when it's due,
evaluates a trigger condition, and fires actions: log to a JSONL file, print an
alert, and/or POST to a webhook. All tasks are receive-and-analyse.

State lives in the config (``automations``) so it persists; the runner keeps
change-detection state in memory for the session.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .. import console
from ..config import Config, save_config
from . import cellular as cellular_mod
from . import intel as intel_mod
from . import recon as recon_mod
from . import sweep as sweep_mod
from .defense import monitor_interference


TASKS = ("recon", "monitor", "drone", "imsi", "hop", "sweep", "gnss", "emitters")
ALERT_MODES = ("threat", "always", "change")


def automations_log() -> Path:
    import os
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else (Path.home() / ".config")
    return root / "rfhound" / "automations.log"


@dataclass
class AutoResult:
    alert: bool
    summary: str
    data: dict = field(default_factory=dict)


def _norm(a: dict) -> dict:
    """Fill defaults for an automation dict."""
    return {
        "name": a.get("name", "auto"),
        "task": a.get("task", "recon"),
        "interval_s": int(a.get("interval_s", 60)),
        "params": a.get("params", {}),
        "alert_on": a.get("alert_on", "threat"),
        "webhook": a.get("webhook", ""),
        # Suppress repeat alerts for the same automation within this many seconds
        # (0 = alert every time). Keeps a standing condition from spamming.
        "alert_cooldown_s": int(a.get("alert_cooldown_s", 0)),
        "enabled": a.get("enabled", True),
    }


# --------------------------------------------------------------------------- #
# Task runners — each returns Auto­Result(alert, summary, data)
# --------------------------------------------------------------------------- #
def _task_recon(cfg, params, simulate, prev) -> AutoResult:
    rep = recon_mod.run_recon(cfg, simulate=simulate, progress=False)
    active = sorted(f.band.name for f in rep.active_findings)
    new = [b for b in active if b not in (prev or [])]
    return AutoResult(bool(new), f"{len(active)} active bands"
                      + (f"; NEW: {', '.join(new)}" if new else ""),
                      {"active": active, "new": new})


def _task_monitor(cfg, params, simulate, prev) -> AutoResult:
    lo = float(params.get("start", 433))
    hi = float(params.get("stop", 435))
    rep = monitor_interference(cfg, lo, hi, iterations=int(params.get("iterations", 8)),
                               simulate=simulate)
    return AutoResult(rep.jammed, "JAMMING detected" if rep.jammed else "band nominal",
                      {"alarms": rep.alarms})


def _task_drone(cfg, params, simulate, prev) -> AutoResult:
    hits = intel_mod.drone_scan(cfg, simulate=simulate)
    return AutoResult(bool(hits), f"{len(hits)} drone-band detection(s)",
                      {"hits": [h.band for h in hits]})


def _task_imsi(cfg, params, simulate, prev) -> AutoResult:
    obs = cellular_mod.simulate_observations() if simulate else []
    alerts = cellular_mod.detect_rogue_bts(obs)
    sc = cellular_mod.score(alerts)
    return AutoResult(bool(alerts), f"rogue-BTS likelihood {sc}/100",
                      {"score": sc, "indicators": [a.indicator for a in alerts]})


def _task_hop(cfg, params, simulate, prev) -> AutoResult:
    slices = intel_mod.simulate_hopping_slices(hopping=True) if simulate else []
    r = intel_mod.detect_frequency_hopping(slices)
    return AutoResult(r.hopping_suspected, r.detail, {})


def _task_sweep(cfg, params, simulate, prev) -> AutoResult:
    lo = float(params.get("start", 433))
    hi = float(params.get("stop", 435))
    result = sweep_mod.sweep(cfg, lo, hi, simulate=simulate)
    freqs = [round(p.freq_mhz, 2) for p in result.peaks]
    new = [f for f in freqs if f not in (prev or [])]
    return AutoResult(bool(new), f"{len(freqs)} peaks"
                      + (f"; NEW at {', '.join(map(str, new))} MHz" if new else ""),
                      {"peaks": freqs, "new": new})


def _task_gnss(cfg, params, simulate, prev) -> AutoResult:
    """GNSS integrity monitor — alert on jamming/spoofing indicators."""
    from . import gnss as gnss_mod
    obs = []
    f = params.get("file")
    if f:
        try:
            raw = json.loads(Path(f).read_text())
        except (OSError, ValueError):
            return AutoResult(False, "GNSS: could not read observations", {})
        obs = [gnss_mod.GnssObservation(
            t=float(o.get("t", 0.0)), lat=o.get("lat"), lon=o.get("lon"), alt=o.get("alt"),
            cn0=list(o.get("cn0", [])), elevations=list(o.get("elevations", [])),
            agc=o.get("agc"), num_sats=o.get("num_sats"), fix=bool(o.get("fix", True)))
            for o in raw]
    elif simulate:
        sim = {"nominal": gnss_mod.simulate_nominal, "jamming": gnss_mod.simulate_jamming,
               "spoofing": gnss_mod.simulate_spoofing}
        obs = sim.get(params.get("scenario", "nominal"), gnss_mod.simulate_nominal)()
    if not obs:
        return AutoResult(False, "GNSS: no observations (set params.file)", {})
    rep = gnss_mod.detect_gnss_interference(obs, static=bool(params.get("static", False)))
    return AutoResult(rep.status != "nominal", f"GNSS {rep.status} ({rep.confidence}%)",
                      {"status": rep.status, "findings": [x.indicator for x in rep.findings]})


def _task_emitters(cfg, params, simulate, prev) -> AutoResult:
    """Build the Electronic Order of Battle over time; alert on new emitters."""
    from . import sigint as sigint_mod
    from . import classify as classify_mod
    lo = float(params.get("start", 430))
    hi = float(params.get("stop", 440))
    result = sweep_mod.sweep(cfg, lo, hi, simulate=simulate)
    cat = sigint_mod.EmitterCatalog()
    seen_before = {round(e.freq_mhz, 3) for e in cat.list()}
    for p in result.peaks:
        bw = classify_mod.estimate_bandwidth_khz(result, p.freq_hz)
        g = classify_mod.classify(p.freq_mhz, bandwidth_khz=bw)[0]
        cat.ingest(p.freq_mhz, power_db=p.power_db, bandwidth_khz=bw, guess=g.name, save=False)
    cat.save()
    now_freqs = {round(p.freq_mhz, 3) for p in result.peaks}
    new = sorted(now_freqs - seen_before)
    return AutoResult(bool(new), f"{len(now_freqs)} emitter(s)"
                      + (f"; NEW: {', '.join(map(str, new))} MHz" if new else ""),
                      {"emitters": sorted(now_freqs), "new": new})


_RUNNERS = {
    "recon": _task_recon, "monitor": _task_monitor, "drone": _task_drone,
    "imsi": _task_imsi, "hop": _task_hop, "sweep": _task_sweep,
    "gnss": _task_gnss, "emitters": _task_emitters,
}


def run_task(cfg: Config, auto: dict, *, simulate: bool, prev=None) -> AutoResult:
    a = _norm(auto)
    runner = _RUNNERS.get(a["task"])
    if not runner:
        return AutoResult(False, f"unknown task '{a['task']}'")
    return runner(cfg, a["params"], simulate, prev)


def should_alert(auto: dict, result: AutoResult) -> bool:
    mode = _norm(auto)["alert_on"]
    if mode == "always":
        return True
    if mode == "change":
        return result.alert  # runners set .alert on "new"/change
    return result.alert       # "threat": runners set .alert on a detection


def _post_webhook(url: str, payload: dict) -> None:
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as exc:  # best-effort; never break the loop
        console.debug(f"webhook failed: {exc}")


def fire(cfg: Config, auto: dict, result: AutoResult, *, alerting: bool) -> dict:
    """Log the event and, if alerting, print + webhook. Returns the event dict."""
    a = _norm(auto)
    event = {"t": time.time(), "name": a["name"], "task": a["task"],
             "alert": alerting, "summary": result.summary, "data": result.data}
    log = automations_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(event) + "\n")
    # Logging + webhook only; callers handle console display.
    if alerting and a["webhook"]:
        _post_webhook(a["webhook"], event)
    return event


def run_due(cfg: Config, *, simulate: bool, state: dict, now: float | None = None,
            force: bool = False) -> list[dict]:
    """Run every enabled automation that is due; return the events fired."""
    now = now if now is not None else time.time()
    events = []
    for auto in cfg.automations:
        a = _norm(auto)
        if not a["enabled"]:
            continue
        last = state.get(a["name"], {}).get("last_run", 0)
        if not force and (now - last) < a["interval_s"]:
            continue
        prev_state = state.get(a["name"], {})
        prev = prev_state.get("prev")
        result = run_task(cfg, auto, simulate=simulate, prev=prev)
        alerting = should_alert(auto, result)
        # Re-alert cooldown: suppress a repeat alert within the window so a
        # standing condition alerts once, not every interval.
        last_alert = prev_state.get("last_alert", 0)
        cooldown = a["alert_cooldown_s"]
        if alerting and cooldown and (now - last_alert) < cooldown:
            alerting = False
        events.append(fire(cfg, auto, result, alerting=alerting))
        # Update change-detection + alert-cooldown state.
        prev_key = result.data.get("active") or result.data.get("peaks") or prev
        state[a["name"]] = {"last_run": now, "prev": prev_key,
                            "last_alert": now if alerting else last_alert}
    return events


def run_scheduler(cfg: Config, *, simulate: bool, tick_s: float = 2.0,
                  max_ticks: int | None = None) -> None:
    """Foreground scheduler loop (Ctrl-C to stop)."""
    if not cfg.automations:
        console.warn("No automations defined. Add one first (automation menu / "
                     "'rfhound automate add').")
        return
    console.success(f"Running {sum(1 for a in cfg.automations if _norm(a)['enabled'])} "
                    f"automation(s). Ctrl-C to stop. Log: {automations_log()}")
    state: dict = {}
    ticks = 0
    try:
        while max_ticks is None or ticks < max_ticks:
            for ev in run_due(cfg, simulate=simulate, state=state, force=(ticks == 0)):
                tag = "ALERT" if ev["alert"] else "ok"
                (console.error if ev["alert"] else console.info)(
                    f"{ev['name']} · {tag}: {ev['summary']}")
            ticks += 1
            time.sleep(tick_s)
    except KeyboardInterrupt:
        console.warn("Scheduler stopped.")


# --------------------------------------------------------------------------- #
# CRUD helpers (operate on cfg.automations)
# --------------------------------------------------------------------------- #
def add_automation(cfg: Config, name: str, task: str, *, interval_s: int = 60,
                   params: dict | None = None, alert_on: str = "threat",
                   webhook: str = "", alert_cooldown_s: int = 0,
                   persist: bool = True) -> dict:
    cfg.automations = [a for a in cfg.automations if a.get("name") != name]
    auto = {"name": name, "task": task, "interval_s": interval_s,
            "params": params or {}, "alert_on": alert_on, "webhook": webhook,
            "alert_cooldown_s": alert_cooldown_s, "enabled": True}
    cfg.automations.append(auto)
    if persist:
        save_config(cfg)
    return auto


def remove_automation(cfg: Config, name: str, *, persist: bool = True) -> bool:
    before = len(cfg.automations)
    cfg.automations = [a for a in cfg.automations if a.get("name") != name]
    if persist:
        save_config(cfg)
    return len(cfg.automations) < before


def set_enabled(cfg: Config, name: str, enabled: bool, *, persist: bool = True) -> bool:
    found = False
    for a in cfg.automations:
        if a.get("name") == name:
            a["enabled"] = enabled
            found = True
    if persist:
        save_config(cfg)
    return found
