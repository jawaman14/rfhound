from rfhound import cli


def run(argv):
    return cli.main(argv)


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


def test_wifi_channels(capsys):
    rc = run(["wifi", "channels", "--band", "2.4"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "channel plan" in out.lower()


def test_wifi_survey_simulate(capsys):
    rc = run(["wifi", "survey", "--band", "2.4", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Wi-Fi" in out
    assert "Suggested channel" in out


def test_wifi_survey_both_default_simulate(capsys):
    rc = run(["--simulate", "wifi", "survey"])
    out = capsys.readouterr().out
    assert rc == 0
    # both bands surveyed
    assert "2.4 GHz" in out and "5 GHz" in out


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
