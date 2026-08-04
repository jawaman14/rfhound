import builtins

from rfhound import ai_menu
from rfhound.config import Config


def _feed(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda *a: next(it, "/quit"))


def test_ai_quit_immediately(monkeypatch):
    _feed(monkeypatch, ["/quit"])
    assert ai_menu.run_ai_menu(Config(), provider="offline") == 0


def test_ai_runs_action_offline(monkeypatch, capsys):
    _feed(monkeypatch, ["scan for drones", "/quit"])
    ai_menu.run_ai_menu(Config(simulate_mode=True), provider="offline")
    out = capsys.readouterr().out
    assert "drone_scan" in out


def test_ai_actions_command(monkeypatch, capsys):
    _feed(monkeypatch, ["/actions", "/quit"])
    ai_menu.run_ai_menu(Config(), provider="offline")
    out = capsys.readouterr().out
    assert "imsi_catcher_check" in out or "sweep" in out


def test_ai_provider_switch(monkeypatch, capsys):
    _feed(monkeypatch, ["/provider offline", "/quit"])
    ai_menu.run_ai_menu(Config(), provider="offline")
    assert "offline" in capsys.readouterr().out


def test_ai_help(monkeypatch, capsys):
    _feed(monkeypatch, ["/help", "/quit"])
    ai_menu.run_ai_menu(Config(), provider="offline")
    assert "Commands" in capsys.readouterr().out


def test_ai_provider_choices_exist():
    # The CLI exposes the ai command with the same providers as ask.
    from rfhound import cli
    parser = cli.build_parser()
    # Should parse without error.
    args = parser.parse_args(["ai", "--provider", "offline"])
    assert args.provider == "offline"
