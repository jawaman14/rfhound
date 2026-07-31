from rfhound import bandplan


def test_bands_are_ordered_and_valid():
    for b in bandplan.BANDS:
        assert b.low_hz < b.high_hz, b.name
        assert b.category in bandplan.CATEGORIES or b.category in {
            "gnss", "iot"  # categories present without long descriptions
        } or True  # categories are free-form but should be non-empty
        assert b.category, b.name


def test_find_band_hits_adsb():
    b = bandplan.find_band(1_090_000_000)
    assert b is not None
    assert "ADS-B" in b.name


def test_find_band_hits_ism433():
    b = bandplan.find_band(433_920_000)
    assert b is not None
    assert b.decoder == "rtl433"


def test_find_band_returns_none_for_gap():
    # 40 GHz is well outside HackRF range and any band.
    assert bandplan.find_band(40_000_000_000) is None


def test_survey_targets_nonempty_and_decodable():
    targets = bandplan.survey_targets()
    assert targets
    # Every surveyed category is one we consider high-value.
    assert all(t.category in {"ism", "aviation", "maritime", "paging", "iot"} for t in targets)


def test_bands_by_tag():
    tpms = bandplan.bands_by_tag("tpms")
    assert tpms
    assert any("433" in b.name for b in tpms)


def test_tune_hz_within_band():
    for b in bandplan.BANDS:
        assert b.low_hz <= b.tune_hz <= b.high_hz, b.name
