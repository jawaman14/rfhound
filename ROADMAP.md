# RFHound roadmap

A living plan for the project — where it is, how it got here, and where it's
going. This is the working reference I (and any contributor) steer by. It is
intentionally opinionated about scope.

_Last updated: post-v1.0, at 197 tests._

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
   transmitters, or active countermeasures. This boundary is enforced by tests
   and must stay that way.
3. **Runs without hardware.** Every scan supports `--simulate`; the suite runs
   green with no HackRF.
4. **Honest.** Never fake a decode/measurement. If a tool is missing, say so.
5. **Light core.** Only `rich` is a hard dependency; `numpy` is optional
   (`rfhound[iq]`). Keep it that way — add heavy deps only as extras.

---

## Current state (v1.0.0)

Shipped and tested (197 tests, flake8-clean, MIT, standalone repo):

- **Orientation:** band plan (1 MHz–6 GHz) + ITU designations, `at` (freq→tools),
  `tune` (protocol→freq), knowledge base, bookmarks.
- **Spectrum:** sweep + peak detection + `--identify`, recon survey, live
  `--watch`, web dashboard (spectrum + waterfall + S-meter + threat KPIs +
  bookmarks + click-to-tune) + REST API.
- **Signal ID:** heuristic classifier (freq/bandwidth/modulation), IQ analysis
  (`iqtools`: measured bandwidth + modulation detection), recordings catalog
  (captures that store their classification + decode settings).
- **Decoders:** ~19 receive-only recipes; `decode run --track`.
- **Detection (EP):** jamming/interference, replay, rolling-code, ADS-B/AIS
  spoofing, counter-UAS, frequency-hopping, rogue-BTS/IMSI-catcher, TSCM
  baseline-diff; response playbooks.
- **SIGINT (ES):** ELINT pulse analysis (PW/PRI), jamming characterisation,
  emitter catalogue / EOB, multi-node RSSI geolocation.
- **Tracking:** decoded-ID sightings (ICAO/MMSI/sensor/capcode).
- **Platform:** LLM copilot (`ai` console + `ask`), automation engine + console
  (scheduled tasks, triggers, webhook alerting), multi-node hub/node linking,
  mods/plugins, GNU Radio flowgraph presets, dev + global-simulate modes.
- **HackRF hardware:** gains, amp, bias-tee, baseband filter, ppm, device serial,
  Opera Cake antenna switch, external clock.

---

## Roadmap

Tiers: **Now** (next few iterations) · **Next** (planned) · **Later** (aspirational).
Each item notes the guardrail it must respect.

### 1. Geolocation & direction finding

- **[Next] TDOA multilateration (precise geolocation).** The upgrade from the
  current RSSI-weighted centroid. Approach:
  - Synchronise receivers: share a **10 MHz reference** (HackRF external clock
    input — already surfaced via `device clock`) and/or a **PPS/GPSDO** time
    mark; record aligned IQ across ≥3 nodes.
  - Cross-correlate the shared captures to estimate **time difference of arrival**
    per node pair; solve the hyperbolic system for an emitter fix.
  - Deliver via the hub: nodes push timestamped IQ snippets / TDOA measurements;
    a `sigint locate --tdoa` mode does the multilateration.
  - Needs `numpy`; correlation + least-squares solve. Ship with a simulator
    (synthetic TDOAs from known geometry) so it's testable without hardware.
  - Guardrail: passive collection only.
- **[Later] Power-on-arrival + map export.** Fuse RSSI and TDOA; export fixes as
  GeoJSON/KML for mapping. Confidence ellipses from geometry (GDOP).
- **[Later] Single-node pseudo-DF** with a rotating/directional antenna: log
  power-vs-bearing to estimate a bearing from one site.

### 2. Signal analysis & classification

- **[Now] Auto-fill `--mod` in `sweep --identify`.** Grab a short IQ snippet per
  strong peak, run modulation detection, feed it back into the classifier for a
  sharper guess in one pass.
- **[Next] Analog-vs-digital + duty-cycle/periodicity classifiers.** Identify
  polling sensors (regular bursts), continuous vs bursty, analog vs digital —
  extend `iqtools`/`classify`.
- **[Next] Channel-plan snapping.** Snap a measured bandwidth/step to a known
  channelisation (12.5/25 kHz LMR, 200 kHz GSM, LoRa BW) to narrow the guess.
