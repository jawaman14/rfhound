from rfhound.config import Config
from rfhound.modules import defense


def test_interference_monitor_simulated_detects_jamming():
    cfg = Config()
    report = defense.monitor_interference(cfg, 433.0, 435.0, iterations=12, simulate=True)
    assert report.simulated
    assert report.jammed
    assert report.alarms


def test_interference_monitor_no_alarm_when_quiet():
    cfg = Config()
    # Only baseline samples -> not enough to alarm, floor stays flat.
    report = defense.monitor_interference(cfg, 433.0, 435.0, iterations=3, simulate=True)
    # With only 3 samples (all baseline), no alarms should fire.
    assert not report.jammed


def test_detect_replays_flags_rolling_repeat():
    obs = [
        defense.Observation(0.0, "abc"),
        defense.Observation(0.5, "abc"),
    ]
    findings = defense.detect_replays(obs, rolling_expected=True)
    assert findings
    assert findings[0].payload == "abc"
    assert findings[0].count == 2


def test_detect_replays_fixed_only_flags_fast_repeats():
    obs = [
        defense.Observation(0.0, "abc"),
        defense.Observation(100.0, "abc"),  # 100s apart, plausible human presses
    ]
    findings = defense.detect_replays(obs, rolling_expected=False, window_s=8.0)
    assert not findings  # too far apart to be a replay


def test_detect_replays_fixed_flags_burst():
    obs = [defense.Observation(float(i) * 0.3, "abc") for i in range(4)]
    findings = defense.detect_replays(obs, rolling_expected=False, window_s=8.0)
    assert findings


def test_assess_fixed_code():
    payloads = defense.simulate_payloads("fixed")
    a = defense.assess_rolling_code(payloads)
    assert a.classification == "fixed"
    assert a.resilience_score < 20
    assert a.recommendations


def test_assess_rolling_code():
    payloads = defense.simulate_payloads("rolling")
    a = defense.assess_rolling_code(payloads)
    assert a.classification == "rolling"
    assert a.resilience_score >= 70


def test_assess_counter_flagged_as_weakish_rolling():
    payloads = defense.simulate_payloads("counter")
    a = defense.assess_rolling_code(payloads)
    # A plain counter should classify as rolling but be flagged as counter-like.
    assert a.classification in ("rolling", "unknown")


def test_assess_empty():
    a = defense.assess_rolling_code([])
    assert a.classification == "unknown"
    assert a.samples == 0


def test_resilience_simulated_reports_vulnerable():
    cfg = Config()
    result = defense.run_resilience_test(cfg, device="testfob", simulate=True)
    assert result.simulated
    assert result.replay_vulnerable is True
    assert result.score <= 15
    assert result.recommendations


def test_resilience_with_rolling_device_not_vulnerable():
    cfg = Config()
    payloads = defense.simulate_payloads("rolling")
    result = defense.run_resilience_test(
        cfg, device="goodfob", payloads=payloads, replayed=True, device_actuated=False
    )
    assert result.replay_vulnerable is False
    assert result.rolling is not None
    assert result.score >= 50
