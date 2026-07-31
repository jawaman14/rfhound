# GNU Radio integration

**Is it worth adding GNU Radio?** Yes — but for one specific job. The fixed CLI
decoders (`rtl_433`, `dump1090`, …) cover known protocols. GNU Radio is the right
tool when you need **custom DSP**: an unusual modulation, a tailored filter
chain, an energy detector, or raw demodulation you'll post-process yourself.

Hand-building flowgraphs is exactly the friction RFHound removes, so RFHound
ships **prebuilt, parameterised presets** that generate a runnable GNU Radio
Python flowgraph for you.

> Every preset is **receive / analysis only** — an Osmocom HackRF *source* into a
> file/WAV/probe sink. There are deliberately **no transmit (Osmocom sink)
> presets**, consistent with the rest of RFHound.

## Check your environment

```bash
rfhound gnuradio status      # is GNU Radio + gr-osmosdr installed?
```

Generated flowgraphs need `gnuradio` and `gr-osmosdr` to *run* (you can generate
them anywhere): `sudo apt install gnuradio gr-osmosdr`.

## Presets

| Preset | Purpose |
|---|---|
| `iq_record` | Record raw complex IQ to a file |
| `wbfm` | Wideband FM → WAV |
| `nbfm` | Narrowband FM voice → WAV |
| `am` | AM envelope → WAV |
| `energy_detector` | Log power (dB) vs time — presence detection |
| `ook_envelope` | Magnitude envelope for OOK/ASK analysis |
| `fsk_quad` | Quadrature-demod FSK → float stream |

## Generate and run

```bash
rfhound gnuradio list
rfhound gnuradio gen wbfm --freq 100.3 --out fm.py
rfhound gnuradio gen energy_detector --freq 433.92 --data-out energy.f32
python3 fm.py         # requires gnuradio + gr-osmosdr on this machine
```

The generated script reads its RF/IF/BB gains from your RFHound config, uses the
HackRF via `osmosdr.source`, and writes to the output you chose. Edit the file
freely — it's plain GNU Radio Python you can extend into any custom RX pipeline.
