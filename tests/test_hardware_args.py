from rfhound import proc
from rfhound.config import Config


def test_no_hardware_flags_by_default():
    assert proc.hackrf_common_args(Config()) == []


def test_amp_and_bias_tee():
    cfg = Config(amp_enable=True, antenna_power=True)
    args = proc.hackrf_common_args(cfg)
    assert "-a" in args and "1" in args
    assert "-p" in args


def test_device_serial_selection():
    cfg = Config(device_serial="0000000000000000abcd")
    args = proc.hackrf_common_args(cfg)
    assert args[:2] == ["-d", "0000000000000000abcd"]


def test_baseband_and_ppm_only_for_transfer_not_sweep():
    cfg = Config(baseband_filter_hz=3_500_000, freq_correction_ppm=12)
    transfer = proc.hackrf_common_args(cfg)
    sweep = proc.hackrf_common_args(cfg, for_sweep=True)
    assert "-b" in transfer and "-C" in transfer
    assert "-b" not in sweep and "-C" not in sweep


def test_config_roundtrip_includes_hardware(tmp_path, monkeypatch):
    from rfhound.config import save_config, load_config
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config(Config(antenna_power=True, baseband_filter_hz=5_000_000, device_serial="abc"))
    loaded = load_config()
    assert loaded.antenna_power is True
    assert loaded.baseband_filter_hz == 5_000_000
    assert loaded.device_serial == "abc"
