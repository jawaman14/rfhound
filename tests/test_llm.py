from rfhound.config import Config
from rfhound.llm import actions, Copilot


def test_no_transmit_actions_exist():
    # The LLM surface must never be able to transmit / replay / capture / exec.
    forbidden = {"transmit", "replay", "tx", "capture", "jam", "spoof_transmit",
                 "exec", "shell", "run_code", "eval"}
    assert forbidden.isdisjoint(actions.ACTIONS.keys())


def test_actions_are_receive_analysis():
    expected = {"status", "list_bands", "find_band", "sweep", "recon",
                "list_decoders", "drone_scan", "spoof_check", "imsi_catcher_check",
                "hop_detect", "respond", "draft_mod"}
    assert expected <= set(actions.ACTIONS.keys())


def test_run_action_unknown_is_safe():
    out = actions.run_action("transmit", Config(), {})
    assert "error" in out


def test_run_action_recon_simulate():
    out = actions.run_action("recon", Config(), {"simulate": True})
    assert "findings" in out


def test_tool_schemas_anthropic_and_openai():
    a = actions.tool_schemas("anthropic")
    o = actions.tool_schemas("openai")
    assert a and all("input_schema" in t for t in a)
    assert o and all(t["type"] == "function" for t in o)


def test_draft_mod_writes_to_pending_not_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    out = actions.run_action("draft_mod", Config(),
                             {"name": "myidea", "description": "d", "code": "x=1"})
    assert "drafted" in out
    p = tmp_path / "rfhound" / "mods" / "pending" / "myidea.py"
    assert p.exists()
    # It must live under pending/, never directly in the loaded mods dir.
    assert "pending" in out["drafted"]


def test_offline_copilot_routes_to_imsi():
    r = Copilot(Config(), provider="offline").ask("check for an IMSI catcher nearby")
    assert r.provider == "offline"
    assert any(a["action"] == "imsi_catcher_check" for a in r.actions_run)


def test_offline_copilot_routes_to_drone():
    r = Copilot(Config(), provider="offline").ask("are there any drones around?")
    assert any(a["action"] == "drone_scan" for a in r.actions_run)


def test_offline_copilot_unknown_query():
    r = Copilot(Config(), provider="offline").ask("hello there")
    assert r.actions_run == []
