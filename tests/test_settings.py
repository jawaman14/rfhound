import time

import pytest

from rfhound import parallel, settings
from rfhound.config import Config
from rfhound.modules import diagnostics


# --- settings registry / coercion ---
def test_set_valid_int_with_step():
    cfg = Config()
    assert settings.set_value(cfg, "lna_gain", "24") == 24
    assert cfg.lna_gain == 24


def test_set_rejects_bad_step():
    with pytest.raises(ValueError):
        settings.set_value(Config(), "lna_gain", "25")   # not a multiple of 8


def test_set_rejects_out_of_range():
    with pytest.raises(ValueError):
        settings.set_value(Config(), "vga_gain", "99")   # max 62


def test_set_bool_parsing():
    cfg = Config()
    assert settings.set_value(cfg, "amp_enable", "yes") is True
    assert settings.set_value(cfg, "amp_enable", "off") is False
    with pytest.raises(ValueError):
        settings.set_value(cfg, "amp_enable", "maybe")


def test_set_choice_enforced():
    cfg = Config()
    assert settings.set_value(cfg, "llm_provider", "anthropic") == "anthropic"
    with pytest.raises(ValueError):
        settings.set_value(cfg, "llm_provider", "bogus")


def test_unknown_key_raises_keyerror():
    with pytest.raises(KeyError):
        settings.set_value(Config(), "nope", "1")


def test_current_snapshot_shape():
    snap = settings.current(Config())
    assert all({"key", "kind", "value", "help", "choices"} <= set(s) for s in snap)
    assert any(s["key"] == "scan_workers" for s in snap)


# --- parallel.run_jobs ---
def test_run_jobs_returns_all_results():
    res = parallel.run_jobs({"a": lambda: 1, "b": lambda: 2}, workers=2)
    assert res["a"].ok and res["a"].value == 1
    assert res["b"].ok and res["b"].value == 2


def test_run_jobs_isolates_exceptions():
    def boom():
        raise RuntimeError("kaboom")
    res = parallel.run_jobs({"good": lambda: 42, "bad": boom}, workers=2)
    assert res["good"].ok and res["good"].value == 42
    assert res["bad"].ok is False and "kaboom" in res["bad"].error


def test_run_jobs_empty():
    assert parallel.run_jobs({}) == {}


def test_run_jobs_actually_concurrent():
    # Three 0.15s sleeps should finish well under the 0.45s serial time.
    jobs = {f"j{i}": (lambda: time.sleep(0.15)) for i in range(3)}
    start = time.monotonic()
    parallel.run_jobs(jobs, workers=3)
    assert time.monotonic() - start < 0.4


# --- diagnostics ---
def test_run_diagnostics_has_core_checks():
    checks = diagnostics.run_diagnostics(Config(), deep=False)
    names = {c.name for c in checks}
    assert {"Python", "Config", "Output dir", "Disk space"} <= names
    assert all(c.status in ("ok", "warn", "fail") for c in checks)


def test_run_diagnostics_deep_probes_tools():
    checks = diagnostics.run_diagnostics(Config(), deep=True)
    names = {c.name for c in checks}
    assert "hackrf_sweep" in names   # probed even if absent (as a warn)


def test_summarize_counts_and_health():
    checks = [diagnostics.Check("a", "ok", ""), diagnostics.Check("b", "warn", ""),
              diagnostics.Check("c", "fail", "")]
    s = diagnostics.summarize(checks)
    assert s == {"ok": 1, "warn": 1, "fail": 1, "healthy": False}
    assert diagnostics.summarize([diagnostics.Check("a", "ok", "")])["healthy"] is True


def test_output_dir_check_fails_on_bad_path():
    cfg = Config(output_dir="/proc/nonexistent/cannot/create")
    checks = diagnostics.run_diagnostics(cfg, deep=False)
    outdir = [c for c in checks if c.name == "Output dir"][0]
    assert outdir.status == "fail" and outdir.hint


# --- profiles ---
def test_profile_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    settings.set_value(cfg, "lna_gain", 24)
    settings.set_value(cfg, "amp_enable", True)
    settings.save_profile(cfg, "airband")
    assert "airband" in settings.list_profiles()
    # Mutate, then restore from the profile.
    settings.set_value(cfg, "lna_gain", 8)
    settings.set_value(cfg, "amp_enable", False)
    applied = settings.load_profile(cfg, "airband")
    assert "lna_gain" in applied
    assert cfg.lna_gain == 24 and cfg.amp_enable is True


def test_profile_load_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        settings.load_profile(Config(), "ghost")


def test_profile_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings.save_profile(Config(), "tmp")
    assert settings.delete_profile("tmp") is True
    assert settings.delete_profile("tmp") is False        # already gone
    assert settings.list_profiles() == []


def test_profile_rejects_bad_name(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        settings.save_profile(Config(), "../escape")
