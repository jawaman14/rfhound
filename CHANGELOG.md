# Changelog

All notable changes to RFHound. Versioning is [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **GNSS jamming & spoofing detection (`sigint gnss`)** — Electronic Protection
  for GNSS. Ingests receiver observations (per-sat C/N0, AGC, position/time,
  satellite elevations) and flags jamming (C/N0 collapse, AGC spike, fix loss)
  and spoofing (uniform/high C/N0, elevation-decorrelated C/N0, impossible-speed
  position jumps, a static receiver that "moves" or disagrees with a known site).
  Includes a light L1 IQ check (genuine GPS sits below the noise floor) and
  built-in `nominal`/`jamming`/`spoofing` simulators. Receive-only — RFHound
  never transmits on GNSS frequencies.

## [1.1.0] — 2026-08-04

Everything since 1.0 — SIGINT/EW-support, automation, an AI console, recordings,
ID tracking, an emitter catalogue, more HackRF hardware, and dashboard polish.
Still receive-first; the no-Electronic-Attack guarantees are unchanged and
test-enforced. **207 tests**, flake8-clean.

### Added in 1.1.0
- **SIGINT / EW-support (`sigint`)** — ELINT pulse analysis (PW/PRI), interference
  characterisation (barrage/spot/multi-tone), an emitter catalogue / Electronic
  Order of Battle, and multi-node RSSI geolocation. (ES + EP only, never EA.)
- **Signal classifier + IQ modulation detection** — guess a signal's type with a
  confidence score from frequency/bandwidth/modulation; `sweep --identify`;
  `classify --file` measures real bandwidth + modulation (OOK/FSK/PSK/FM) from a
  capture (NumPy optional via `rfhound[iq]`).
- **Recordings catalog** — captures store their classification + decode settings
  in the SigMF sidecar; `recordings list|classify|show`; replay announces what a
  recording is.
- **Decoded-ID tracker (`track`)** — remembers ICAO/MMSI/sensor/pager IDs;
  `decode run --track`.
- **Automation engine + console (`automate`)** — scheduled receive-only tasks
  with triggers (threat/change/always) and actions (log, alert, webhook).
- **AI copilot console (`ai`)** — interactive, receive-only; offline / Claude /
  local providers.
- **Frequency helpers** — `at` (freq → every tool), `tune` (protocol → freq),
  ITU band designations shown across CLI + dashboard.
- **Bookmarks (`bookmark`)** and a dashboard **bookmarks panel + S-meter** with
  click-to-tune.
- **HackRF hardware** — Opera Cake antenna switch + external clock (`device`),
  documented capability table.
- **Docs** — DECODERS, SIGINT, AUTOMATION, RECORDINGS, KNOWLEDGE_BASE,
  REFERENCES, TUTORIAL; installer + Makefile + `setup`; ROADMAP (incl. TDOA).

### Fixed in 1.1.0
- NOAA APT default frequency corrected 137.500 → 137.100 MHz (accuracy audit).
- Added `test_frequency_accuracy.py` locking canonical frequencies so charts and
  decoder defaults can't silently drift.

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
