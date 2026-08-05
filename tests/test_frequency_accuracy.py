"""Lock canonical frequencies so the charts and decoder defaults can't drift.

These assert real-world allocations against the values RFHound ships. If a future
edit moves a decoder default or band edge off its canonical frequency, this fails.
Sources: ITU/regional allocations, sigidwiki, the decoders' own docs.
"""

from rfhound import bandplan
from rfhound.modules import classify, decode


def _rec_mhz(rid: str) -> float:
    return decode.get_recipe(rid).default_freq_hz / 1e6


def _band_at(mhz: float):
    return bandplan.find_band(int(mhz * 1e6))


# Canonical decoder default frequencies (MHz). Tolerance is tight (10 kHz).
CANONICAL_DECODERS = {
    "adsb": 1090.0,        # 1090ES
    "uat978": 978.0,       # UAT
    "ais": 162.0,          # AIS1/AIS2 = 161.975 / 162.025, band center
    "acars": 131.55,       # US primary
    "vdl2": 136.975,       # VDL2 primary
    "noaa_apt": 137.1,     # NOAA-19
    "ert": 912.6,          # ERT/SCM smart meters
    "radiosonde": 403.0,   # ~400-406 band
    "iridium": 1621.25,    # L-band
    "pocsag": 929.0,       # US paging
    "flex": 929.0,
    "wspr": 14.0956,       # 20 m WSPR dial + 1500 Hz audio
}


def test_decoder_default_frequencies_are_canonical():
    for rid, mhz in CANONICAL_DECODERS.items():
        got = _rec_mhz(rid)
        assert abs(got - mhz) <= 0.01, f"{rid}: {got} MHz != canonical {mhz} MHz"


def test_noaa_apt_is_a_real_satellite_frequency():
    # Must be one of the three active NOAA APT downlinks (guards the old bug).
    assert _rec_mhz("noaa_apt") in (137.1, 137.62, 137.9125)


def test_gps_l1_band():
    b = _band_at(1575.42)
    assert b is not None and "GPS" in b.name


def test_ais_channels_fall_in_marine_band():
    for f in (161.975, 162.025):
        b = _band_at(f)
        assert b is not None and "AIS" in b.name


def test_adsb_band():
    b = _band_at(1090.0)
    assert b is not None and "ADS-B" in b.name


def test_ism_band_names():
    assert "315" in _band_at(315.0).name
    assert "433" in _band_at(433.92).name
    assert "868" in _band_at(868.3).name
    assert "915" in _band_at(915.0).name


def test_fm_broadcast_band():
    assert _band_at(100.0).name == "FM broadcast"


def test_itu_designations():
    assert bandplan.itu_band(int(14.0e6))[0] == "HF"
    assert bandplan.itu_band(int(100.0e6))[0] == "VHF"
    assert bandplan.itu_band(int(433.92e6))[0] == "UHF"
    assert bandplan.itu_band(int(1575.42e6))[0] == "UHF"
    assert bandplan.itu_band(int(5000.0e6))[0] == "SHF"


def test_classifier_canonical_frequencies():
    assert classify.classify(1090.0, bandwidth_khz=1500)[0].decoder == "adsb"
    assert classify.classify(1575.42)[0].category == "gnss"
    assert classify.classify(162.0, bandwidth_khz=25)[0].decoder == "ais"


def test_all_bands_are_sane():
    # Sanity guard against typo'd frequencies. Some reference bands (AM
    # broadcast, HF) sit below HackRF's native 1 MHz and need an upconverter,
    # so allow down to 100 kHz; nothing should start above the 6 GHz ceiling.
    for b in bandplan.BANDS:
        assert b.low_hz < b.high_hz, b.name
        assert b.low_hz >= 100_000, b.name
        assert b.low_hz <= 6_000_000_000, b.name
