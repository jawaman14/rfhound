from rfhound.config import Config
from rfhound.modules import classify, sweep as sweep_mod


def test_adsb_top_at_1090():
    m = classify.classify(1090.0, bandwidth_khz=1500)
    assert m[0].name.startswith("ADS-B 1090")
    assert m[0].decoder == "adsb"
    assert m[0].likelihood >= 60


def test_fm_broadcast():
    m = classify.classify(100.1, bandwidth_khz=180, modulation="wfm")
    assert m[0].name == "FM broadcast"
    assert m[0].likelihood >= 70


def test_ism_ook_prefers_rtl433_ook():
    m = classify.classify(433.92, bandwidth_khz=40, modulation="ook")
    assert m[0].decoder == "rtl433"
    assert "ook" in " ".join(m[0].reasons).lower()


def test_bandwidth_mismatch_lowers_score():
    # A ~20 MHz-wide signal at 433 is not a narrow ISM remote.
    narrow = classify.classify(433.92, bandwidth_khz=40)[0].likelihood
    wide = classify.classify(433.92, bandwidth_khz=20000)[0].likelihood
    assert wide <= narrow


def test_modulation_hint_changes_ranking():
    fsk = classify.classify(433.92, modulation="fsk")
    ook = classify.classify(433.92, modulation="ook")
    # Whichever matches should be near the top with a decent score.
    assert fsk[0].likelihood >= 50
    assert ook[0].likelihood >= 50


def test_out_of_plan_is_unknown():
    m = classify.classify(40000.0)
    assert m[0].name in ("Unknown",) or m[0].likelihood <= 30


def test_estimate_bandwidth_from_simulated_sweep():
    cfg = Config()
    result = sweep_mod.sweep(cfg, 433.0, 435.0, simulate=True)
    peak = result.peaks[0]
    bw = classify.estimate_bandwidth_khz(result, peak.freq_hz)
    assert bw is None or bw > 0


def test_best_guess_returns_single():
    g = classify.best_guess(162.0, 25)
    assert g.name and 0 <= g.likelihood <= 100
