# Changelog

All notable changes to RFHound. Versioning is [SemVer](https://semver.org/).

## [1.0.0] — 2026-07-31

First stable release. RFHound is a friendly, powerful **defensive** HackRF
reconnaissance & RF situational-awareness toolkit: an orchestration layer over
best-of-breed SDR tools, with a knowledge base, a web dashboard + REST API, a
detector suite, an LLM copilot, and multi-node linking.

### Added in 1.0.0
- **`rfhound at <MHz>`** — identify the band you're on and surface *every*
  associated tool: decoders, applicable threat detectors, GNU Radio presets, and
  ready-to-run example commands. `--json` for integration.
- **`rfhound tune <query>`** — type a protocol/name (adsb, tpms, pager, drone…)
  and get the frequency to tune to. `--json`.
- Web dashboard `/api/at` endpoint + an "at frequency" lookup widget.
- Full command reference in [`docs/HELP.md`](docs/HELP.md); this changelog.

### Summary of the 0.x line, now stabilised
- **0.1** — core: band plan, sweep + peak detection, recon survey, IQ capture
  (SigMF), gated replay, decoders, reporting, interactive menu, CLI, `--simulate`.
- **0.2** — defense module (jamming/replay/rolling-code), intel (TSCM baseline
  diff, ADS-B/AIS spoof detection, counter-UAS), mods/plugins, web dashboard +
  REST API, HackRF hardware controls (bias-tee, baseband filter, ppm, serial).
- **0.3** — expanded decoders (UAT/VDL2/ERT/DSD/HD Radio/WSPR/TETRA/APT/
  radiosonde/SatDump/Iridium…), GNU Radio receive/analysis presets,
  frequency-hopping detection, counter-threat playbooks, rogue-BTS /
  IMSI-catcher detection, LLM copilot, multi-node linking, dev mode, global
  simulate mode, redesigned dashboard.

### Design guarantees (unchanged, enforced by tests)
- **Receive-first.** Transmit is disabled by default and, when enabled, gated
  behind consent + a per-frequency allow-list + a per-call `--authorized` flag.
- The only transmit path is **replay of your own capture** at its own frequency.
- **No** jamming/DoS, spoofers (GPS/ADS-B/AIS/EPIRB), RollJam, brute-force,
  IMSI catcher, SS7 tooling, arbitrary/customizable transmitters, or active RF
  countermeasures. The LLM copilot and web dashboard have **no** transmit path.
