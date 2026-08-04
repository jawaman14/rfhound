import builtins

from rfhound import cli
from rfhound import automation_menu
from rfhound.config import Config


def run(argv):
    return cli.main(argv)


def test_automate_add_list_once_remove(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["automate", "add", "watch", "monitor", "--start", "433",
                "--stop", "435", "--interval", "30"]) == 0
    capsys.readouterr()
    assert run(["automate", "list"]) == 0
    assert "watch" in capsys.readouterr().out

    assert run(["automate", "once", "watch", "--simulate"]) == 0
    out = capsys.readouterr().out
    assert "watch" in out

    assert run(["automate", "disable", "watch"]) == 0
    assert run(["automate", "remove", "watch"]) == 0


def test_automate_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["automate", "list"]) == 0
    assert "No automations" in capsys.readouterr().out


def test_automation_menu_add_and_quit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    answers = iter([
        "2",            # Add
        "nightwatch",   # name
        "drone",        # task
        "45",           # interval
        "threat",       # alert_on
        "",             # webhook
        "7",            # quit
    ])
    monkeypatch.setattr(builtins, "input", lambda *a: next(answers, "7"))
    rc = automation_menu.run_automation_menu(Config(simulate_mode=True))
    assert rc == 0
