import pytest

from rfhound.config import Config, TxAllowRange
from rfhound.exceptions import SafetyError
from rfhound import safety


def test_tx_blocked_without_authorized_flag():
    cfg = Config(tx_enabled=True, tx_consent_at="now",
                 tx_allow_ranges=[TxAllowRange(433_000_000, 434_800_000)])
    with pytest.raises(SafetyError):
        safety.authorize_tx(cfg, 433_920_000, authorized=False)


def test_tx_blocked_when_disabled():
    cfg = Config(tx_enabled=False)
    with pytest.raises(SafetyError):
        safety.authorize_tx(cfg, 433_920_000, authorized=True)


def test_tx_blocked_outside_allow_range():
    cfg = Config(tx_enabled=True, tx_consent_at="now",
                 tx_allow_ranges=[TxAllowRange(433_000_000, 434_800_000)])
    with pytest.raises(SafetyError):
        safety.authorize_tx(cfg, 915_000_000, authorized=True)


def test_tx_allowed_when_everything_satisfied():
    cfg = Config(tx_enabled=True, tx_consent_at="now",
                 tx_allow_ranges=[TxAllowRange(433_000_000, 434_800_000)])
    # Should not raise.
    safety.authorize_tx(cfg, 433_920_000, authorized=True)


def test_tx_blocked_outside_hardware_range():
    cfg = Config(tx_enabled=True, tx_consent_at="now",
                 tx_allow_ranges=[TxAllowRange(1_000_000, 6_000_000_000)])
    with pytest.raises(SafetyError):
        safety.authorize_tx(cfg, 7_000_000_000, authorized=True)


def test_enable_tx_requires_ranges():
    cfg = Config()
    with pytest.raises(SafetyError):
        safety.enable_tx(cfg, [], persist=False)


def test_enable_tx_rejects_out_of_hw_range():
    cfg = Config()
    with pytest.raises(SafetyError):
        safety.enable_tx(cfg, [TxAllowRange(1_000, 2_000)], persist=False)


def test_enable_tx_sets_consent_and_ranges():
    cfg = Config()
    cfg = safety.enable_tx(
        cfg, [TxAllowRange(433_000_000, 434_800_000)], jurisdiction="EU", persist=False
    )
    assert cfg.tx_enabled
    assert cfg.tx_consent_at
    assert cfg.jurisdiction == "EU"
    assert cfg.is_tx_range_allowed(433_920_000)


@pytest.mark.parametrize("freq_hz,name_part", [
    (1_575_420_000, "GNSS"),      # GPS L1
    (1_227_600_000, "GNSS"),      # GPS L2
    (121_500_000, "Aviation"),    # emergency
    (1_090_000_000, "ADS-B"),     # aviation surveillance
    (406_040_000, "distress"),    # EPIRB
    (156_800_000, "distress"),    # marine Ch16
])
def test_protected_band_detection(freq_hz, name_part):
    name = safety.protected_band(freq_hz)
    assert name is not None and name_part.lower() in name.lower()


def test_protected_band_refused_even_when_allowlisted():
    # A broad allow-list that covers GPS L1 must still be refused.
    cfg = Config(tx_enabled=True, tx_consent_at="now",
                 tx_allow_ranges=[TxAllowRange(1_000_000, 2_000_000_000)])
    with pytest.raises(SafetyError) as exc:
        safety.authorize_tx(cfg, 1_575_420_000, authorized=True)
    assert "safety-of-life" in str(exc.value)


def test_non_protected_freq_not_flagged():
    assert safety.protected_band(433_920_000) is None


def test_tx_audit_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert safety.read_tx_audit() == []
    safety.record_tx_event(freq_hz=433_920_000, sample_rate=2_000_000, gain=20,
                           duration_s=1.5, authorized=True, dry_run=True, outcome="dry-run")
    safety.record_tx_event(freq_hz=433_920_000, sample_rate=2_000_000, gain=20,
                           duration_s=99.0, authorized=True, dry_run=False,
                           outcome="blocked", reason="too long")
    events = safety.read_tx_audit()
    assert len(events) == 2
    assert events[0]["outcome"] == "dry-run" and events[0]["freq_mhz"] == 433.92
    assert events[1]["outcome"] == "blocked" and events[1]["reason"] == "too long"
    assert safety.clear_tx_audit() == 2
    assert safety.read_tx_audit() == []
