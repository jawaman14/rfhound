from rfhound import bandplan, plugins
from rfhound.modules import decode as decode_mod


SAMPLE = '''
NAME = "Test mod"
VERSION = "9.9"

def register(api):
    api.add_band(name="TESTBAND", low_mhz=100.0, high_mhz=101.0,
                 category="ism", description="test", tags=("test",))
    api.add_detector("t", lambda cfg: 1)
'''

BAD = '''
NAME = "Broken"
def register(api):
    raise RuntimeError("boom")
'''


def test_write_sample_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = plugins.write_sample_mod()
    assert path.exists()
    loaded = plugins.load_mods()
    assert any("Sample" in m.name for m in loaded)


def test_load_mod_registers_band(tmp_path):
    (tmp_path / "m.py").write_text(SAMPLE)
    n_before = len(bandplan.BANDS)
    loaded = plugins.load_mods(tmp_path)
    assert len(bandplan.BANDS) == n_before + 1
    assert loaded[0].name == "Test mod"
    assert loaded[0].version == "9.9"
    assert "TESTBAND" in loaded[0].bands
    assert "t" in loaded[0].detectors
    # cleanup so we don't leak into other tests
    bandplan.BANDS[:] = [b for b in bandplan.BANDS if b.name != "TESTBAND"]


def test_bad_mod_does_not_crash(tmp_path):
    (tmp_path / "bad.py").write_text(BAD)
    loaded = plugins.load_mods(tmp_path)
    assert loaded[0].error is not None
    assert "boom" in loaded[0].error


def test_empty_dir_returns_nothing(tmp_path):
    assert plugins.load_mods(tmp_path / "nope") == []
