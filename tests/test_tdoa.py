import math

import pytest

np = pytest.importorskip("numpy")

from rfhound.modules import tdoa  # noqa: E402


def test_enu_roundtrip():
    ref = (51.5, -0.12)
    for lat, lon in [(51.52, -0.10), (51.49, -0.15)]:
        e, n = tdoa.latlon_to_enu(lat, lon, *ref)
        lat2, lon2 = tdoa.enu_to_latlon(e, n, *ref)
        assert abs(lat - lat2) < 1e-6 and abs(lon - lon2) < 1e-6


def test_estimate_tdoa_recovers_known_delay():
    sr = 20_000_000
    rng = np.random.default_rng(0)
    sig = (rng.standard_normal(8192) + 1j * rng.standard_normal(8192)).astype(np.complex64)
    delay = 37  # samples
    other = np.roll(sig, delay)
    tau = tdoa.estimate_tdoa(sig, other, sr)
    assert abs(tau * sr - delay) < 1.0     # within a sample


def test_solve_tdoa_recovers_emitter_no_noise():
    emitter = (51.510, -0.118)
    nodes_ll = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.130), (51.515, -0.140)]
    nodes = tdoa.simulate_scenario(emitter, nodes_ll, sigma_tdoa_s=0.0)
    fix = tdoa.solve_tdoa(nodes)
    assert fix is not None and fix.method == "tdoa"
    # Recover within ~50 m with clean TDOAs.
    e1, n1 = tdoa.latlon_to_enu(fix.lat, fix.lon, emitter[0], emitter[1])
    assert math.hypot(e1, n1) < 50.0
    assert fix.residual_m < 1.0


def test_solve_tdoa_needs_three_nodes():
    emitter = (51.51, -0.12)
    nodes = tdoa.simulate_scenario(emitter, [(51.52, -0.12), (51.50, -0.10)])
    assert tdoa.solve_tdoa(nodes) is None  # only 2 nodes


def test_geolocate_tdoa_falls_back_to_rssi():
    # Two nodes, no tdoa but with rssi -> RSSI fallback.
    nodes = [tdoa.Node("a", 51.52, -0.12, rssi=-55),
             tdoa.Node("b", 51.50, -0.10, rssi=-65)]
    fix = tdoa.geolocate_tdoa(nodes)
    assert fix.method == "rssi-fallback"
    assert fix.lat is not None


def test_full_pipeline_from_captures():
    emitter = (51.512, -0.121)
    nodes_ll = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.135), (51.518, -0.145)]
    caps = tdoa.simulate_captures(emitter, nodes_ll, sample_rate=40_000_000, n_samples=16384)
    nodes = tdoa.tdoa_from_captures(caps, sample_rate=40_000_000)
    fix = tdoa.geolocate_tdoa(nodes)
    assert fix.method == "tdoa"
    # Integer-sample delays -> recover within a few hundred metres.
    e1, n1 = tdoa.latlon_to_enu(fix.lat, fix.lon, emitter[0], emitter[1])
    assert math.hypot(e1, n1) < 400.0


def test_gdop_and_confidence_present():
    emitter = (51.510, -0.118)
    nodes = tdoa.simulate_scenario(
        emitter, [(51.520, -0.120), (51.505, -0.100), (51.500, -0.130), (51.515, -0.140)],
        sigma_tdoa_s=1e-8)
    fix = tdoa.solve_tdoa(nodes, sigma_tdoa_s=1e-7)
    assert fix.gdop is not None and fix.gdop > 0
    assert fix.confidence_m is not None
