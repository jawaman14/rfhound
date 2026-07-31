from rfhound.config import Config
from rfhound.modules import sweep as sweep_mod


def test_parse_hackrf_sweep_line():
    line = "2024-01-01, 12:00:00, 433000000, 434000000, 100000.0, 20, -80.1, -40.2, -79.9"
    bins = sweep_mod._parse_hackrf_sweep_line(line)
    assert len(bins) == 3
    assert bins[0].freq_hz == 433_050_000  # low + 0.5 * binwidth
    assert bins[1].power_db == -40.2


def test_parse_bad_line_returns_empty():
    assert sweep_mod._parse_hackrf_sweep_line("garbage") == []
    assert sweep_mod._parse_hackrf_sweep_line("") == []


def test_detect_peaks_finds_injected_signal():
    bins = [sweep_mod.Bin(433_000_000 + i * 100_000, -90.0) for i in range(20)]
    bins[10] = sweep_mod.Bin(bins[10].freq_hz, -30.0)  # strong peak
    peaks, floor = sweep_mod._detect_peaks(bins, snr_db=12)
    assert floor <= -80
    assert peaks
    assert peaks[0].freq_hz == 434_000_000


def test_simulate_sweep_produces_peaks_in_ism433():
    cfg = Config()
    result = sweep_mod.sweep(cfg, 433.0, 435.0, simulate=True)
    assert result.simulated
    assert result.bins
    assert result.peaks  # injected signal at 433.92 should be found
    # The strongest peak should map to a known band.
    assert any(p.band is not None for p in result.peaks)


def test_simulate_sweep_adsb():
    cfg = Config()
    result = sweep_mod.sweep(cfg, 1089.0, 1091.0, simulate=True)
    assert result.peaks
    strongest = result.peaks[0]
    assert strongest.band is not None
    assert "ADS-B" in strongest.band.name


def test_render_spectrum_no_crash(capsys):
    cfg = Config()
    result = sweep_mod.sweep(cfg, 433.0, 435.0, simulate=True)
    sweep_mod.render_spectrum(result)
    out = capsys.readouterr().out
    assert "Spectrum" in out
