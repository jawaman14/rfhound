import json

import pytest

from rfhound.config import Config, TxAllowRange, load_config, save_config
from rfhound.modules import recon as recon_mod
from rfhound.modules import report as report_mod


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config(lna_gain=24, tx_allow_ranges=[TxAllowRange(433_000_000, 434_800_000, "eu")])
    path = save_config(cfg)
    assert path.exists()
    loaded = load_config()
    assert loaded.lna_gain == 24
    assert loaded.tx_allow_ranges[0].note == "eu"


def test_config_ignores_unknown_keys():
    data = {"lna_gain": 8, "totally_unknown": 1}
    cfg = Config.from_dict(data)
    assert cfg.lna_gain == 8


def test_export_redacts_secrets_by_default():
    from rfhound.config import export_dict, REDACTED
    cfg = Config(smtp_password="hunter2", hub_token="tok", lna_gain=24)
    d = export_dict(cfg)
    assert d["smtp_password"] == REDACTED and d["hub_token"] == REDACTED
    assert d["lna_gain"] == 24
    full = export_dict(cfg, include_secrets=True)
    assert full["smtp_password"] == "hunter2"


def test_import_merge_skips_redacted_secret():
    from rfhound.config import merge_dict, REDACTED
    cfg = Config(smtp_password="original", lna_gain=8)
    applied = merge_dict(cfg, {"lna_gain": 24, "smtp_password": REDACTED, "vga_gain": 30})
    assert cfg.lna_gain == 24 and cfg.vga_gain == 30
    assert cfg.smtp_password == "original"          # redacted placeholder skipped
    assert "smtp_password" not in applied and "lna_gain" in applied


def test_import_merge_ignores_unknown_and_tx_ranges():
    from rfhound.config import merge_dict
    cfg = Config()
    applied = merge_dict(cfg, {"nope": 1, "tx_allow_ranges": [{"low_hz": 1, "high_hz": 2}],
                               "jurisdiction": "UK"})
    assert applied == ["jurisdiction"] and cfg.jurisdiction == "UK"
    assert cfg.tx_allow_ranges == []                # tx ranges never imported


def test_recon_simulated_produces_findings():
    cfg = Config()
    report = recon_mod.run_recon(cfg, simulate=True, progress=False)
    assert report.simulated
    assert report.findings
    # At least one high-value band should be "active" in simulation.
    assert report.active_findings


def test_report_markdown_and_html(tmp_path):
    cfg = Config()
    report = recon_mod.run_recon(cfg, simulate=True, progress=False)
    md = report_mod.to_markdown(report)
    assert "RFHound recon report" in md
    html = report_mod.to_html(report)
    assert "<html" in html
    out_md = report_mod.write_report(report, tmp_path / "r.md", fmt="md")
    out_html = report_mod.write_report(report, tmp_path / "r.html", fmt="html")
    assert out_md.exists() and out_html.exists()


def test_capture_simulate(tmp_path):
    from rfhound.modules import capture as capture_mod
    cfg = Config(output_dir=str(tmp_path))
    cap = capture_mod.capture_iq(cfg, 433.92, 1.0, simulate=True)
    assert cap.data_path.exists()
    assert cap.meta_path.exists()
    meta = json.loads(cap.meta_path.read_text())
    assert meta["captures"][0]["core:frequency"] == 433_920_000


def test_replay_dry_run_gated(tmp_path):
    from rfhound.modules import capture as capture_mod
    from rfhound.modules import replay as replay_mod
    from rfhound.exceptions import SafetyError
    cfg = Config(output_dir=str(tmp_path))
    cap = capture_mod.capture_iq(cfg, 433.92, 1.0, simulate=True)
    # Not authorized -> blocked even in dry run.
    try:
        replay_mod.replay(cfg, cap.data_path, authorized=True, dry_run=True)
        assert False, "should have raised (tx disabled)"
    except SafetyError:
        pass


def test_replay_duration_cap(tmp_path, monkeypatch):
    from rfhound.config import TxAllowRange
    from rfhound.modules import capture as capture_mod
    from rfhound.modules import replay as replay_mod
    from rfhound.exceptions import SafetyError
    from rfhound import safety
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config(output_dir=str(tmp_path), tx_max_seconds=2)
    cfg = safety.enable_tx(cfg, [TxAllowRange(433_000_000, 434_800_000)], persist=False)
    cap = capture_mod.capture_iq(cfg, 433.92, 5.0, simulate=True)  # 5s > 2s cap
    with pytest.raises(SafetyError) as exc:
        replay_mod.replay(cfg, cap.data_path, authorized=True, dry_run=False)
    assert "cap" in str(exc.value)
    # The block was audited.
    events = safety.read_tx_audit()
    assert events and events[-1]["outcome"] == "blocked"


def test_replay_dry_run_records_audit(tmp_path, monkeypatch):
    from rfhound.config import TxAllowRange
    from rfhound.modules import capture as capture_mod
    from rfhound.modules import replay as replay_mod
    from rfhound import safety
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config(output_dir=str(tmp_path))
    cfg = safety.enable_tx(cfg, [TxAllowRange(433_000_000, 434_800_000)], persist=False)
    cap = capture_mod.capture_iq(cfg, 433.92, 1.0, simulate=True)
    plan = replay_mod.replay(cfg, cap.data_path, authorized=True, dry_run=True)
    assert plan.protected is None
    events = safety.read_tx_audit()
    assert events and events[-1]["outcome"] == "dry-run"
