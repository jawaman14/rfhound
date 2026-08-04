from rfhound import cli


def run(argv):
    return cli.main(argv)


def test_track_add_and_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert run(["track", "add", "adsb", "abc123", "--freq", "1090"]) == 0
    capsys.readouterr()
    assert run(["track", "list"]) == 0
    out = capsys.readouterr().out
    assert "abc123" in out and "adsb" in out


def test_track_show_and_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    run(["track", "add", "ais", "999", "--note", "ferry"])
    capsys.readouterr()
    assert run(["track", "show", "999"]) == 0
    assert "ferry" in capsys.readouterr().out
    assert run(["track", "clear", "--kind", "ais"]) == 0
    capsys.readouterr()
    run(["track", "list"])
    assert "No sightings" in capsys.readouterr().out


def test_device_default_info_no_hardware(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    rc = run(["device", "info"])
    # No HackRF present -> returns non-zero but must not crash.
    assert rc in (0, 1)


def test_noaa_apt_frequency_corrected():
    from rfhound.modules import decode
    r = decode.get_recipe("noaa_apt")
    assert r.default_freq_hz == 137_100_000
