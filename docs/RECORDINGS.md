# Recordings — captures that remember how to decode themselves

A capture is IQ + a SigMF sidecar. RFHound adds a management layer: it can run
the signal **classifier** over a capture and write the result back into the
sidecar — measured bandwidth, detected modulation, best-guess signal type, and
the **decode settings** (which decoder, at what frequency and sample rate). So a
recording carries everything needed to decode or replay it later.

Classification needs NumPy (`pip install rfhound[iq]`); everything else does not.

## Record

```bash
rfhound capture 433.92 10               # 10 s of IQ + SigMF metadata
rfhound capture 433.92 10 --classify    # ...and classify it into the metadata
```

## Catalog

```bash
rfhound recordings list                 # all captures + their classification
rfhound recordings classify fob_433     # (re)analyze one and store the result
rfhound recordings show fob_433         # full SigMF metadata
```

Example:

```
 Name      Freq MHz  Length  Likely signal                   Mod  Decoder
 fob_433   433.920   10.0s   ISM remote/sensor (OOK) (100%)  ook  rtl433
```

## What gets stored

The classifier writes these into the SigMF `global` block:

| Key | Meaning |
|-----|---------|
| `rfhound:bandwidth_khz` | measured occupied bandwidth |
| `rfhound:modulation` / `:mod_confidence` | detected modulation + confidence |
| `rfhound:guess` / `:guess_confidence` | best-guess signal type + confidence |
| `rfhound:suggested_decoder` | the decoder to try |
| `rfhound:decode_settings` | `{decoder, freq_mhz, sample_rate}` |

## Replay knows what it is

Because the decode settings live in the sidecar, replay tells you what you're
about to transmit (and it stays gated — see [LEGAL.md](LEGAL.md)):

```bash
rfhound replay captures/fob_433.sigmf-data --authorized --dry-run
# › This recording looks like: ISM remote/sensor (OOK) (100%) · ook · decoder rtl433
```

Captures are SigMF, so they also open directly in **URH**, **inspectrum**, and
**GNU Radio** for deeper protocol work.
