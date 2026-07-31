"""Frequency-aware toolbox.

Two operator conveniences:

* **"What am I looking at?"** — given a frequency, identify the band and surface
  *every* tool associated with it: decoders, applicable threat detectors, GNU
  Radio presets, and ready-to-run example commands.
* **"What frequency do I need?"** — search the knowledge base by protocol/name
  (e.g. "adsb", "tpms", "pager") and get the frequency to tune to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import bandplan
from . import decode as decode_mod


@dataclass
class BandToolbox:
    band: bandplan.Band
    decoders: list = field(default_factory=list)      # decode recipe ids
    detectors: list = field(default_factory=list)     # defense subcommands
    gnuradio: list = field(default_factory=list)      # suggested presets
    commands: list = field(default_factory=list)      # copy-paste example commands


def _decoders_for(band: bandplan.Band) -> list:
    """Decoders whose default frequency is in-band, or whose category matches."""
    out = []
    for r in decode_mod.list_recipes():
        in_band = band.low_hz <= r.default_freq_hz <= band.high_hz
        if in_band or r.category == band.category:
            out.append(r.id)
    # The band's own suggested decoder first, de-duplicated.
    ordered = ([band.decoder] if band.decoder else []) + out
    seen, uniq = set(), []
    for x in ordered:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _detectors_for(band: bandplan.Band) -> list:
    """Threat detectors that make sense for this band."""
    d = ["monitor (jamming/interference)", "baseline (TSCM rogue-emitter)",
         "hop-detect (frequency-agile emitters)"]
    tags = set(band.tags)
    cat = band.category
    if cat == "cellular":
        d.insert(0, "imsi-catcher (rogue base station)")
    if cat == "aviation" and ("adsb" in tags or "1090" in band.name):
        d.insert(0, "spoof-check adsb")
    if cat == "maritime" or "ais" in tags:
        d.insert(0, "spoof-check ais")
    if cat == "cuas" or "drone" in tags:
        d.insert(0, "drone-scan (counter-UAS)")
    if "keyfob" in tags or "tpms" in tags or cat == "ism":
        d.insert(0, "replay-check / rolling-assess (device security)")
    return d


def _gnuradio_for(band: bandplan.Band) -> list:
    """Suggested GNU Radio presets by band character."""
    cat = band.category
    if cat == "broadcast" and "FM" in band.name:
        return ["wbfm", "iq_record"]
    if cat in ("voice", "amateur"):
        return ["nbfm", "am", "iq_record"]
    if cat in ("ism", "iot", "cuas"):
        return ["ook_envelope", "fsk_quad", "energy_detector", "iq_record"]
    return ["energy_detector", "iq_record"]


def tools_for_band(band: bandplan.Band) -> BandToolbox:
    tune = band.tune_hz / 1e6
    decoders = _decoders_for(band)
    detectors = _detectors_for(band)
    gr = _gnuradio_for(band)
    commands = [f"rfhound sweep {band.low_hz/1e6:.3f} {band.high_hz/1e6:.3f}",
                f"rfhound capture {tune:.3f} 10"]
    for rid in decoders[:3]:
        commands.append(f"rfhound decode run {rid} --freq {tune:.3f}")
    commands.append(f"rfhound gnuradio gen {gr[0]} --freq {tune:.3f}")
    return BandToolbox(band=band, decoders=decoders, detectors=detectors,
                       gnuradio=gr, commands=commands)


def at_frequency(freq_mhz: float) -> BandToolbox | None:
    """Identify the band at *freq_mhz* and return its full toolbox."""
    band = bandplan.find_band(int(freq_mhz * 1e6))
    return tools_for_band(band) if band else None


@dataclass
class TuneMatch:
    name: str
    tune_mhz: float
    low_mhz: float
    high_mhz: float
    category: str
    decoder: str | None


def tune_search(query: str) -> list[TuneMatch]:
    """Find the frequency to tune to for a protocol/name/tag query."""
    q = query.lower().strip()
    matches = []
    for b in bandplan.BANDS:
        hay = " ".join([b.name.lower(), b.category, " ".join(b.tags),
                        b.description.lower()])
        if q in hay:
            matches.append(TuneMatch(b.name, round(b.tune_hz / 1e6, 4),
                                     b.low_hz / 1e6, b.high_hz / 1e6,
                                     b.category, b.decoder))
    # Rank: a name hit first, then bands that have a decoder, then by frequency.
    matches.sort(key=lambda m: (q not in m.name.lower(), m.decoder is None, m.tune_mhz))
    return matches
