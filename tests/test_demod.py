import pytest

from rfhound import plugins
from rfhound.modules import demod


# --- bit/byte primitives ---
def test_manchester_decode():
    # 10 -> 1, 01 -> 0; a 00/11 pair is a violation (None).
    assert demod.manchester_decode([1, 0, 0, 1]) == [1, 0]
    assert demod.manchester_decode([1, 0, 1, 1]) == [1, None]
    assert demod.manchester_decode([1]) == []            # trailing odd bit dropped


def test_differential_decode():
    # out[i] = bit[i] XOR bit[i-1]  (prev starts at `initial`)
    assert demod.differential_decode([1, 1, 0, 0], initial=0) == [1, 0, 1, 0]
    assert demod.differential_decode([0, 0, 0], initial=1) == [1, 0, 0]
    assert demod.differential_decode([1, 0, 1], initial=1) == [0, 1, 1]


def test_bits_to_bytes_roundtrip():
    assert demod.bits_to_bytes([0, 1, 0, 0, 1, 0, 0, 0]) == b"H"          # MSB-first
    assert list(demod.bits_to_bytes([0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 1])) == [0x48]  # tail dropped
    lsb = demod.bits_to_bytes([1, 0, 0, 0, 0, 0, 0, 0], msb_first=False)
    assert lsb == b"\x01"


def test_crc8_known_vector():
    # CRC-8/SMBus (poly 0x07, init 0x00) of b"123456789" is 0xF4.
    assert demod.crc8(b"123456789") == 0xF4
    assert demod.crc8(b"") == 0x00


# --- registry ---
def test_builtins_registered():
    assert {"manchester", "nrzi", "bytes", "ook", "fsk"} <= set(demod.names())
    d = demod.get("manchester")
    assert d.kind == "bits" and d.source == "built-in"


def test_register_and_run_custom():
    demod.register("rev", "reverse bits", lambda bits, **_: list(reversed(bits)),
                   kind="bits", description="test")
    assert demod.run("rev", [1, 0, 0]) == [0, 0, 1]
    with pytest.raises(KeyError):
        demod.run("does-not-exist", [])


def test_register_rejects_bad_kind():
    with pytest.raises(ValueError):
        demod.register("x", "x", lambda p: p, kind="banana")


# --- IQ demod (needs numpy) ---
def test_ook_bits_from_iq():
    np = pytest.importorskip("numpy")
    sr, baud = 8000, 1000            # 8 samples per symbol
    # Alternating on/off symbols -> 1,0,1,0
    sym = [1, 0, 1, 0]
    iq = np.repeat(np.array(sym, dtype=float), sr // baud).astype(complex)
    assert demod.ook_bits(iq, sr, baud) == [1, 0, 1, 0]


# --- mod integration ---
def test_mod_can_register_soft_decoder(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text(
        "NAME='D'\nVERSION='1'\n"
        "def register(api):\n"
        "    api.add_soft_decoder('mine', 'Mine', lambda b, **_: api.demod.manchester_decode(b),\n"
        "                         kind='bits', description='x')\n")
    loaded = plugins.load_mods(tmp_path)
    assert loaded and loaded[0].decoders == ["mine"] and loaded[0].error is None
    assert demod.run("mine", [1, 0, 0, 1]) == [1, 0]
    assert demod.get("mine").source == "mod"


def test_sample_mod_decoder_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    plugins.write_sample_mod()
    loaded = plugins.load_mods()
    assert any("acme" in m.decoders for m in loaded)
    # Build a valid Acme frame: body byte 0x48, Manchester-encode body+crc.
    body = bytes([0x48])
    crc = demod.crc8(body)
    frame = body + bytes([crc])
    bits = []
    for byte in frame:
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            bits += [1, 0] if bit else [0, 1]      # Manchester encode
    out = demod.run("acme", bits)
    assert out["ok"] is True
