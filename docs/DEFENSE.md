# Defensive module — detect attacks & harden devices

The `rfhound defense` commands are the "build protections" half of RFHound. They
help you **detect** RF attacks and **assess and harden** your own devices. They
are receive-and-analyse only, except the resilience harness, which reuses the
separate, safety-gated *replay-of-your-own-capture* path.

> **By design, RFHound ships no jammer/DoS transmitter, no RollJam
> capture-and-replay attack, and no brute-force code generator.** These are RF
> denial-of-service and access-control-defeating attack primitives; they are out
> of scope regardless of environment. Crucially, a defence program does not need
> them — everything you need to *detect* and *harden against* those attacks is
> here. See [`LEGAL.md`](LEGAL.md).

## 1. Jamming / interference detection — `defense monitor`

Learns a baseline noise floor for a band, then alarms when the floor rises
(classic jamming) or when expected signals disappear (desense). This is the
actual capability a defender needs to *detect* an RF DoS attack.

```bash
rfhound defense monitor 433 435 --threshold 10 --samples 20
rfhound defense monitor 433 435 --simulate      # models a jammer switching on
```

Deploy it as a continuous watch on a band your devices rely on (garage/gate
receivers, sensors) and route alarms to your monitoring stack.

## 2. Replay-attack detection — `defense replay-check`

Analyses a stream of observed transmissions and flags replay signatures:
identical payloads on a device that should roll its code, or the same fixed code
repeated faster than a human could press a button.

Input file: one observation per line, `timestamp payload`:

```
1712000000.0 a1b2c3
1712000000.4 a1b2c3
1712000000.7 a1b2c3
```

```bash
rfhound defense replay-check --file observations.txt
rfhound defense replay-check --file observations.txt --fixed   # fixed-code device
rfhound defense replay-check --simulate
```

Pair it with a decoder (e.g. pipe `rtl_433 -F json` payloads into this format) to
get runtime replay alerts.

## 2b. RollJam correlation — `defense rolljam-check`

RollJam jams a fob's band *while* you press it, capturing the rolling code under
cover (your car doesn't unlock, so you press again — and the attacker keeps the
first code). This fuses jamming events and fob presses on a timeline and flags a
**press under active jamming** — and, the strongest signature, **two such presses
close together**.

```bash
rfhound defense rolljam-check --simulate
rfhound defense rolljam-check --file trace.json
#   trace.json: [{"t":10,"kind":"jam","freq_mhz":433.92,"duration_s":6},
#                {"t":11,"kind":"press","freq_mhz":433.92}, ...]
```

Detection only — RFHound never jams or replays a captured code.

## 3. Rolling-code posture assessment — `defense rolling-assess`

Capture a handful of presses of the **same button** on a device you're
authorized to assess, then classify it: fixed vs rolling, whether a "rolling"
code looks like a thinly-masked counter, and a 0–100 resilience score with
concrete hardening recommendations. Passive analysis — it reports weaknesses and
produces no attack.

Input file: one captured payload (hex or bits) per line.

```bash
rfhound defense rolling-assess --file captures.txt
rfhound defense rolling-assess --simulate --kind fixed     # demo: weak device
rfhound defense rolling-assess --simulate --kind rolling   # demo: strong device
```

## 4. Lab resilience harness — `defense resilience`

Structures a resilience test of **your own** device and turns the result into a
hardening report. The active step (transmitting) is the *separate, gated* replay
of a capture you made, inside your RF enclosure:

```bash
# 1) capture your device (your own remote), inside the tent
rfhound capture 433.92 5 --name myfob

# 2) enable gated transmit for the band, then replay your capture at your device
rfhound tx enable --allow 433.0-434.8
rfhound replay <captures>/myfob.sigmf-data --authorized

# 3) tell the harness what happened, get a hardening report
rfhound defense resilience --device myfob --payloads captures.txt \
    --replayed --actuated true
```

If the device actuates on a replayed capture, it doesn't enforce freshness and is
replay-vulnerable; the report recommends an authenticated rolling counter /
challenge-response and runtime replay + RollJam detection.

```bash
rfhound defense resilience --device demo --simulate    # end-to-end demo
```

## 5. TSCM baseline diff — `defense baseline`

