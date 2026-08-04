# Architecture

RFHound is a thin, well-tested **orchestration layer** over best-of-breed SDR
CLIs. The design goal: be friendly enough for a beginner and scriptable enough
for a pro, while never pretending to do DSP it doesn't actually do.

## Layout

```
rfhound/
├── rfhound/
│   ├── cli.py         # argparse subcommands (the scriptable surface)
│   ├── menu.py        # guided interactive menu (the friendly surface)
│   ├── console.py     # rich-or-plain output (graceful degradation)
│   ├── config.py      # ~/.config/rfhound/config.json (incl. TX safety)
│   ├── safety.py      # the transmit authorization gate (no jamming/DoS)
│   ├── proc.py        # subprocess runner + external-tool detection catalogue
│   ├── device.py      # HackRF detection via hackrf_info
│   ├── bandplan.py    # the frequency knowledge base
│   ├── plugins.py     # mod/plugin loader (custom bands/recipes/detectors)
│   ├── exceptions.py  # typed error hierarchy
│   ├── web/           # browser dashboard + JSON REST API (stdlib http.server)
│   │   ├── server.py  # routing, JSON serialisers (RX-only, no TX endpoint)
│   │   └── dashboard.html  # self-contained SPA (canvas spectrum + waterfall)
│   ├── llm/           # LLM copilot — safe, RX-only action registry + agent
│   │   ├── actions.py # the ONLY actions a model may call (no TX / no exec)
│   │   └── agent.py   # anthropic / local / offline providers
│   ├── net/           # multi-node linking (hub aggregator + node client)
│   │   ├── hub.py     # aggregator server (roster + report feed)
│   │   └── node.py    # push status/findings to a hub
│   └── modules/
│       ├── sweep.py   # hackrf_sweep driver + peak detection + simulate
│       ├── capture.py # hackrf_transfer record + SigMF metadata
│       ├── replay.py  # hackrf_transfer replay (gated through safety.py)
│       ├── decode.py  # registry of decoder "recipes" (rtl_433/dump1090/…)
│       ├── recon.py   # multi-band auto-survey
│       ├── defense.py # detection & hardening (jamming/replay/rolling-code)
│       ├── intel.py   # TSCM baseline diff, ADS-B/AIS spoof detection, C-UAS, hop-detect
│       ├── gnuradio.py # GNU Radio receive/analysis flowgraph preset generator
│       ├── response.py # defensive counter-threat playbooks
│       ├── cellular.py # rogue base station / IMSI-catcher detection
│       ├── toolbox.py # frequency→tools ('at') and protocol→frequency ('tune')
│       ├── classify.py # signal auto-matching: guess type + confidence
│       └── report.py  # Markdown / HTML reporting
└── tests/             # pytest suite (runs with no hardware)
```

## Key design decisions

**Wrap, don't reinvent.** DSP-heavy work (sweeping, demodulation, protocol
decode) is delegated to mature tools. `proc.py` centralises how they're found
(`shutil.which`) and run (with timeouts and clean errors), and carries a
`KNOWN_TOOLS` catalogue with install hints surfaced by `rfhound doctor`.

**Recipes, not hard-coded pipelines.** `modules/decode.py` is a registry of
`Recipe` objects: each knows its tool, how to build an argv for a frequency, and
a legal/usage note. Adding a decoder is adding one `Recipe`. This keeps RFHound
honest — a recipe whose tool is missing is reported as such, never faked.

**Simulate mode is first-class.** `sweep.py` can synthesise plausible spectrum
(noise floor + injected signals at real band centers). Every scan command takes
`--simulate`, so the whole pipeline — parsing, peak detection, rendering,
reporting — is exercised by the test suite and usable for demos without a HackRF.

**Safety is a chokepoint, not a sprinkle.** *Every* transmit goes through
`safety.authorize_tx()`, which requires (a) `tx_enabled` + recorded consent in
config, (b) the frequency inside a declared allow-range, and (c) an explicit
per-call `authorized=True`. There is no "allow all" and no code path that keys
the radio while bypassing this. Jamming/DoS/deauth/brute-force are absent by
design.

**Graceful output.** `console.py` uses `rich` when importable and falls back to
ANSI/plain `print` otherwise, so RFHound runs in minimal environments.

## Data formats

Captures are written as interleaved signed-8-bit IQ (`hackrf_transfer -r`
output) with a **SigMF**-compatible `.sigmf-meta` sidecar (`core:datatype: ci8`),
so they open directly in URH, inspectrum, and GNU Radio.

## Extending RFHound

- **Add a band:** append a `Band` to `bandplan.BANDS`.
- **Add a decoder:** add a `Recipe` to `decode.RECIPES` (+ its tool to
  `proc.KNOWN_TOOLS`).
- **Add a report format:** add a `to_<fmt>()` in `modules/report.py`.
- **Add a CLI command:** add a subparser + handler in `cli.py`.

Run the suite with `pytest` and lint with
`flake8 rfhound --max-line-length=110`.
