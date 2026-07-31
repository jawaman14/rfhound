"""GNU Radio integration — prebuilt receive/analysis flowgraph presets.

Is it worth adding GNU Radio? Yes, for one specific job: when a signal needs
*custom DSP* (an unusual modulation, a tailored filter chain, an energy
detector) that a fixed CLI decoder can't do. GNU Radio is the right tool for
that — but hand-building flowgraphs is exactly the friction RFHound exists to
remove.

So RFHound ships **prebuilt, parameterised presets** that generate a runnable
GNU Radio Python flowgraph for you. Every preset is **receive / analysis only**
— the source is an Osmocom HackRF *source* and the sink is a file/WAV/probe.
There are deliberately no transmit (Osmocom sink) presets.

Running a generated flowgraph requires GNU Radio + gr-osmosdr installed; use
``gnuradio_status()`` to check.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import proc
from ..config import Config


@dataclass
class GnuRadioStatus:
    installed: bool
    version: str | None
    has_osmosdr: bool
    detail: str


def gnuradio_status() -> GnuRadioStatus:
    """Detect whether GNU Radio (and gr-osmosdr) are available."""
    version = None
    installed = False
    try:
        from gnuradio import gr  # type: ignore
        installed = True
        version = getattr(gr, "version", lambda: "unknown")()
    except Exception:
        # Fall back to the CLI probe.
        cfg_tool = shutil.which("gnuradio-config-info")
        if cfg_tool:
            try:
                out = proc.run([cfg_tool, "--version"], check=False, timeout=10)
                version = (out.stdout or "").strip() or None
                installed = version is not None
            except Exception:
                pass
    has_osmosdr = False
    try:
        import osmosdr  # type: ignore  # noqa: F401
        has_osmosdr = True
    except Exception:
        has_osmosdr = False
    detail = (
        f"GNU Radio {version} present"
        + (", gr-osmosdr present" if has_osmosdr else ", gr-osmosdr MISSING")
        if installed else
        "GNU Radio not found — install it to run generated flowgraphs "
        "(apt install gnuradio gr-osmosdr)."
    )
    return GnuRadioStatus(installed, version, has_osmosdr, detail)


# --------------------------------------------------------------------------- #
# Preset flowgraph templates (receive / analysis only)
# --------------------------------------------------------------------------- #
_HEADER = '''#!/usr/bin/env python3
"""RFHound-generated GNU Radio flowgraph: {name} (receive/analysis only).

