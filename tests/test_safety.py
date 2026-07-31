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
