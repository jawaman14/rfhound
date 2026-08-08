# RFHound roadmap

A living, detailed plan — where the project is, how it got here, and where it's
going. This is the reference I (and any contributor) steer by; it is
intentionally opinionated about scope. It's research-informed: the threat items
trace back to [`docs/THREATS.md`](docs/THREATS.md), and the SIGINT/DF items to the
references at the end.

_Last updated: post-v1.2.0, at 268 tests. See [VISION.md](docs/VISION.md) for the
purpose/aim and UI positioning that steer this roadmap._

---

## Vision

RFHound is a **friendly, powerful, defensive** RF situational-awareness toolkit
for the HackRF (1 MHz – 6 GHz). It is an **orchestration layer**: it drives
best-of-breed SDR tools behind one guided interface, ships a frequency knowledge
base, and adds detection, analysis, automation, and reporting — so a user goes
from *"what's around me?"* to *"what is this signal?"* to *"decode / harden /
respond"* without stitching tools together by hand.

### Principles (do not drift from these)

1. **Receive-first.** Everything is receive-and-analyse. The only transmit path
   is gated **replay of your own capture** (consent + per-frequency allow-list +
   per-call `--authorized`).
2. **ES + EP, never EA.** RFHound covers Electronic **Support** (detect / measure
   / identify / locate) and Electronic **Protection** (recognise jamming/spoofing
   to defend). It never implements Electronic **Attack** — no jamming, spoofing,
   deception, RollJam, brute-force, IMSI-catcher, arbitrary/customizable
   transmitters, or active countermeasures. Enforced by tests; must stay that way.
3. **Runs without hardware.** Every scan supports `--simulate`; the suite runs
   green with no HackRF, and every new capability ships a simulator.
4. **Honest.** Never fake a decode/measurement. If a tool is missing, say so.
5. **Light core.** Only `rich` is a hard dependency; `numpy` is optional
   (`rfhound[iq]`). Heavy deps only as extras.

---

## The SIGINT capability model (the intelligence cycle)

RFHound is organised, implicitly, around the classic intelligence cycle. Naming
the stages shows what's built and what's missing. SIGINT = COMINT (comms) +
ELINT (non-comms/radar) + FISINT (telemetry); RFHound touches all three on the
**collection/analysis** side.

| Stage | What it means | RFHound today | Gap / roadmap |
|---|---|---|---|
| **Tasking** | Decide what to look for | band plan, `at`/`tune`, recon targets, automations | watchlists tied to EOB; standing collection plans |
| **Collection** | Receive the energy | sweep, capture (IQ+SigMF), decoders, multi-node hub | wideband survey scheduler; antenna/front-end guidance (below) |
| **Processing** | Turn RF into measurements | `iqtools` (bandwidth, modulation), pulse analysis, sweep peaks | live decode→structured-data pipeline; deinterleaving |
| **Exploitation / analysis** | Identify, characterise, locate | classifier, spoof/jam/rogue-BTS detection, emitter catalogue (EOB), RSSI geolocation | TDOA, DF (AoA), correlation across time, ML classifier |
| **Dissemination** | Get it to a decision-maker | reports (MD/HTML), dashboard + REST API, webhook alerts, hub state | NDJSON/SIEM feeds, PDF, GeoJSON/KML map export |

Discipline mapping: **COMINT** → decoders + interception detection; **ELINT** →
`sigint pulse` (PW/PRI), emitter catalogue, jamming characterisation; **FISINT**
→ TPMS/telemetry/ACARS decoding + ID tracking.

---

## Collection hardware & front-end requirements

What a real deployment needs beyond the HackRF — captured here so the software
can *guide* the operator (`doctor`/`setup` hints) and so DF/geolocation features
have a hardware target.

