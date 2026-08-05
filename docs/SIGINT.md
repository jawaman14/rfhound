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
(For precise fixes, TDOA with synchronised receivers is the next step.)
