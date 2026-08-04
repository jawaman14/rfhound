from rfhound import bandplan, cli
from rfhound.config import load_config


def test_itu_band_uhf():
    b = bandplan.itu_band(433_920_000)
    assert b is not None and b[0] == "UHF"


def test_itu_band_vhf():
    assert bandplan.itu_band(100_000_000)[0] == "VHF"


def test_itu_band_hf():
    assert bandplan.itu_band(14_000_000)[0] == "HF"


def test_itu_label_format():
    label = bandplan.itu_label(1_090_000_000)
    assert label.startswith("UHF")
    assert "MHz" in label or "GHz" in label


def test_itu_out_of_range():
    assert bandplan.itu_band(500_000_000_000) is None


def test_bookmark_add_list_remove(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli.main(["bookmark", "add", "myfob", "433.92", "--note", "garage"]) == 0
    assert load_config().bookmarks[0]["name"] == "myfob"

    capsys.readouterr()
    assert cli.main(["bookmark", "list"]) == 0
    out = capsys.readouterr().out
    assert "myfob" in out and "433.92" in out and "UHF" in out

    assert cli.main(["bookmark", "remove", "myfob"]) == 0
    assert load_config().bookmarks == []


def test_bookmark_add_replaces_same_name(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cli.main(["bookmark", "add", "x", "100"])
    cli.main(["bookmark", "add", "x", "200"])
    bms = load_config().bookmarks
    assert len(bms) == 1 and bms[0]["freq_mhz"] == 200
