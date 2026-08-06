import pytest

from rfhound.modules import gnss


def test_l1_power_flags_carrier():
    np = pytest.importorskip("numpy")
    n = 8192
    t = np.arange(n)
    # A strong CW carrier at L1 => structured (low spectral flatness) => anomaly.
    carrier = np.exp(1j * 2 * np.pi * 0.11 * t).astype(np.complex64)
    res = gnss.analyze_l1_power(carrier, 2_000_000)
    assert res["anomaly"] is True
    # Pure noise (genuine GPS is below the floor) => no anomaly.
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    res2 = gnss.analyze_l1_power(noise, 2_000_000)
    assert res2["anomaly"] is False


def test_nominal_no_findings():
    report = gnss.detect_gnss_interference(gnss.simulate_nominal(), static=True)
    assert report.status == "nominal"
    assert report.findings == []
    assert report.confidence == 0
    assert report.samples == 5


def test_jamming_detected():
    report = gnss.detect_gnss_interference(gnss.simulate_jamming())
    assert report.status == "jamming"
    kinds = {f.kind for f in report.findings}
    assert kinds == {"jamming"}
    indicators = {f.indicator for f in report.findings}
    assert "fix-loss" in indicators
    assert "low-cn0" in indicators


def test_spoofing_detected():
    report = gnss.detect_gnss_interference(gnss.simulate_spoofing(), static=True)
    assert report.status == "spoofing"
    kinds = {f.kind for f in report.findings}
    assert kinds == {"spoofing"}
    indicators = {f.indicator for f in report.findings}
    assert "uniform-cn0" in indicators
    assert "position-jump" in indicators


def test_uniform_cn0_only_flags_when_high_and_present():
    # Low but uniform C/N0 is a denial (jamming) signature, not spoofing.
    obs = [gnss.GnssObservation(t=0.0, cn0=[18, 18, 19, 18],
                                elevations=[10, 30, 50, 70], fix=True)]
    report = gnss.detect_gnss_interference(obs)
    indicators = {f.indicator for f in report.findings}
    assert "uniform-cn0" not in indicators
    assert "elevation-decorrelation" not in indicators
    # It's low C/N0 => jamming.
    assert report.status == "jamming"


def test_known_location_mismatch():
    obs = [gnss.GnssObservation(t=0.0, lat=52.0, lon=0.5, alt=30,
                                cn0=[40, 42, 44, 46], elevations=[10, 30, 50, 70])]
    report = gnss.detect_gnss_interference(obs, known_location=(51.5, -0.12))
    indicators = {f.indicator for f in report.findings}
    assert "location-mismatch" in indicators
    assert report.status == "spoofing"


def test_position_jump_impossible_speed():
    obs = [
        gnss.GnssObservation(t=0.0, lat=51.5, lon=-0.12, cn0=[40, 42, 44, 46],
                             elevations=[10, 30, 50, 70]),
        gnss.GnssObservation(t=1.0, lat=52.5, lon=1.0, cn0=[40, 42, 44, 46],
                             elevations=[10, 30, 50, 70]),
    ]
    report = gnss.detect_gnss_interference(obs)
    assert any(f.indicator == "position-jump" for f in report.findings)


def test_empty_observations():
    report = gnss.detect_gnss_interference([])
    assert report.status == "nominal"
    assert report.samples == 0