- **[Later] Optional ML modulation classifier** as a plugin extra (keeps core
  light). Train/ship a small model; never a hard dependency.

### 3. Decoders & protocol coverage

- **[Next] Live decoder → detector/sightings/EOB wiring.** Stream `rtl_433` /
  `dump1090` / AIS JSON directly into spoof-detection, the sightings tracker, and
  the emitter catalogue in real time (today `decode --track` covers sightings;
  extend to detectors + EOB).
- **[Next] More recipes:** Meshtastic/LoRa PHY, Z-Wave (US 908.42 / EU 868.42),
  rtl_amr wmbus (smart meters, EU), inmarsat STD-C (JAERO), HDLC/ADS-C.
- **[Later] IQ-file decoding path.** Where a tool supports it (`rtl_433 -r`,
  URH CLI), decode directly from a recording, not just live RF.

### 4. Detection & SIGINT depth

- **[Next] Emitter-catalogue intelligence.** Alert on a *new* emitter vs a saved
  EOB baseline (TSCM at the emitter level); track an emitter's on/off pattern and
  power trend over time; tie into automation.
- **[Next] Jamming characterisation from IQ.** Feed `sigint jamming` an IQ
  capture (not just a sweep) to detect swept/chirp and pulsed jammers via the
  hopping + pulse analysers.
- **[Later] GNSS interference monitor.** Passive detection of GPS
  jamming/spoofing indicators (C/N0 anomalies) if a GNSS front-end feed is
  available. Detection only — never TX.

### 5. Platform, integration & ops

- **[Now] Alerting expansion.** Add email (SMTP) alongside webhooks in the
  automation engine; templated alert payloads for SIEM/chat.
- **[Next] NDJSON streaming API + tokened auth** on the web server and hub for
  real SIEM feeds; optional read auth.
- **[Next] Packaging & deployment:** publish to **PyPI**; a **Docker image**;
  **systemd units** for the hub and the automation scheduler so a sensor node
  runs unattended.
- **[Later] PDF situational-awareness reports** (extend the Markdown/HTML report
  generator).
- **[Later] Persistent spectrum-survey store** (long-term occupancy DB) with a
  timeline view.

### 6. UX & dashboard

- **[Now] Dashboard: live decode output panel + demod one-click presets;** surface
  the emitter catalogue and sightings as panels (endpoints exist / are cheap).
- **[Next] Config wizard** (`rfhound config wizard`) for first-run gains,
  output dir, LLM/hub settings.
- **[Next] Dashboard bookmarks add/edit** (currently read-only on the web; keep
  writes gated + optional-auth).
- **[Later] Deeper URH/inspectrum handoff** buttons/links from a recording.

### 7. Quality & release

- **[Now] `test_frequency_accuracy.py`** — assert canonical frequencies (ADS-B
  1090/978, AIS 161.975/162.025, WSPR 14.0956, GPS 1575.42, NOAA APT 137.100,
  ISM 315/433.92/868.3/915…) so the charts can't silently drift.
- **[Now] Tag v1.1.0** with a CHANGELOG entry covering everything since 1.0:
  SIGINT/EW-support, automation, AI console, recordings, ID tracker, emitter
  catalogue, HackRF Opera Cake/clock, dashboard S-meter/bookmarks, classifier +
  IQ modulation detection.
- **[Next] CI badge + coverage;** contributor guide (`CONTRIBUTING.md`).
- **[Ongoing] Keep the suite green and flake8-clean on every change.**

---

## Explicitly out of scope (won't build)

To keep future-me honest: **Electronic Attack and offensive transmit.** No
jammers, no barrage/spot/swept/pulsed jamming *generators*, no GPS/ADS-B/AIS/EPIRB
**spoofers**, no RollJam, no code brute-forcers, no IMSI **catcher**, no SS7
tooling, no arbitrary/customizable **transmitters**, no drone takeover / active
RF countermeasures. RFHound *detects, measures, characterises, and locates* these
threats so a defender can respond — it never becomes the weapon. Requests to add
them get the same answer regardless of framing.

---

## Near-term next steps (concrete queue)

1. Cut **v1.1.0** (+ CHANGELOG) and add `test_frequency_accuracy.py`.
2. **Auto-fill `--mod`** in `sweep --identify`.
3. **Email alerting** in automation; NDJSON + optional auth on hub/web.
4. **TDOA** module (simulator-first), delivered through the hub.
5. Dashboard: **live decode + emitter/sightings panels**.
