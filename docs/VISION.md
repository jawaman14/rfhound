# RFHound — purpose, aim & positioning

_The "why" that steers every feature and UI decision. Read this before a big
change; if a proposed feature doesn't serve the purpose below, it probably
doesn't belong._

## One sentence

**RFHound turns a wall of raw spectrum into decisions** — it tells you *what's
around you*, *what a signal is*, and *how to decode, harden, or respond* — on a
HackRF, receive-first, without stitching a dozen tools together by hand.

## The aim

Give a security-minded operator (pentester, blue-team, researcher, hobbyist) a
**single guided console** for RF situational awareness and defensive SIGINT:

1. **See** — survey the spectrum and know what's transmitting (sweep, recon,
   waterfall, emitter catalogue).
2. **Identify** — turn RF into meaning (classifier, IQ measurement, decoders,
   ITU/band knowledge base).
3. **Detect** — recognise threats: jamming, spoofing (ADS-B/AIS/GNSS), rogue base
   stations, drones, frequency hopping, replay.
4. **Locate** — direction-find / geolocate emitters (RSSI, TDOA multilateration).
5. **Respond** — playbooks, hardening advice, authorized replay of your *own*
   capture for testing your *own* gear.
6. **Operate** — automate all of the above on a schedule, alert into a SIEM, run
   as an unattended sensor, and report.

Everything maps onto the classic **intelligence cycle** (task → collect →
process → exploit → disseminate). That's the mental model the product and its UI
are organised around.

## What RFHound is *not* (positioning vs other SDR software)

RFHound deliberately is **not** a live-audio SDR receiver, and the UI should not
pretend to be one.

| Tool | What it is | RFHound's difference |
|---|---|---|
| SDR#, SDRuno, GQRX, CubicSDR | Real-time tune-and-listen receivers (demod audio) | RFHound *surveys, detects, and analyses*; it drives decoders rather than demodulating audio live |
| SDRangel | Multi-channel SDR workbench | RFHound is opinionated and defensive: a curated workflow, not a construction kit |
| SatDump | Satellite downlink processing | Overlaps only on IQ handling; RFHound is terrestrial situational awareness |
| URH / inspectrum | Deep single-signal reverse engineering | RFHound *points you at them* with a capture + classification, then hands off |
| Kismet | Wi-Fi/BT wardriving | RFHound is sub-6 GHz RF-general and threat-detection-first |

**What we borrow from them for the UI:** the spectrum+waterfall as the
centerpiece with real dB/frequency axes and an interactive tuning cursor;
click-to-tune and drag-to-zoom; a receiver bar with a large frequency readout,
step controls, and band presets; an S-meter; memory/bookmarks. **What we keep
that's ours:** the intelligence-cycle organisation, threat KPIs, the emitter
catalogue (EOB), sightings, the knowledge base, and receive-first safety.

## Principles (do not drift)

1. **Receive-first.** The only transmit path is gated replay of your own capture
   (consent + per-frequency allow-list + per-call `--authorized`, safety-of-life
   bands hard-refused, duration-capped, audited). No EA, ever.
2. **ES + EP, never EA.** Detect / measure / identify / locate / protect — never
   jam, spoof, or attack. Enforced by tests.
3. **Runs without hardware.** Every capability ships a `--simulate` path and
   tests; the suite is green with no HackRF.
4. **Honest.** Never fake a decode or measurement. If a tool is missing, say so.
5. **Light core.** `rich` is the only hard dependency; `numpy` is an optional
   extra (`rfhound[iq]`). Heavy deps only as extras.
6. **One coherent surface.** CLI, interactive menu, and web dashboard reach the
   same capabilities and stay in step.

## Success looks like

- A newcomer runs `rfhound` (menu) or `rfhound web`, and within a minute
  understands what's on the air around them and what to do next.
- A blue-teamer wires `rfhound automate` into a SIEM and gets actionable RF
  alerts (jamming, spoofing, rogue BTS, new emitters) with a defensible audit
  trail.
- A researcher captures a signal, gets a confident classification and the exact
  decoder command, and hands the IQ to URH — all without leaving the console.
- Nothing in the product can be turned into a weapon.
