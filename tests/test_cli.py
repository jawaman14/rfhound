import json

import pytest

from rfhound import cli


def run(argv):
    return cli.main(argv)


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