Auto-generated. Requires: gnuradio, gr-osmosdr. Run: python3 {filename}
"""
from gnuradio import gr, blocks, analog, filter
from gnuradio.filter import firdes
import osmosdr

SAMPLE_RATE = {sample_rate}
CENTER_FREQ = {freq_hz}
RF_GAIN = {rf_gain}
IF_GAIN = {if_gain}
BB_GAIN = {bb_gain}


def make_source(tb):
    src = osmosdr.source(args="numchan=1 hackrf=0")
    src.set_sample_rate(SAMPLE_RATE)
    src.set_center_freq(CENTER_FREQ)
    src.set_gain(RF_GAIN)
    src.set_if_gain(IF_GAIN)
    src.set_bb_gain(BB_GAIN)
    return src
'''

_BODY = {
    "iq_record": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound IQ recorder")
        src = make_source(self)
        sink = blocks.file_sink(gr.sizeof_gr_complex, "{out}")
        self.connect(src, sink)
''',
    "wbfm": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound WBFM RX")
        audio_rate = 48000
        src = make_source(self)
        demod = analog.wfm_rcv(quad_rate=SAMPLE_RATE, audio_decimation=int(SAMPLE_RATE/audio_rate))
        sink = blocks.wavfile_sink("{out}", 1, audio_rate)
        self.connect(src, demod, sink)
''',
    "nbfm": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound NBFM RX")
        audio_rate = 48000
        decim = int(SAMPLE_RATE/audio_rate)
        src = make_source(self)
        demod = analog.nbfm_rx(audio_rate=audio_rate, quad_rate=audio_rate*decim)
        rs = filter.rational_resampler_fff(interpolation=1, decimation=decim)
        sink = blocks.wavfile_sink("{out}", 1, audio_rate)
        self.connect(src, rs, demod, sink)
''',
    "am": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound AM RX")
        audio_rate = 48000
        decim = int(SAMPLE_RATE/audio_rate)
        src = make_source(self)
        rs = filter.rational_resampler_ccf(interpolation=1, decimation=decim)
        demod = blocks.complex_to_mag(1)
        dc = blocks.sub_ff  # placeholder; AM = envelope detector
        sink = blocks.wavfile_sink("{out}", 1, audio_rate)
        self.connect(src, rs, demod, sink)
''',
    "energy_detector": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound energy detector")
        src = make_source(self)
        mag2 = blocks.complex_to_mag_squared(1)
        log = blocks.nlog10_ff(10, 1, 0)
        sink = blocks.file_sink(gr.sizeof_float, "{out}")
        self.connect(src, mag2, log, sink)
''',
    "ook_envelope": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound OOK/ASK envelope")
        src = make_source(self)
        env = blocks.complex_to_mag(1)
        sink = blocks.file_sink(gr.sizeof_float, "{out}")
        self.connect(src, env, sink)
''',
    "fsk_quad": '''

class Flow(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RFHound FSK quadrature demod")
        src = make_source(self)
        quad = analog.quadrature_demod_cf(1.0)
        sink = blocks.file_sink(gr.sizeof_float, "{out}")
        self.connect(src, quad, sink)
''',
}

_FOOTER = '''

if __name__ == "__main__":
    tb = Flow()
    try:
        tb.start()
        input("RFHound flowgraph running — press Enter to stop...\\n")
    finally:
        tb.stop()
        tb.wait()
'''


@dataclass
class FlowgraphPreset:
    id: str
    name: str
    category: str
    description: str
    default_out: str


PRESETS: dict[str, FlowgraphPreset] = {
    "iq_record": FlowgraphPreset("iq_record", "IQ recorder", "capture",
                                 "Record raw complex IQ to a file.", "capture.iq"),
    "wbfm": FlowgraphPreset("wbfm", "Wideband FM RX", "audio",
                            "Demodulate broadcast/wideband FM to a WAV.", "wbfm.wav"),
    "nbfm": FlowgraphPreset("nbfm", "Narrowband FM RX", "audio",
                            "Demodulate narrowband FM voice to a WAV.", "nbfm.wav"),
    "am": FlowgraphPreset("am", "AM RX (envelope)", "audio",
                          "Envelope-detect AM to a WAV.", "am.wav"),
    "energy_detector": FlowgraphPreset("energy_detector", "Energy detector", "analysis",
                                       "Log power (dB) vs time for presence detection.",
                                       "energy.f32"),
    "ook_envelope": FlowgraphPreset("ook_envelope", "OOK/ASK envelope", "analysis",
                                    "Magnitude envelope for OOK/ASK signal analysis.",
                                    "ook.f32"),
    "fsk_quad": FlowgraphPreset("fsk_quad", "FSK quadrature demod", "analysis",
                                "Quadrature-demod FSK to a float stream.", "fsk.f32"),
}


def list_presets() -> list[FlowgraphPreset]:
    return list(PRESETS.values())


def generate_flowgraph(
    preset_id: str,
    cfg: Config,
    *,
    freq_mhz: float,
    sample_rate: int | None = None,
    out_file: str | None = None,
    dest_path: Path | None = None,
) -> Path:
    """Write a runnable GNU Radio Python flowgraph for *preset_id*."""
    preset = PRESETS.get(preset_id)
    if not preset:
        raise ValueError(f"Unknown preset '{preset_id}'. Try: gnuradio list")
    sr = sample_rate or cfg.sample_rate
    out = out_file or preset.default_out
    dest = dest_path or Path(f"rfhound_{preset_id}.py")
    header = _HEADER.format(
        name=preset.name, filename=dest.name, sample_rate=sr,
        freq_hz=int(freq_mhz * 1e6), rf_gain=14 if cfg.amp_enable else 0,
        if_gain=cfg.lna_gain, bb_gain=cfg.vga_gain,
    )
    body = _BODY[preset_id].format(out=out)
    dest.write_text(header + body + _FOOTER)
    return dest
