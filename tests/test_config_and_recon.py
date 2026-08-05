import json

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
