from rfhound.config import Config
from rfhound.modules import wifi as wifi_mod


def test_channel_plan_centers():
    # 2.4 GHz canonical centers.
    by_num = {c.number: c for c in wifi_mod.CHANNELS_24}
    assert by_num[1].center_hz == 2_412_000_000
    assert by_num[6].center_hz == 2_437_000_000
    assert by_num[11].center_hz == 2_462_000_000
    assert by_num[14].center_hz == 2_484_000_000
    # 5 GHz: center = 5000 MHz + n*5 MHz.
    ch36 = next(c for c in wifi_mod.CHANNELS_5 if c.number == 36)
    assert ch36.center_hz == 5_180_000_000
    ch149 = next(c for c in wifi_mod.CHANNELS_5 if c.number == 149)
    assert ch149.center_hz == 5_745_000_000


def test_dfs_flagged():
    dfs = {c.number for c in wifi_mod.CHANNELS_5 if c.dfs}
    assert 52 in dfs and 100 in dfs
    assert 36 not in dfs and 149 not in dfs


def test_channels_for_both_and_bad_band():
    assert wifi_mod.channels_for("both") == wifi_mod.CHANNELS_24 + wifi_mod.CHANNELS_5
    try:
        wifi_mod.channels_for("6")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown band")


def test_channel_at_maps_frequency():
    ch = wifi_mod.channel_at(2_437_000_000)
    assert ch is not None and ch.number == 6
    assert wifi_mod.channel_at(900_000_000) is None


def test_survey_band_24_simulate():
    cfg = Config()
    survey = wifi_mod.survey_band(cfg, "2.4", simulate=True)
    assert survey.simulated
    assert survey.band == "2.4"
    # One load per 2.4 GHz channel.
    assert len(survey.loads) == len(wifi_mod.CHANNELS_24)
    assert survey.floor_db < 0  # simulated floor is around -95 dB
    # The synthetic sweep injects energy near 2442 MHz -> some channel is busy.
    assert survey.busy_channels


def test_survey_recommend_24_is_non_overlapping():
    cfg = Config()
    survey = wifi_mod.survey_band(cfg, "2.4", simulate=True)
    best, reason = survey.recommend()
    assert best is not None
    assert best.channel.number in (1, 6, 11)
    assert reason


def test_survey_band_5_simulate():
    cfg = Config()
    survey = wifi_mod.survey_band(cfg, "5", simulate=True)
    assert len(survey.loads) == len(wifi_mod.CHANNELS_5)
    best, _ = survey.recommend()
    assert best is not None


def test_summarize_no_crash(capsys):
    cfg = Config()
    survey = wifi_mod.survey_band(cfg, "2.4", simulate=True)
    wifi_mod.summarize(survey)
    out = capsys.readouterr().out
    assert "Wi-Fi" in out
    assert "Suggested channel" in out
