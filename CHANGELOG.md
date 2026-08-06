# Changelog

All notable changes to RFHound. Versioning is [SemVer](https://semver.org/).

## [Unreleased] — v1.3 (rebuild & beef-up)

### Added
- **VISION.md** — the project's purpose, aim, and explicit positioning vs other
  SDR software; steers the UI and feature direction.
- **Ground-up dashboard rebuild** (SDR-software-inspired): receiver bar (big
  frequency readout, span, step/zoom, band-preset chips), dB-axed interactive
  spectrum with a hover cursor and click-to-inspect, and new **Capture**,
  **Recordings**, **Emitters (EOB)**, and **Sightings** panels. New endpoints:
  `POST /api/capture` (receive-only, token-gated), `GET /api/recordings`,
  `GET /api/emitters`.
- **RF front-end guide** (`doctor --rf`, `--rf --freq MHz`) — antenna / filter /
  LNA recommendation per band, from the collection-hardware notes.
- **Email (SMTP) alerting** for automations (`automate add … --email`,
  `config smtp …`) alongside webhooks.
- **GeoJSON export** for geolocation fixes (`sigint locate … --geojson FILE`) —
  emitter + receiver points for a map/GIS.
- **Config wizard** (`rfhound config wizard`) — interactive first-run setup for
  the capture dir, hardware gains, simulate default, and optional SMTP alerts.
- **Deployment packaging** — a `Dockerfile` (bundles hackrf + rtl-433) and
  `docker-compose.yml` (dashboard + hub), plus hardened **systemd units** in
  `deploy/` for an unattended, receive-only, token-gated sensor node.

### Removed
- Dead code: unused `console.live_lines`/`make_text` helpers (and their now-orphan
  rich imports), and an always-true `if` guard in the `node` command.

## [1.2.0] — 2026-08-06

Enterprise hardening on top of 1.1: GNSS integrity monitoring, an authenticated
dashboard, machine-readable output, and menu parity. Still receive-first; the
no-Electronic-Attack guarantees are unchanged and test-enforced. **243 tests**,
flake8-clean.

### Added
- **Dashboard UI/UX polish** — a persisted theme toggle (auto/dark/light) that
  overrides the OS preference; an S-meter with an S-unit scale (S1–S9/+20/+40),
  a peak-hold marker, and the strongest-peak frequency; and inline bookmark
  editing (add/delete from the UI, or ★ the current sweep centre) backed by new
  token-gated `POST /api/bookmarks/add` and `/delete` endpoints. The
  spectrum/waterfall canvases stay dark in both themes. Bookmark names are
  HTML-escaped on render.
- **Live threat-KPI auto-refresh** — a "Live" toggle re-runs the drone/ADS-B/
  IMSI checks every 5 s with a pulsing status indicator.
- **Waterfall colormaps + intensity** — pick Aqua/Turbo/Viridis/Inferno/
  Grayscale and adjust an intensity slider; both are persisted and re-colour the
  existing waterfall without re-sweeping.
- **Per-panel export** — download the peaks, recon, and knowledge-base tables as
  CSV or JSON straight from the dashboard.
- **Peak detail drawer** — clicking a spectrum peak opens a slide-in drawer with
  "what's here" (band, decoders, detectors), a ranked signal classification with
  confidence bars, and a copyable suggested decoder command, plus tune/bookmark
  shortcuts.
- A 204 handler for `/favicon.ico` (silences the browser's default request).
- **Transmit safety hardening** (authorized replay-of-your-own-capture only —
  still no signal generation, jamming, or spoofing):
  - **Safety-of-life refuse-list** — GNSS, aviation VHF (incl. 121.5), ADS-B/UAT,
    marine distress, and COSPAS-SARSAT beacon bands are **always** refused, even
    if the operator allow-listed a range covering them.
  - **Max replay duration cap** (`tx_max_seconds`, default 30 s) rejects an
    over-long or looping on-air time.
  - **Append-only transmit audit log** of every attempt (transmitted / blocked /
    dry-run) — view with `rfhound tx audit [--json] [--clear]`; `tx status` shows
    the policy + recent events.
  - **`replay --dry-run`** now prints a preflight summary (frequency + ITU band,
    duration vs. cap, allow-list status, protected-band check) without keying.
- **Web dashboard authentication** — optional bearer-token auth on all `/api/…`
  endpoints (`rfhound web --token`), auto-generated when binding to a
  non-localhost host, with a warning when exposed without one. Token accepted as
  a Bearer header, `X-RFHound-Token`, `?token=`, or the `rfh_token` cookie; the
  HTML shell captures it into `sessionStorage`. Defensive response headers added.
- **Machine-readable output (`--json`)** on `doctor` and `sigint gnss` (joining
  `at`/`tune`/`classify`) for SIEM/automation; non-nominal GNSS exits non-zero.
- **Interactive menu parity** — a SIGINT/EW submenu (interference, emitter
  catalogue, geolocation, GNSS spoof detection) and a captures/recordings entry.
- **More automation (still receive-only)** — two new scheduled tasks: `gnss`
  (GNSS integrity monitor that alerts on jamming/spoofing) and `emitters` (builds
  the emitter catalogue / Electronic Order of Battle over time and alerts on new
  emitters); an `--alert-cooldown` to suppress repeat alerts for a standing
  condition; and a general `--param KEY=VALUE` for per-task options. Automations
  never transmit.

### Fixed
- **Input validation** — `sweep`, `capture`, and `classify` now reject
  frequencies outside the HackRF's 1–6000 MHz range, reversed sweep ranges
  (start ≥ stop), and non-positive capture lengths with a clear message and a
  non-zero exit, instead of failing obscurely or accepting impossible input.
- JSON output is written verbatim (via `console.raw`) instead of through the
  rich console, which soft-wrapped long values and produced invalid JSON.
- Corrected the project Homepage/URLs to the standalone `jawaman14/rfhound`
  repository; CI now lints `tests/` alongside `rfhound/`.

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
