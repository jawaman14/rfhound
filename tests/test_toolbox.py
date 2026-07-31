from rfhound.modules import toolbox


def test_at_frequency_ism433():
    tb = toolbox.at_frequency(433.92)
    assert tb is not None
    assert "433" in tb.band.name
    assert "rtl433" in tb.decoders
    assert tb.commands
    assert any("decode run" in c for c in tb.commands)


def test_at_frequency_adsb_has_spoof_detector():
    tb = toolbox.at_frequency(1090.0)
    assert tb is not None
    assert any("spoof-check adsb" in d for d in tb.detectors)


def test_at_frequency_cellular_has_imsi_detector():
    tb = toolbox.at_frequency(942.0)  # GSM-900 downlink
    assert tb is not None
    assert any("imsi" in d.lower() for d in tb.detectors)


def test_at_frequency_drone_has_counter_uas():
    tb = toolbox.at_frequency(5800.0)
    assert tb is not None
    assert any("drone" in d.lower() or "uas" in d.lower() for d in tb.detectors)


def test_at_frequency_out_of_plan():
    assert toolbox.at_frequency(40000.0) is None


def test_tune_search_adsb():
    m = toolbox.tune_search("adsb")
    assert m
    assert any(abs(x.tune_mhz - 1090.0) < 1 for x in m)


def test_tune_search_tpms():
    m = toolbox.tune_search("tpms")
    assert m
    # 433 or 315 should be among matches
    assert any(int(x.tune_mhz) in (433, 434, 315) for x in m)


def test_tune_search_no_match():
    assert toolbox.tune_search("zzzznope") == []
