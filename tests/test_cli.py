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


def test_config_set_get_persists(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "set", "lna_gain", "24"]) == 0
    capsys.readouterr()
    assert run(["config", "get", "lna_gain"]) == 0
    assert capsys.readouterr().out.strip() == "24"
    # A fresh load sees the persisted value.
    from rfhound.config import load_config
    assert load_config().lna_gain == 24


def test_config_set_rejects_invalid(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "set", "lna_gain", "25"]) == 2      # bad step
    assert run(["config", "set", "unknownkey", "1"]) == 2     # unknown


def test_config_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "list"]) == 0
    out = capsys.readouterr().out
    assert "scan_workers" in out and "lna_gain" in out


def test_doctor_self_test_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    rc = run(["doctor", "--self-test", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "checks" in data and "summary" in data
    assert rc in (0, 1)   # 1 only if a hard failure (unlikely in CI)


def test_sources_scan_parallel_simulated(capsys):
    rc = run(["--simulate", "sources", "--scan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "HackRF" in out and "Wi-Fi" in out and "BLE" in out


def test_contacts_table_simulated(capsys):
    rc = run(["--simulate", "contacts"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "BAW117" in out and "RED FALCON" in out


def test_contacts_json_and_export(tmp_path, capsys):
    gj = tmp_path / "c.geojson"
    kml = tmp_path / "c.kml"
    rc = run(["--simulate", "contacts", "--json", "--geojson", str(gj), "--kml", str(kml)])
    assert rc == 0
    capsys.readouterr()
    assert gj.exists() and kml.exists()
    fc = json.loads(gj.read_text())
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 4
    assert fc["features"][0]["properties"]["rssi_dbm"] == -62.0


def test_config_profile_cli_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "set", "vga_gain", "40"]) == 0
    assert run(["config", "profile", "save", "myp"]) == 0
    assert run(["config", "set", "vga_gain", "20"]) == 0
    assert run(["config", "profile", "load", "myp"]) == 0
    capsys.readouterr()
    assert run(["config", "get", "vga_gain"]) == 0
    assert capsys.readouterr().out.strip() == "40"
    assert run(["config", "profile", "list"]) == 0
    assert "myp" in capsys.readouterr().out


def test_contacts_near_distance(capsys):
    rc = run(["--simulate", "contacts", "--near", "51.5,-0.12", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    dists = [c["distance_km"] for c in data["contacts"]]
    assert dists == sorted(dists)          # nearest-first
    assert data["contacts"][0]["id"] == "abc123"


def test_contacts_near_bad_input():
    assert run(["--simulate", "contacts", "--near", "notacoord"]) == 2


def test_config_export_import_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "set", "lna_gain", "24"]) == 0
    out_file = tmp_path / "backup.json"
    assert run(["config", "export", str(out_file)]) == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["lna_gain"] == 24
    # Change, then import the backup to restore.
    assert run(["config", "set", "lna_gain", "8"]) == 0
    capsys.readouterr()
    assert run(["config", "import", str(out_file)]) == 0
    from rfhound.config import load_config
    assert load_config().lna_gain == 24


def test_config_export_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["config", "export"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "lna_gain" in data
    assert data["smtp_password"] == "" or data["smtp_password"] == "***REDACTED***"