Counter-surveillance ("bug sweep"). Record a **known-good** spectrum of a room /
site, then diff a fresh sweep against it to surface emitters that are **new** or
**notably stronger** — the signature of a planted transmitter or a new rogue
device.

```bash
rfhound defense baseline save 88 960 --out room-clean.json   # capture known-good
# ...later / periodically...
rfhound defense baseline diff room-clean.json --threshold 10
rfhound defense baseline diff room-clean.json --simulate      # demo (injects a bug)
```

## 6. Spoof detection — `defense spoof-check`

The defensive counterpart to Mayhem's ADS-B/AIS transmitters. Feed in decoded
messages (JSON array) and RFHound flags spoofing indicators: **ghost aircraft /
teleporting tracks** (position jumps implying impossible speed), **impossible
altitude**, **duplicate identities** (one ICAO from two places at once), and for
AIS **invalid MMSI** + impossible vessel motion.

```bash
rfhound defense spoof-check adsb --file adsb-messages.json
rfhound defense spoof-check ais  --file ais-messages.json
rfhound defense spoof-check adsb --simulate     # demo with a ghost aircraft
```

ADS-B message objects use `icao, t, lat, lon, alt, speed`; AIS uses
`mmsi, t, lat, lon, sog`. Wire your decoder's JSON output into this for a live
spoofing monitor.

## 7. Counter-UAS detection — `defense drone-scan`

Detection-only. Sweeps the common drone control/video bands (900 MHz, 1.2/1.3
GHz, 2.4 GHz, 5.8 GHz) and reports activity with a coarse confidence. This finds
*presence* of drone RF; it does not jam or take over anything.

```bash
rfhound defense drone-scan
rfhound defense drone-scan --simulate
```

## 8. Frequency-hopping detection — `defense hop-detect`

Spot frequency-agile / covert emitters that hop across channels to evade a
fixed-tuned listener. Analyses peak frequencies across successive sweeps and
flags a pattern of many short-lived (transient) frequencies.

```bash
rfhound defense hop-detect --simulate
```

## 9b. Rogue base station / IMSI-catcher detection — `defense imsi-detect`

The **defensive** counterpart to an IMSI catcher (SnoopSnitch / EFF Crocodile
Hunter approach). RFHound does not impersonate a network or intercept anyone — it
ingests observed cellular broadcast parameters and flags the classic indicators
of a fake base station: **no/weak encryption (A5/0), empty neighbor list,
unusual/changing LAC, an implausibly strong new cell, unexpected operator, or a
Cell-ID reused across frequencies.**

```bash
rfhound defense imsi-detect --simulate            # demo with a planted catcher
rfhound defense imsi-detect --file cells.json     # your observed cell records
```

`cells.json` is an array of objects with fields like `rat, mcc, mnc, lac, cid,
arfcn, rxlev, cipher, neighbors`. RFHound does **not** demodulate cellular itself
(use gr-gsm / a supported baseband to produce the observations) and performs no
cellular transmission of any kind. **SS7 / network-side location is out of scope**
— that's carrier-network interception, not RF, and not something this tool does.

## 9. Counter-threat playbooks — `defense respond`

Every threat RFHound detects has a **defensive** response playbook: immediate
actions, evidence to preserve, mitigations to harden the target, and when to
escalate.

```bash
rfhound defense respond jamming
rfhound defense respond gps_spoof
rfhound defense respond drone        # threats: jamming, gps_spoof, adsb_spoof,
                                     # ais_spoof, drone, rogue_emitter, replay
```

> These are blue-team actions — alert, record, harden, escalate. RFHound
> provides **no active RF countermeasures** (jam-back, spoof-back, drone
> takeover); those are offensive, usually illegal for non-government operators,
> and are a decision for authorised personnel with purpose-built equipment.

## Turning findings into protections

| Finding | Hardening action |
|---|---|
| Fixed code / replay-vulnerable | Move to authenticated rolling code or challenge-response; receiver rejects reused codes |
| "Rolling" code is really a counter | Use a cryptographic hop with good avalanche; validate a forward-only window |
| Jamming detected | Alarm + fail-safe behaviour; diversity/redundancy; detect jam-then-press (RollJam) |
| Replays seen in the wild | Rate-limit, nonce/timestamp validation, alerting |
