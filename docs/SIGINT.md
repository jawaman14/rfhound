# SIGINT / EW-support tools

The collection-and-analysis side of electronic warfare — **Electronic Support
(ES)** and **Electronic Protection (EP)**. All receive-and-analyse.

> **Scope.** RFHound covers ES (detect/measure/identify/locate emitters) and EP
> (recognise how you're being jammed so you can defend). It deliberately does
> **not** implement **Electronic Attack (EA)** — jamming, spoofing, deception,
> DoS. It characterises a jammer so you can respond; it never becomes one. See
> [LEGAL.md](LEGAL.md).

## ELINT pulse analysis — `sigint pulse`

Measure a pulsed emitter's parameters from an IQ capture: pulse width (PW),
pulse repetition interval (PRI), jitter and duty, and classify it (regular-PRI
radar/beacon-like, irregular, or continuous wave).

```bash
rfhound capture 3000 2 --name radar     # capture the emitter first
rfhound sigint pulse --file <captures>/radar.sigmf-data
# → Classification: pulsed — regular PRI (radar/beacon-like)
#   9 pulses, PW~50us, PRI~1000us (jitter 0us), duty 0.01
```

Needs NumPy (`pip install rfhound[iq]`).

## Interference / jamming characterisation — `sigint jamming`

Classify the *type* of interference on a band (EP): **barrage** (broadband
noise), **spot** (a single dominant carrier), **multi-tone**, or **none**.

```bash
rfhound sigint jamming 433 435
rfhound sigint jamming 433 435 --simulate
```

Pair it with `defense monitor` (which *detects* jamming) — this tells you *what
kind*, which drives the right anti-jam response.

**From an IQ capture** (`--file`) it also catches jammers a single sweep misses —
**swept/chirp** (the peak frequency drifts across the band) and **pulsed** (energy
toggles on/off) — via the capture's spectrogram, alongside barrage and spot/CW:

```bash
rfhound sigint jamming --file <captures>/jammer.sigmf-data
rfhound sigint jamming --iq-kind swept    # demo on synthetic IQ (no capture)
```

Needs NumPy (`pip install rfhound[iq]`). A noise-like capture reads as barrage —
confirm it's jamming (not ambient) against a quiet baseline (`defense baseline`).

## Emitter catalogue / Electronic Order of Battle — `sigint emitters`

A persistent catalogue of observed emitters with their parameters (frequency,
ITU band, max power, bandwidth, likely type, first/last-seen, count) — an
Electronic Order of Battle built up from sweeps.

```bash
rfhound sigint emitters --scan 430 440    # sweep, ingest peaks, then list
rfhound sigint emitters                    # show the catalogue
rfhound sigint emitters --clear            # reset
```

Stored in `~/.config/rfhound/emitters.json`.

## Multi-node RSSI geolocation / DF — `sigint locate`

Estimate an emitter's position from several receivers' signal-strength reports
(an RSSI-power-weighted centroid). It sharpens with more, well-separated
receivers — pair it with the [multi-node hub](MULTINODE.md).

```bash
rfhound sigint locate --simulate
rfhound sigint locate --file reports.json   # [{"node","lat","lon","rssi"}, ...]
# → Estimated position: 51.512, -0.105 (55% · 3 receivers)
```

A single receiver's RSSI cannot localise; this needs ≥2–3 positioned receivers.

## GNSS jamming & spoofing detection — `sigint gnss`

Electronic **Protection** for GNSS: ingest a receiver's observations — per-satellite
C/N0, AGC, position/time, satellite elevations — and flag the indicators of
**jamming** (denial) and **spoofing** (a false position/time). Receive-and-analyse
only; RFHound **never** transmits on GNSS frequencies (see [LEGAL.md](LEGAL.md)).

What it looks for:

| Indicator | Signature | Verdict |
|-----------|-----------|---------|
| `fix-loss` / `low-cn0` | C/N0 collapse, fix dropped | jamming |
| `agc-spike` | receiver AGC jumps (front-end desense) | jamming |
| `uniform-cn0` | many sats at near-identical, high C/N0 | spoofing |
| `elevation-decorrelation` | C/N0 doesn't rise with elevation | spoofing |
| `position-jump` | impossible speed between fixes | spoofing / meaconing |
| `static-moved` / `location-mismatch` | fixed receiver "moves", or disagrees with a known site | spoofing |

```bash
rfhound sigint gnss --simulate nominal        # healthy constellation
rfhound sigint gnss --simulate jamming        # C/N0 collapse + AGC spike + fix loss
rfhound sigint gnss --simulate spoofing --static

# From real receiver logs (NMEA/UBX exported to JSON):
rfhound sigint gnss --file observations.json --static
#   observations.json: [{"t","lat","lon","alt","cn0":[...],
#                        "elevations":[...],"agc","num_sats","fix"}, ...]
rfhound sigint gnss --file observations.json --known 51.5 -0.12   # known site

# Light L1 IQ check — genuine GPS sits *below* the noise floor, so a carrier
# or elevated in-band power at 1575.42 MHz is itself suspicious:
rfhound capture 1575 2 --name l1
rfhound sigint gnss --iq <captures>/l1.sigmf-data --sample-rate 2000000
```

Use `--static` for a fixed installation (any reported movement is spoofing) or
`--known LAT LON` when the true position is known. Pair with the TDOA module to
*locate* a spoofer/jammer, and with `defense respond gps_spoof` for the playbook.
The L1 IQ check needs NumPy (`pip install rfhound[iq]`).

Add `--json` for machine-readable output (SIEM/automation); a non-nominal verdict
exits non-zero, so it drops straight into a monitoring pipeline:

```bash
rfhound sigint gnss --file observations.json --static --json || alert "GNSS integrity"
```

### Precise fixes — TDOA multilateration — `sigint locate --tdoa`

For a precise fix, use **time-difference-of-arrival** across ≥3 *synchronised*
receivers (shared 10 MHz reference + PPS). RFHound cross-correlates each node's
IQ snippet against a reference node (sub-sample parabolic interpolation),
estimates the TDOAs, and solves the hyperbolic system (Gauss-Newton least
squares) for the emitter position — with a **GDOP**-based confidence radius from
the geometry.

```bash
rfhound sigint locate --tdoa --simulate
# → Estimated position: 51.5100, -0.1181 (tdoa)
#   4 nodes · ±24.8 m · GDOP 0.83 · residual 2.0 m · multilateration over 4 nodes

rfhound sigint locate --tdoa --file nodes.json
#   nodes.json: [{"node","lat","lon","tdoa_s"}, ...]  (reference node tdoa_s = 0)
```

**Hub-delivered (distributed) TDOA.** Several nodes push a time-aligned IQ
snippet to a [hub](MULTINODE.md) for a common collection *trigger*; the solver
pulls them, measures the TDOAs by cross-correlation, and computes the fix:

```bash
rfhound hub --port 8787                                   # run the aggregator
# each node (on a shared PPS/10 MHz trigger) pushes its snippet via the API...
rfhound sigint locate --tdoa --hub http://HUB:8787        # pull latest trigger + solve
rfhound sigint locate --tdoa --hub http://HUB:8787 --simulate  # seed + solve (demo)
rfhound sigint locate --tdoa --hub http://HUB:8787 --trigger run1   # a specific event
```

Real deployments must **sample-align** the snippets (shared 10 MHz reference +
PPS) — see the [ROADMAP](../ROADMAP.md) hardware-sync notes.

Provide `tdoa_s` per node (arrival time relative to the reference), or feed
time-aligned IQ snippets and let RFHound measure the TDOAs by cross-correlation.
With fewer than 3 synchronised nodes it **degrades gracefully to the RSSI
centroid**. Needs NumPy (`rfhound[iq]`). Passive collection only — RFHound never
transmits. See the [ROADMAP](../ROADMAP.md) DF/geolocation section for the
hardware sync requirements.