- **Antennas (band-appropriate is the #1 sensitivity factor):**
  - Sub-GHz ISM (315/433/868/915) — tuned whip / telescopic; a **band-pass filter**
    hugely helps in RF-dense sites.
  - Wideband survey — **discone** (very wide) or a log-periodic.
  - Directional / DF — **Yagi** (manual bearing), **Adcock** array (Watson-Watt),
    **circular arrays** (pseudo-Doppler / correlative interferometry).
  - ADS-B/GNSS/L-band — resonant 1090/1.5 GHz antennas; active GNSS patch.
- **Front-end:** **LNA** (raise weak signals above the HackRF's noise figure) +
  **bias-tee** to power it (already supported via `antenna_power`); **band-pass /
  notch filters** to stop strong out-of-band signals (FM, cellular, pagers) from
  desensitising or creating images.
- **Timing/frequency reference (critical for DF/TDOA):** an **external 10 MHz
  reference (GPSDO/OCXO)** shared across receivers for frequency coherence
  (surfaced via `device clock`), and a **PPS** mark for sample-time alignment.
- **Antenna switching:** **Opera Cake** (supported via `device operacake`) for
  automated multi-antenna / filter-bank scanning by frequency or time.
- **Multi-node:** ≥3 spatially separated, time/frequency-synchronised receivers
  for TDOA; the `hub`/`node` link is the transport.
- **TX resilience testing:** a **shielded enclosure / Faraday tent** — the only
  place gated replay testing belongs.

Roadmap: a **`doctor --rf` / knowledge-base "front-end guide"** that recommends
antenna + filter + LNA per target band, and flags when a strong out-of-band
signal is likely desensitising a capture.

---

## Direction finding & geolocation — methods & targets

Locating an emitter is the highest-value SIGINT capability RFHound is missing at
precision. Methods, their hardware cost, and RFHound's target:

| Method | Principle | Hardware | Accuracy | RFHound |
|---|---|---|---|---|
| **RSSI / power-on-arrival** | stronger receiver ≈ closer; weighted centroid | ≥2–3 positioned single-antenna nodes | coarse (100s m) | ✅ `sigint locate` |
| **Watson-Watt (Adcock)** | amplitude comparison on crossed pairs → bearing | Adcock array + coherent RX | ~1–5° | Later |
| **Pseudo-Doppler** | electronically "rotate" a circular array → Doppler phase → bearing | switched circular array | few ° | Later |
| **Correlative interferometry / MUSIC** | phase across baselines vs a reference manifold | multi-element array + multi-coherent RX | <1° (VHF/UHF) | Later (multi-HackRF, hard) |
| **TDOA multilateration** | time-difference of arrival at separated sites → hyperbolae | ≥3 synced nodes (PPS/GPSDO) | good with geometry | **Next** (headline) |
| **AoA + TDOA fusion** | combine bearings and TDOA; GDOP-aware | arrays + synced nodes | best | Later |

**TDOA — shipped** (`sigint locate --tdoa`, simulator-first). Detail:
- **Sync:** share a 10 MHz reference and a PPS mark; record short aligned IQ
  snippets at each node on a common trigger.
- **Measure:** cross-correlate node-pair captures → sub-sample TDOA (parabolic
  interpolation of the correlation peak).
- **Solve:** hyperbolic least-squares (Levenberg-Marquardt) for the emitter fix;
  report a confidence region from **GDOP** (geometry).
- **Deliver:** `sigint locate --tdoa`; nodes push timestamped snippets/TDOAs via
  the hub. **Simulator-first** (synthetic TDOAs from a known geometry) so it's
  fully testable without hardware. `numpy`-only; passive collection.
- **Acceptance:** on a simulated 4-node geometry, recover a known emitter to
  within the GDOP-predicted ellipse; degrade gracefully to RSSI with <3 nodes.

---

## Roadmap (themed, tiered, with acceptance criteria)

Tiers: **Now** · **Next** · **Later**. Each item: guardrail + acceptance criteria
(AC) + dependencies (dep).

### 1. Geolocation & direction finding
- **[Done] TDOA multilateration** — `sigint locate --tdoa`: cross-correlation
  TDOA estimation (sub-sample) + Gauss-Newton hyperbolic solve + GDOP confidence,
  simulator-first, RSSI fallback with <3 nodes. *Remaining:* deliver node
  snippets over the hub for a live multi-receiver fix (currently local/file/IQ).
- **[Done] Hub-delivered TDOA** — `sigint locate --tdoa --hub URL`: nodes push
  time-aligned IQ snippets (base64 ci8) or pre-computed TDOAs to the hub under a
  common *trigger*; the solver pulls, cross-correlates, and fixes. *Remaining:*
  real node-side sample alignment (PPS/GPSDO) and a triggered capture command.
- **[Later] POA+TDOA fusion; GeoJSON/KML export; confidence ellipses (GDOP).**
- **[Later] Single-node pseudo-DF** with a rotating/directional antenna (log
  power-vs-bearing). *Dep:* Opera Cake or a rotator; front-end guide.

### 2. Signal analysis & classification
- **[Now] Auto-fill `--mod` in `sweep --identify`.** Grab a short IQ snippet per
  strong peak → modulation detection → sharper classifier guess in one pass.
  *AC:* `--identify --measure` fills modulation for real captures; simulated path
  tested. *Dep:* `iqtools`.
- **[Next] Analog-vs-digital + duty-cycle/periodicity classifiers.** Identify
  polling sensors (regular bursts), continuous vs bursty. *AC:* labels on
  synthetic burst/continuous signals.
- **[Next] Channel-plan snapping.** Snap measured bandwidth/step to known
  channelisation (12.5/25 kHz LMR, 200 kHz GSM, LoRa BW) to narrow the guess.
- **[Later] Optional ML modulation classifier** as a plugin extra (never a hard
  dep). *Dep:* a small shipped/trainable model.

### 3. Decoders & protocol coverage
- **[Next] Live decoder → detector/sightings/EOB wiring.** Stream `rtl_433` /
  `dump1090` / AIS JSON straight into spoof-detection, `track`, and the emitter
  catalogue in real time. *AC:* a decode session updates spoof-check + EOB live.
- **[Next] More recipes:** Meshtastic/LoRa PHY, Z-Wave (908.42/868.42), wM-Bus
  (EU meters), Inmarsat STD-C (JAERO), ADS-C. *AC:* each recipe + doctor hint +
  DECODERS.md row.
- **[Later] IQ-file decoding** where the tool supports it (`rtl_433 -r`, URH CLI).

### 4. Detection & SIGINT depth (traces to THREATS.md gaps)
- **[Done in 1.2.0] Emitter-catalogue intelligence (new-emitter alerting).**
  The automation `emitters` task sweeps a range, ingests peaks into the catalogue
  (EOB), and alerts when a genuinely new emitter appears. *Remaining:* power-trend
  / on-off-pattern tracking, and a dashboard EOB panel (below).
- **[Next] Jamming characterisation from IQ.** Feed `sigint jamming` an IQ capture
  to catch **swept/chirp** and **pulsed** jammers (via hop + pulse analysers).
- **[Next] Correlated RollJam detector.** Fuse `defense monitor` (jam) + a fob
  press in time → flag the jam-then-capture pattern. *AC:* simulated trace flags.
- **[Done in 1.2.0] GNSS interference monitor** — `sigint gnss`: passive GPS
  jamming/spoofing indicators (C/N0 collapse/uniformity, AGC spike, elevation
  decorrelation, position/time jump, static-move) + L1 IQ carrier check +
  simulators; also an automation `gnss` task. **Detection only — never TX.**
- **[Later] Cellular downgrade detection.** Flag 2G-forcing / re-selection
  patterns alongside the existing rogue-BTS indicators.
- **[Later] Selective-jamming detection** (LoRaWAN/others): jamming synced to
  specific frames.

### 5. Platform, integration & ops
- **[Now] Alerting expansion.** SMTP email alongside webhooks; templated payloads
  for SIEM/chat. *AC:* automation fires an email in a test SMTP.
- **[Next] NDJSON streaming API + optional token auth** on web + hub for SIEM.
- **[Next] Packaging & deployment:** **PyPI**, a **Docker image**, **systemd
  units** for hub + automation scheduler (unattended sensor node).
- **[Later] PDF situational-awareness reports** (extend the report generator).
- **[Later] Persistent spectrum-survey store** (occupancy DB + timeline view).

### 6. UX & dashboard
- **[In progress — v1.3] Ground-up dashboard rebuild** (SDR-software-inspired,
  see [VISION.md](docs/VISION.md)): receiver bar with big frequency readout +
  band presets + step controls; larger spectrum/waterfall with dB/frequency
  axes and a hover cursor; **capture panel**, **recordings**, **emitter/EOB**,
  and **sightings** panels; keep token auth, sim/live, export, drawer, theme.
- **[Done in 1.2.0] Dashboard auth + bookmark add/edit** (token-gated writes),
  theme toggle, S-meter scale + peak-hold, waterfall colormaps, per-panel export,
  peak detail drawer.
- **[Next] Config wizard** (`rfhound config wizard`).
- **[Next] Front-end guide** surfaced in `doctor --rf`/knowledge base
  (antenna/filter/LNA per band).
- **[Later] Deeper URH/inspectrum handoff** from a recording.

### 7. Quality & release
- **[Done in 1.1.0] `test_frequency_accuracy.py`** (canonical freqs locked).
- **[Done] v1.1.0** cut with CHANGELOG.
- **[Now] Tag v1.1.0 on GitHub** (blocked locally by proxy on tag refs — needs a
  maintainer click, or a later retry).
- **[Next] CI badge + coverage; `CONTRIBUTING.md`; publish THREATS.md link** in
  README.
- **[Ongoing] Keep the suite green + flake8-clean on every change; every new
  capability ships a `--simulate` path and tests.**

---

## Explicitly out of scope (won't build)

To keep future-me honest: **Electronic Attack and offensive transmit.** No
jammers, no barrage/spot/swept/pulsed jamming *generators*, no GPS/ADS-B/AIS/EPIRB
**spoofers**, no RollJam/RollBack tooling, no code brute-forcers, no IMSI
**catcher**, no SS7/Diameter tooling, no arbitrary/customizable **transmitters**,
no drone takeover / active RF countermeasures. RFHound *detects, measures,
characterises, and locates* these threats so a defender can respond — it never
becomes the weapon. Requests to add them get the same answer regardless of
framing. The threat descriptions in [`docs/THREATS.md`](docs/THREATS.md) are
defensive threat-modelling, not attack how-tos.

---

## Near-term queue — the v1.3 "rebuild & beef up" push

Shipped in this push:
1. ✅ **Dashboard capture panel** + `POST /api/capture` (receive-only,
   token-gated), and **recordings / emitters (EOB) / sightings** endpoints + panels.
2. ✅ **Ground-up dashboard UI/UX rebuild** (receiver bar, band presets, axed
   spectrum, hover cursor, click-to-inspect) — see [VISION.md](docs/VISION.md).
3. ✅ **Front-end guide** (`doctor --rf [--freq]`): antenna/filter/LNA per band.
4. ✅ **Config wizard** (`rfhound config wizard`).
5. ✅ **Email (SMTP) alerting** (`automate add … --email`, `config smtp`) +
   **NDJSON** streaming feed (`automate run --ndjson`).
6. ✅ **GeoJSON export** for `sigint locate` fixes (`--geojson`).
7. ✅ **Docker + systemd** packaging (`Dockerfile`, `docker-compose.yml`,
   hardened units in `deploy/`) for unattended sensor nodes. *(PyPI publish TBD.)*

Also shipped in this push:
- ✅ **Jamming characterisation from IQ** (`sigint jamming --file`) — swept/chirp,
  pulsed, barrage & spot/CW from a capture's spectrogram.
- ✅ **Correlated RollJam detector** (`defense rolljam-check`) — jam + fob press
  fused on a timeline.
- ✅ **Live decode → EOB** (`decode run --eob`) + the existing `--track` sightings
  wiring.

Still open (next):
- **PyPI publish** (needs maintainer credentials).
- **PDF situational-awareness reports**; **KML** alongside GeoJSON.
- ML modulation classifier (plugin extra); AoA/DF; deeper URH handoff.

---

## References

- SIGINT disciplines & cycle — [Trenton Systems](https://www.trentonsystems.com/en-us/resource-hub/blog/sigint-vs-comint-vs-elint) ·
  [Naval War College](https://usnwc.libguides.com/c.php?g=494120&p=3381559) ·
  [Maltego collection disciplines](https://www.maltego.com/blog/understanding-the-different-types-of-intelligence-collection-disciplines/)
- Direction finding & geolocation — [Rohde & Schwarz DF methodologies](https://cdn.rohde-schwarz.com/am/us/campaigns_2/a_d/Intro-to-direction-finding-methodologies.pdf) ·
  [CRFS AoA/DF](https://pages.crfs.com/hubfs/whitepapers/Angle%20of%20Arrival-Direction%20Finding.pdf) ·
  [CRFS DF for EW/SIGINT](https://www.crfs.com/blog/radio-direction-finding-techniques-and-applications-for-ew-and-sigint)
- Threat sources — see [`docs/THREATS.md`](docs/THREATS.md) references.
