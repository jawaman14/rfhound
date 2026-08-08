import builtins
import json

import pytest

from rfhound import cli


def run(argv):
    return cli.main(argv)


def test_decode_eob_and_track_wiring(tmp_path, monkeypatch):
    import argparse
    from rfhound.config import Config
    from rfhound.modules import sigint, sightings
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def fake_run(recipe, cfg, *, freq_hz, seconds, on_line=None, dry_run=False):
        lines = ['{"icao":"ABC123"}', '{"icao":"DEF456"}']
        for ln in lines:
            if on_line:
                on_line(ln)
        return lines

    monkeypatch.setattr(cli.decode_mod, "run_decoder", fake_run)
    args = argparse.Namespace(decode_cmd="run", recipe="adsb", freq=None, seconds=1,
                              track=True, eob=True, dry_run=False)
    assert cli.cmd_decode(args, Config(simulate_mode=True)) == 0
    emitters = sigint.EmitterCatalog().list()
    assert any(round(e.freq_mhz) == 1090 for e in emitters)  # channel in the EOB
    ids = {s.id for s in sightings.SightingsStore().list()}
    assert {"ABC123", "DEF456"} <= ids                        # IDs tracked


def test_config_wizard_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    answers = iter([str(tmp_path / "caps"), "10", "24", "20", "y", "n", "y", "n"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    rc = run(["config", "wizard"])
    assert rc == 0
    from rfhound.config import load_config
    cfg = load_config()
    assert cfg.output_dir == str(tmp_path / "caps")
    assert cfg.sample_rate == 10_000_000
    assert cfg.lna_gain == 24
    assert cfg.amp_enable is True
    assert cfg.simulate_mode is True


@pytest.mark.parametrize("argv", [
    ["doctor", "--json"],
    ["at", "433.92", "--json"],
    ["tune", "adsb", "--json"],
    ["classify", "1090", "--json"],
    ["sigint", "gnss", "--simulate", "spoofing", "--static", "--json"],
    ["sigint", "gnss", "--simulate", "nominal", "--json"],
])
def test_json_output_is_parseable(argv, capsys):
    # Guards against the console re-wrapping JSON to terminal width (which
    # injected mid-string newlines and produced invalid JSON).
    run(argv)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed is not None


def test_gnss_json_reports_spoofing(capsys):
    rc = run(["sigint", "gnss", "--simulate", "spoofing", "--static", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "spoofing"
    assert rc == 1  # non-nominal => non-zero exit for scripting


def test_version_exits_zero(capsys):
    try:
        run(["--version"])
    except SystemExit as e:
        assert e.code == 0


def test_setup_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    rc = run(["setup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Next steps" in out
    # It should have written a config file.
    assert (tmp_path / "rfhound" / "config.json").exists()


def test_bands_list(capsys):
    rc = run(["bands"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ADS-B" in out or "ISM" in out


def test_bands_filter_category(capsys):
    rc = run(["bands", "--category", "aviation"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ADS-B" in out


def test_sweep_simulate(capsys):
    rc = run(["sweep", "433", "435", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Spectrum" in out


def test_sweep_start_after_stop_rejected(capsys):
    rc = run(["sweep", "440", "430", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "must be below" in out


def test_sweep_out_of_range_rejected(capsys):
    rc = run(["sweep", "-5", "10", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "outside the HackRF range" in out


def test_classify_out_of_range_rejected(capsys):
    rc = run(["classify", "-100"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "outside the HackRF range" in out


def test_capture_nonpositive_seconds_rejected(capsys):
    rc = run(["capture", "433", "-3", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "must be positive" in out


def test_recon_simulate_with_report(tmp_path, capsys):
    report = tmp_path / "rep.md"
    rc = run(["recon", "--simulate", "--report", str(report)])
    assert rc == 0
    assert report.exists()


def test_decode_list(capsys):
    rc = run(["decode", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "rtl433" in out


def test_decode_run_dry(capsys):
    rc = run(["decode", "run", "adsb", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dump1090" in out


def test_replay_blocked_by_default(tmp_path, capsys):
    # A non-existent file still shouldn't transmit; expect a non-zero rc.
    rc = run(["replay", str(tmp_path / "nope.iq"), "--authorized", "--dry-run"])
    assert rc != 0


def test_tx_status(capsys):
    rc = run(["tx", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Transmit" in out
