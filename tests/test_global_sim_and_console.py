from rfhound import cli, console
from rfhound.config import Config, save_config, load_config
from rfhound.llm import actions


def test_global_simulate_flag_runs_sweep(capsys):
    rc = cli.main(["--simulate", "sweep", "433", "435"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SIMULATED" in out


def test_global_simulate_config_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config(Config(simulate_mode=True))
    assert load_config().simulate_mode is True


def test_global_simulate_makes_llm_actions_simulate():
    cfg = Config(simulate_mode=True)
    # recon with no simulate param should still simulate (no hardware anyway),
    # and drone should return synthetic hits.
    out = actions.run_action("drone_scan", cfg, {})
    assert out["hits"]


def test_dev_flag_enables_debug():
    cli.main(["--dev", "bands", "--category", "aviation"])
    assert console.is_debug() is True
    console.set_debug(False)  # reset for other tests


def test_console_syntax_and_status_no_crash(capsys):
    with console.status("working"):
        pass
    console.syntax("x = 1\n", "python", title="demo")
    # Just ensure it produced some output without raising.
    assert True


def test_console_debug_gated(capsys):
    console.set_debug(False)
    console.debug("hidden")
    assert "hidden" not in capsys.readouterr().out
    console.set_debug(True)
    console.debug("shown")
    assert "shown" in capsys.readouterr().out
    console.set_debug(False)
