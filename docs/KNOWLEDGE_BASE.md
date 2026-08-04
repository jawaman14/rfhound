# RFHound knowledge base

A working reference for identifying and understanding signals — the background
RFHound's classifiers and band plan are built on. It's meant to grow: add rows as
you learn a new signal.

## 1. ITU frequency-band designations ("what range am I in?")

| Abbr | Name | Range | Character (for a HackRF) |
|------|------|-------|--------------------------|
| MF | Medium Frequency | 300 kHz–3 MHz | AM broadcast; needs an upconverter |
| HF | High Frequency | 3–30 MHz | Shortwave, ham, WSPR; upconverter |
| VHF | Very High Frequency | 30–300 MHz | FM bcast, air/marine, AIS, pagers, sats |
| UHF | Ultra High Frequency | 300 MHz–3 GHz | ISM 433/868/915, LMR, GSM, ADS-B, GPS |
| SHF | Super High Frequency | 3–30 GHz | Wi-Fi 5 GHz, FPV 5.8 (HackRF tops at 6) |

`rfhound at <MHz>` and the dashboard footer show the ITU band you're in.

## 1b. HackRF One hardware capabilities

What the radio can do, and how RFHound uses it:

| Capability | Spec | In RFHound |
|------------|------|------------|
| Frequency range | 1 MHz – 6 GHz, half-duplex | all tuning |
| Sample rate | 2–20 Msps (20 MHz bandwidth) | `sample_rate` in config (default 8) |
| RX/TX gains | LNA (IF), VGA (BB), +14 dB amp | `lna_gain`/`vga_gain`/`amp_enable` |
| Bias-tee | 3.3 V / 50 mA on the antenna port | `antenna_power` (for active antennas/LNAs) |
| Baseband filter | selectable | `baseband_filter_hz` |
| Clock | onboard 25 MHz **or** external 10 MHz ref (SMA in/out) | `rfhound device clock` |
| Opera Cake | 8-port antenna switch add-on (1×8 or dual 1×4), by freq/time | `rfhound device operacake` |
| Max TX power | ~15 dBm (band-dependent) | replay only, gated |

Tools RFHound drives: `hackrf_info`, `hackrf_sweep`, `hackrf_transfer`,
`hackrf_operacake`, `hackrf_clock` (see `rfhound doctor`).

## 2. Modulation cheat-sheet (how to tell them apart)

| Modulation | Amplitude | Frequency/Phase | Tell-tale in IQ | Common users |
|------------|-----------|-----------------|-----------------|--------------|
| OOK/ASK | on/off, bursty | — | high amplitude variance, low duty | ISM remotes, fobs, doorbells |
| FSK/GFSK | constant | 2+ discrete tones | bimodal instantaneous freq | sensors, pagers, BLE |
| (W/N)FM | constant | continuous freq swing | wide inst-freq spread | broadcast, voice, NOAA APT |
| PSK/QAM | constant | phase clusters | tight amplitude, phase states | satellites, digital links |
| Chirp (CSS) | constant | linear freq sweep | ramping inst-freq | LoRa |
| Pulse (PPM) | pulsed | — | short high-power bursts | ADS-B (1090) |
| OFDM | noise-like | many carriers | high PAPR, flat wide band | Wi-Fi, DAB, LTE |

`rfhound classify --file capture.sigmf-data` measures these from a recording.

## 3. Signal-identification workflow

1. **Where?** `rfhound at <freq>` → band + ITU + which tools apply.
2. **What?** `rfhound sweep <a> <b> --identify` (or `classify`) → bandwidth +
   likely type + confidence.
3. **Capture** a clean example: `rfhound capture <freq> <sec>`.
4. **Measure** it: `rfhound classify --file <capture>` → real bandwidth + modulation.
5. **Decode**: `rfhound decode run <id>`; for anything custom, generate a GNU
   Radio flowgraph (`rfhound gnuradio gen …`) or open the capture in **URH**.
6. **Reverse** unknown protocols in URH; note findings back here.

## 4. Quick "what's likely here?" table

| Frequency | Very likely | Try |
|-----------|-------------|-----|
| 88–108 MHz | FM broadcast | `gnuradio gen wbfm` |
| 118–137 MHz | Air-band AM / ACARS | `decode run acars` |
| 137–138 MHz | NOAA/Meteor weather sats | `decode run noaa_apt` |
| 144.39 / 144.80 | APRS | `decode run aprs` |
| 161.975 / 162.025 | AIS (ships) | `decode run ais` |
| 315 / 433.92 / 868 / 915 | ISM devices (fobs, TPMS, sensors) | `decode run rtl433` |
| 929–932 MHz | POCSAG/FLEX pagers | `decode run pocsag` |
| 978 / 1090 MHz | ADS-B (aircraft) | `decode run adsb` |
| 1575.42 MHz | GPS L1 (RX only) | — |
| 2.4 / 5.8 GHz | Wi-Fi/BLE / FPV drones | `defense drone-scan` |

## 5. Glossary

- **IQ**: complex baseband samples (in-phase + quadrature). HackRF outputs 8-bit
  interleaved IQ (SigMF `ci8`).
- **Occupied bandwidth**: the frequency span holding ~99% of a signal's power.
- **Noise floor**: the background power level; signals are found above it.
- **SNR**: signal-to-noise ratio; here also estimated as spectral peak-to-median.
- **SigMF**: an open metadata format for recorded IQ (`.sigmf-data` + `.sigmf-meta`).
- **ARFCN / EARFCN**: channel numbers for GSM / LTE.
- **RollJam**: an attack that jams + captures a rolling code; RFHound *detects*
  the pattern, it does not perform it.

See [REFERENCES.md](REFERENCES.md) for external handbooks, the Signal
Identification Guide, and tool repositories.
