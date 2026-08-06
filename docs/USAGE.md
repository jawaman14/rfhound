# Usage guide

## Install RFHound

```bash
cd rfhound
pip install -e .           # gives you the `rfhound` command + rich
```

RFHound itself only needs Python 3.9+ and (optionally) `rich`. Everything else is
an **external SDR tool** it drives on demand — install only what you need.

## Install the SDR tools RFHound can drive

Run `rfhound doctor` at any time to see what's present and get install hints.

```bash
# HackRF host tools (hackrf_info, hackrf_sweep, hackrf_transfer)
sudo apt install hackrf            # Debian/Ubuntu
brew install hackrf                # macOS

# ISM decoder (build with SoapySDR for HackRF input)
sudo apt install rtl-433

# Pager / APRS decoder
sudo apt install multimon-ng

# ADS-B (dump1090-fa), AIS-catcher, acarsdec, dumpvdl2 — build from source:
#   https://github.com/flightaware/dump1090
#   https://github.com/jvde-github/AIS-catcher
#   https://github.com/TLeconte/acarsdec
#   https://github.com/szpajder/dumpvdl2

# SoapySDR HackRF driver (needed by rtl_433 -d driver=hackrf, AIS-catcher, etc.)
sudo apt install soapysdr-module-hackrf
```

### HackRF permissions on Linux

If `hackrf_info` says the device is busy or permission-denied, install udev rules
and add yourself to `plugdev`:

```bash
sudo usermod -aG plugdev "$USER"    # then log out/in
# The hackrf package usually installs /etc/udev/rules.d rules automatically.
```

## Core workflows

### 1. What's around me? (recon)

```bash
rfhound recon                        # survey high-value bands
rfhound recon --category ism         # just the ISM bands
rfhound recon --report site.html     # write an HTML report
rfhound recon --simulate             # no hardware needed
```

### 2. Look at a slice of spectrum (sweep)

```bash
rfhound sweep 433 435                # spectrogram + peak table
rfhound sweep 100 1000 --bin 250     # wide sweep, coarser bins
rfhound sweep 862 928 --snr 8        # lower threshold = more sensitive
```

### 3. Browse the knowledge base (bands)

```bash
rfhound bands                        # everything
rfhound bands --category aviation
rfhound bands --tag tpms -v          # with descriptions
rfhound bands --search pager
```

### 4. Decode a protocol (decode)

```bash
rfhound decode list                  # recipes + which tools are ready
rfhound decode run rtl433            # 433 MHz ISM devices
rfhound decode run adsb              # aircraft at 1090 MHz
rfhound decode run rtl433 --freq 868.3 --seconds 60
rfhound decode run adsb --dry-run    # print the command, run nothing
```

#### Pagers / APRS need an FM front-end

`multimon-ng` consumes demodulated audio on stdin. With a HackRF the canonical
pipeline is (RFHound prints the `multimon-ng` half; wire up the front-end
yourself so the choice is deliberate):

```bash
# Example using rtl_fm-style demod via SoapySDR + sox, piped into multimon-ng:
hackrf_transfer -r - -f 929000000 -s 2000000 \
  | csdr convert_u8_f | csdr fmdemod_quadri_cf | csdr fractional_decimator_ff ... \
  | multimon-ng -a POCSAG1200 -f alpha -
```

### 5. Capture IQ for deep analysis (capture)

```bash
rfhound capture 433.92 10            # 10 s at 433.92 MHz
rfhound capture 1090 5 --rate 4000000 --note "ADS-B sample"
```

This writes a `.sigmf-data` file plus a `.sigmf-meta` sidecar. Open it in
**Universal Radio Hacker**, **inspectrum**, or **GNU Radio** to reverse the
protocol, then hand results back to RFHound recipes.

### 6. Authorized replay (transmit — gated)

**Read [`LEGAL.md`](LEGAL.md) first.** Transmit is off by default.

```bash
# One-time: declare the ranges you are authorized to transmit in.
rfhound tx enable --allow 433.0-434.8 --jurisdiction "EU"

# Replay a signal YOU captured, for authorized testing of YOUR device:
rfhound replay capture_433MHz.sigmf-data --authorized --dry-run   # preview
rfhound replay capture_433MHz.sigmf-data --authorized             # transmit

rfhound tx status         # review settings + policy + recent audit
rfhound tx audit          # the append-only transmit audit log (--json, --clear)
rfhound tx disable        # turn transmit back off
```

RFHound refuses to transmit outside your declared allow-list, outside the HackRF
hardware range, or without the per-command `--authorized` flag. On top of that:

- **Safety-of-life bands are always refused** — GNSS, aviation VHF (incl. the
  121.5 MHz emergency channel), ADS-B/UAT, marine distress, and COSPAS-SARSAT
  beacon frequencies are blocked *even if* you allow-listed a range covering
  them. Transmitting there endangers navigation and distress systems.
- **A duration cap** (`tx_max_seconds`, default 30 s) refuses an over-long or
  looping replay.
- **Every attempt is audited** — transmitted, blocked, and dry-run events are
  appended to `~/.config/rfhound/tx_audit.log` with timestamp, frequency,
  duration, and outcome, so any use of the radio is accountable.
- **`--dry-run` prints a full preflight** (frequency + ITU band, duration vs.
  cap, allow-list status, protected-band check) without keying the transmitter.

