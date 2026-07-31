import ast

from rfhound.config import Config
from rfhound.modules import gnuradio as gr_mod
from rfhound.modules import response as response_mod
from rfhound.modules import intel


# --- GNU Radio presets ------------------------------------------------------
def test_gnuradio_status_runs():
    st = gr_mod.gnuradio_status()
    assert isinstance(st.installed, bool)
    assert st.detail


def test_presets_listed():
    ids = {p.id for p in gr_mod.list_presets()}
    assert {"iq_record", "wbfm", "nbfm", "energy_detector", "fsk_quad"} <= ids


def test_generate_flowgraph_is_valid_python(tmp_path):
    cfg = Config()
    for pid in [p.id for p in gr_mod.list_presets()]:
        dest = tmp_path / f"{pid}.py"
        gr_mod.generate_flowgraph(cfg=cfg, preset_id=pid, freq_mhz=433.92,
                                  dest_path=dest)
        assert dest.exists()
        # It must at least parse as Python.
        ast.parse(dest.read_text())


def test_generate_unknown_preset_raises(tmp_path):
    try:
        gr_mod.generate_flowgraph("nope", Config(), freq_mhz=100, dest_path=tmp_path / "x.py")
        assert False
    except ValueError:
        pass


def test_generated_flowgraph_has_no_tx_sink(tmp_path):
    # Receive-only: never an osmosdr sink (transmit).
    cfg = Config()
    for pid in [p.id for p in gr_mod.list_presets()]:
        dest = tmp_path / f"{pid}.py"
        gr_mod.generate_flowgraph(cfg=cfg, preset_id=pid, freq_mhz=100, dest_path=dest)
        text = dest.read_text()
        assert "osmosdr.sink" not in text
        assert "osmosdr.source" in text


# --- Response playbooks -----------------------------------------------------
def test_all_playbooks_present():
    threats = set(response_mod.list_threats())
    assert {"jamming", "gps_spoof", "adsb_spoof", "ais_spoof", "drone",
            "rogue_emitter", "replay"} <= threats


def test_playbook_has_actions():
    pb = response_mod.get_playbook("jamming")
    assert pb.immediate and pb.evidence and pb.mitigations and pb.escalation


def test_drone_playbook_forbids_active_countermeasures():
    pb = response_mod.get_playbook("drone")
    joined = " ".join(pb.escalation).lower()
    assert "do not attempt rf takeover" in joined or "jamming" in joined


def test_unknown_playbook_is_none():
    assert response_mod.get_playbook("nope") is None


# --- Frequency-hopping detection -------------------------------------------
def test_hopping_detected():
    slices = intel.simulate_hopping_slices(hopping=True)
    r = intel.detect_frequency_hopping(slices)
    assert r.hopping_suspected


def test_steady_carrier_not_flagged():
    slices = intel.simulate_hopping_slices(hopping=False)
    r = intel.detect_frequency_hopping(slices)
    assert not r.hopping_suspected
