"""The RFHound copilot: turns natural language into safe RFHound actions.

Provider-agnostic. Supports:
  * "anthropic" — the Claude Messages API (needs ANTHROPIC_API_KEY)
  * "local"     — any OpenAI-compatible endpoint (Ollama, llama.cpp, vLLM…)
  * "offline"   — a no-network keyword planner (default when no provider set),
                  so the copilot is demoable/testable without any model.

Whatever the provider, the model can only invoke the receive-and-analyse actions
in ``llm.actions`` — it cannot transmit or run code.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field

from ..config import Config
from . import actions as A

SYSTEM_PROMPT = (
    "You are the RFHound copilot, an assistant for a defensive HackRF SDR toolkit. "
    "You help with RF situational awareness: spectrum sweeps, recon, identifying "
    "bands, running detectors (jamming, spoofing, drones, rogue base stations, "
    "replay, frequency hopping), and giving defensive response guidance. "
    "You can ONLY call the provided tools, which are all receive-and-analyse. You "
    "cannot transmit, replay, or execute code, and you must never advise illegal "
    "transmission (jamming, spoofing). Prefer calling a tool over guessing. When "
    "hardware is absent, tools run in simulate mode; say so."
)


@dataclass
class AgentResult:
    text: str
    actions_run: list = field(default_factory=list)
    provider: str = "offline"


# --------------------------------------------------------------------------- #
# Offline keyword planner (no network)
# --------------------------------------------------------------------------- #
def _offline_plan(user: str) -> tuple[str, dict] | None:
    u = user.lower()
    if "imsi" in u or "base station" in u or "stingray" in u or "cell" in u:
        return "imsi_catcher_check", {"simulate": True}
    if "drone" in u or "uas" in u or "uav" in u:
        return "drone_scan", {"simulate": True}
    if "spoof" in u and "ais" in u:
        return "spoof_check", {"protocol": "ais", "simulate": True}
    if "spoof" in u or "adsb" in u or "aircraft" in u:
        return "spoof_check", {"protocol": "adsb", "simulate": True}
    if "hop" in u:
        return "hop_detect", {"simulate": True}
    if "recon" in u or "survey" in u or "around" in u:
        return "recon", {"simulate": True}
    if "decoder" in u or "decode" in u:
        return "list_decoders", {}
    if "respond" in u or "playbook" in u or "what do i do" in u:
        for t in ("jamming", "gps_spoof", "adsb_spoof", "ais_spoof", "drone",
                  "rogue_emitter", "replay"):
            if t.split("_")[0] in u:
                return "respond", {"threat": t}
        return "respond", {"threat": "jamming"}
    # "what's at 1090 MHz?" / "identify 433.92" → find_band on the number found.
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mhz|m)?", u)
    if m and ("at " in u or "mhz" in u or "identif" in u or "what" in u):
        return "find_band", {"freq_mhz": float(m.group(1))}
    if "band" in u or "frequency" in u:
        return "list_bands", {}
    if "status" in u:
        return "status", {}
    return None


def _offline(user: str, cfg: Config) -> AgentResult:
    plan = _offline_plan(user)
    if not plan:
        return AgentResult(
            "Offline copilot: try asking about a sweep, recon, drones, spoofing, "
            "IMSI catchers, hopping, decoders, or a response playbook.",
            provider="offline")
    name, params = plan
    result = A.run_action(name, cfg, params)
    return AgentResult(
        f"Ran `{name}` → {json.dumps(result)[:800]}",
        actions_run=[{"action": name, "params": params, "result": result}],
        provider="offline")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _post_json(url: str, headers: dict, payload: dict, timeout: float = 60) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------------------- #
# Anthropic (Claude) provider — tool-use loop
# --------------------------------------------------------------------------- #
def _anthropic(user: str, cfg: Config, *, max_steps: int = 5) -> AgentResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    model = cfg.llm_model or "claude-sonnet-5"
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    tools = A.tool_schemas("anthropic")
    messages = [{"role": "user", "content": user}]
    ran = []
    for _ in range(max_steps):
        payload = {"model": model, "max_tokens": 1024, "system": SYSTEM_PROMPT,
                   "tools": tools, "messages": messages}
        resp = _post_json(url, headers, payload)
        content = resp.get("content", [])
        tool_uses = [c for c in content if c.get("type") == "tool_use"]
        if not tool_uses:
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            return AgentResult(text.strip(), actions_run=ran, provider="anthropic")
        messages.append({"role": "assistant", "content": content})
        results = []
        for tu in tool_uses:
            out = A.run_action(tu["name"], cfg, tu.get("input", {}))
            ran.append({"action": tu["name"], "params": tu.get("input", {}), "result": out})
            results.append({"type": "tool_result", "tool_use_id": tu["id"],
                            "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})
    return AgentResult("(stopped after max steps)", actions_run=ran, provider="anthropic")


# --------------------------------------------------------------------------- #
# Local / OpenAI-compatible provider — tool-call loop
# --------------------------------------------------------------------------- #
def _local(user: str, cfg: Config, *, max_steps: int = 5) -> AgentResult:
    base = (cfg.llm_base_url or os.environ.get("RFHOUND_LLM_BASE_URL")
            or "http://localhost:11434/v1").rstrip("/")
    model = cfg.llm_model or "llama3.1"
    url = f"{base}/chat/completions"
    key = os.environ.get("RFHOUND_LLM_API_KEY", "not-needed")
    headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
    tools = A.tool_schemas("openai")
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user}]
    ran = []
    for _ in range(max_steps):
        payload = {"model": model, "messages": messages, "tools": tools}
        resp = _post_json(url, headers, payload)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return AgentResult((msg.get("content") or "").strip(), actions_run=ran,
                               provider="local")
        messages.append(msg)
        for c in calls:
            fn = c["function"]
            args = fn.get("arguments") or "{}"
            params = json.loads(args) if isinstance(args, str) else args
            out = A.run_action(fn["name"], cfg, params)
            ran.append({"action": fn["name"], "params": params, "result": out})
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""),
                             "content": json.dumps(out)})
    return AgentResult("(stopped after max steps)", actions_run=ran, provider="local")


class Copilot:
    """Drive RFHound with natural language, safely."""

    def __init__(self, cfg: Config, provider: str | None = None):
        self.cfg = cfg
        self.provider = (provider or cfg.llm_provider or "offline").lower()

    def ask(self, user: str) -> AgentResult:
        if self.provider == "anthropic":
            return _anthropic(user, self.cfg)
        if self.provider == "local":
            return _local(user, self.cfg)
        return _offline(user, self.cfg)
