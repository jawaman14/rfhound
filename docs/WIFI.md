# Wi-Fi 2.4 & 5 GHz channel survey

A **receive-only** spectrum view of the Wi-Fi bands. It answers the practical
questions — *which channels are busy, how congested is each one, and where
should I move my AP for a clean channel?* — by sweeping the ISM / U-NII bands
with the SDR and scoring per-channel occupancy.

> **Scope & guarantees.** This is a **PHY-level occupancy view** (how much RF
> energy sits in each 20 MHz channel), not an 802.11 frame decoder — it does
> **not** read SSIDs/BSSIDs or associated clients. For frame-level work use a
> monitor-mode Wi-Fi NIC (e.g. Kismet). Like the rest of RFHound this is
> **receive-and-analyse only**: there is **no** Wi-Fi transmit, deauth, or
> jamming capability, by design. See [LEGAL.md](LEGAL.md).

Everything here works with no hardware via `--simulate` (or the global
`rfhound --simulate …`), which drives the synthetic sweep generator.

## Channel plan — `wifi channels`

List the channels RFHound knows about. DFS (radar-shared) 5 GHz channels are
flagged; the non-overlapping 2.4 GHz channels (1/6/11) are noted.

```bash
rfhound wifi channels                # both bands
rfhound wifi channels --band 2.4     # just 2.4 GHz (channels 1-14)
rfhound wifi channels --band 5       # just 5 GHz U-NII (36-165)
```

- **2.4 GHz** — channels 1-13 (5 MHz spacing from 2412 MHz) plus channel 14
  (2484 MHz, Japan/802.11b). Because each channel is ~20 MHz wide they overlap;
  1, 6 and 11 are the classic non-overlapping set.
- **5 GHz** — U-NII-1 (36-48), U-NII-2A (52-64, DFS), U-NII-2C (100-144, DFS)
  and U-NII-3 (149-165). DFS channels are shared with radar and carry transmit
  restrictions, so the survey prefers non-DFS channels when recommending one.

## Occupancy survey — `wifi survey`

Sweep a band, score each channel's occupancy (share of bins above the noise
floor) and peak SNR, and recommend the clearest channel to move to.

```bash
rfhound wifi survey                       # both bands (default)
rfhound wifi survey --band 2.4            # only 2.4 GHz
rfhound wifi survey --band 5 --snr 6      # 5 GHz, looser activity threshold
rfhound --simulate wifi survey            # demo it with no hardware
```

Example (simulated):

```
             Wi-Fi 2.4 GHz channel survey [SIMULATED]
 Ch    Center MHz  Occupancy        Peak dB  SNR dB  Status
 1 ★   2412        ············ 0%  -92      3       clear
 6 ★   2437        ············ 4%  -61      34      busy
 7     2442        ············ 4%  -61      34      busy
 11 ★  2462        ············ 0%  -92      3       clear
  noise floor ≈ -94.8 dB · 5/14 channels busy
✓ Suggested channel: 1 (2412 MHz) — clearest of the non-overlapping 1/6/11
  channels (0% occupancy)
```

**Reading it**

- **Occupancy** — percentage of the channel's frequency bins that sit above
  `floor + --snr` dB. High occupancy means the channel is broadly active, not
  just one narrow carrier.
- **Peak dB / SNR dB** — the strongest bin in the channel and how far it stands
  above the noise floor. A channel is marked **busy** when SNR ≥ 10 dB or
  occupancy ≥ 15%, **light** for a weaker signal, else **clear**.
- **Suggested channel** — the least-occupied channel. On 2.4 GHz the pick is
  restricted to 1/6/11; on 5 GHz it prefers non-DFS channels and only falls
  back to DFS if everything else is congested.

`--snr` (default 8 dB) sets how far above the noise floor a bin has to be to
count as occupied — lower it in quiet environments, raise it if a strong local
emitter is washing everything out.

## Interference & jamming on these bands

The survey shows *congestion*. If you suspect deliberate **interference or
jamming** rather than just a crowded band, use the detectors:

```bash
rfhound defense monitor 2400 2483.5     # detect a noise-floor rise / jamming (2.4 GHz)
rfhound sigint jamming 5150 5850        # classify the interference type (5 GHz)
rfhound defense respond jamming         # the counter-jamming response playbook
```

## Menu

The guided menu (`rfhound` with no arguments) has a **"Wi-Fi channel survey
(2.4/5 GHz)"** entry that runs the same survey interactively.
