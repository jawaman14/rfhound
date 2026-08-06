"""Drive the interactive menu non-interactively by feeding stdin."""
import builtins

from rfhound import menu
from rfhound.config import Config


def _feed(monkeypatch, answers):
    it = iter(answers)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            return str(len(menu.MENU))  # fall through to Quit

    monkeypatch.setattr(builtins, "input", fake_input)


def test_menu_has_all_sections():
    labels = [m[0] for m in menu.MENU]
    for want in ["Recon", "Spectrum", "Identify", "Threat", "decoders",
                 "knowledge base", "Bookmarks", "dashboard", "doctor", "Quit"]:
        assert any(want.lower() in lbl.lower() for lbl in labels), want


def test_menu_quit_immediately(monkeypatch):
    _feed(monkeypatch, [str(len(menu.MENU))])
    assert menu.run_menu(Config()) == 0


def test_menu_identify_then_quit(monkeypatch, capsys):
    # 4 = Identify; enter 1090; then Quit.
    _feed(monkeypatch, ["4", "1090", str(len(menu.MENU))])
    menu.run_menu(Config(simulate_mode=True))
    out = capsys.readouterr().out
    assert "ADS-B" in out


def test_menu_bad_choice_recovers(monkeypatch, capsys):
    _feed(monkeypatch, ["zzz", str(len(menu.MENU))])
    assert menu.run_menu(Config()) == 0
    assert "valid number" in capsys.readouterr().out


def test_menu_threats_submenu(monkeypatch, capsys):
    # 5 = Threats; 4 = IMSI catcher; 7 = Back; Quit.
    _feed(monkeypatch, ["5", "4", "7", str(len(menu.MENU))])
    menu.run_menu(Config(simulate_mode=True))
    out = capsys.readouterr().out
    assert "Rogue-BTS" in out or "likelihood" in out