RFHound still provides **no** signal generation, jamming, spoofing, or
brute-force transmit — the only transmit path is replaying an IQ file you
captured yourself, for authorized testing of your own equipment.

## The web dashboard & REST API

```bash
rfhound web                       # http://127.0.0.1:8000
rfhound web --host 0.0.0.0 --port 9000 --token   # require a generated token
rfhound web --token s3cr3t                        # require a specific token
rfhound web --simulate            # demo with no hardware
```

The dashboard is served from Python's standard library (no extra dependencies)
and is **receive-and-analyse only** — there is deliberately no transmit endpoint.
Every panel is backed by a JSON endpoint you can consume directly:

| Endpoint | Returns |
|---|---|
| `GET /api/status` | device, tools, hardware settings, version |
| `GET /api/sweep?start=&stop=&simulate=` | spectrum array + detected peaks |
| `GET /api/recon?simulate=` | band survey findings |
| `GET /api/defense/drone?simulate=` | counter-UAS detections |
| `GET /api/defense/spoof/adsb` · `/ais` | spoof-detection findings |
| `GET /api/bands` · `/api/decoders` | knowledge base & decoder recipes |
| `GET /api/bookmarks` | saved frequency bookmarks |
| `POST /api/bookmarks/add` · `/delete` | add/remove a bookmark (`{name, freq_mhz, note}`) — token-gated when a token is set |

The dashboard has a **theme toggle** (auto / dark / light, persisted per browser),
an **S-meter** with an S-unit scale + peak-hold, and inline **bookmark editing**
(add/delete, or ★ the current sweep centre). The spectrum/waterfall canvases stay
dark in both themes. A **Live** toggle auto-refreshes the threat KPIs; the
**waterfall** has selectable colormaps (Aqua/Turbo/Viridis/Inferno/Grayscale) and
an intensity slider; and the peaks, recon, and knowledge-base tables each
**export to CSV or JSON**.

**Authentication.** By default the dashboard binds to `127.0.0.1` with no token
(fine for a local session). To expose it on a network, gate the API with a token:

```bash
rfhound web --host 0.0.0.0 --token           # generates & prints a token
rfhound web --host 0.0.0.0 --token s3cr3t     # use your own
```

When `--host` is not localhost a token is generated automatically if you don't
pass one. With a token set, every `/api/…` request must present it — as a
`Authorization: Bearer <token>` header, an `X-RFHound-Token` header, a `?token=`
query param, or the `rfh_token` cookie. Open the printed
`http://…/?token=<token>` link and the dashboard captures the token into
`sessionStorage` and sends it as a bearer header on every call (stripping it from
the URL). The HTML shell carries no data and is always served; only the data API
is gated. For production, still prefer a reverse proxy (TLS + your own SSO) in
front of the token. Responses set `X-Content-Type-Options`, `X-Frame-Options`,
and `Referrer-Policy`. The server is receive-only — no token, cookie, or proxy
ever unlocks a transmit path, because there isn't one.

## HackRF hardware options

RFHound exposes the HackRF's hardware controls via config (used by sweep and
capture):

| Setting | Flag | Meaning |
|---|---|---|
| `amp_enable` | `-a` | Front-end RF amplifier (+~14 dB) |
| `antenna_power` | `-p` | **Bias-tee**: 3.3 V / 50 mA on the antenna port for powered antennas/LNAs |
| `lna_gain` / `vga_gain` | `-l` / `-g` | RX IF and baseband gain |
| `baseband_filter_hz` | `-b` | Baseband filter bandwidth (capture only; 0 = auto) |
| `freq_correction_ppm` | `-C` | Crystal clock error correction (capture only) |
| `device_serial` | `-d` | Select a specific HackRF by serial (multi-unit setups) |

```bash
rfhound config show
# edit ~/.config/rfhound/config.json, e.g. set "antenna_power": true to power an
# active antenna, or "device_serial" to pick one of several HackRFs.
```

## The guided menu

Prefer clicking to typing? Just run:

```bash
rfhound
```

…for an interactive menu covering recon, sweep, the knowledge base, and decoders.
It auto-detects whether a HackRF is attached and drops into `--simulate` if not.

## Global simulate & dev mode

Two global flags sit before any subcommand:

```bash
rfhound --simulate recon           # force synthetic data for ANY command
rfhound --dev sweep 433 435        # verbose debug + full tracebacks
rfhound --dev --simulate web       # a fully offline dev/demo dashboard
```

`--simulate` can also be made permanent via `"simulate_mode": true` in the
config, so a dev/demo box always runs against synthetic data with no hardware.

## Nicer terminal (powered by `rich`)

RFHound leans on the `rich` library it already depends on:

```bash
rfhound sweep 433 435 --watch --interval 1   # live, continuously-updating spectrum
rfhound recon                                # animated spinner while surveying
rfhound gnuradio gen wbfm --freq 100.3       # generated code shown with syntax highlighting
```

All of these degrade gracefully to plain text when `rich` isn't installed.

## Configuration

```bash
rfhound config show        # current settings
rfhound config init        # write ~/.config/rfhound/config.json
rfhound config path        # where the config lives
```

Editable settings include RX gains (`lna_gain`, `vga_gain`, `amp_enable`),
`sample_rate`, `output_dir`, and the transmit safety block.
