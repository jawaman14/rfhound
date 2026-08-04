# Decoders

RFHound drives best-of-breed, **receive-only** decoders through a registry of
"recipes". Each recipe knows its external tool, a sensible default frequency, and
what it decodes. `rfhound decode list` shows the same list plus which tools are
installed on your machine right now.

To run one: `rfhound decode run <id> [--freq MHz] [--seconds N]`
(add `--dry-run` to just print the command).

## The list (19 recipes)

| ID | Name | Category | Default MHz | Tool | Decodes |
|----|------|----------|-------------|------|---------|
| `wspr` | WSPR weak-signal beacons | amateur | 14.096 | `wsprd` | WSPR propagation beacons (HF; needs upconversion on HackRF) |
| `aprs` | APRS packet radio | amateur | 144.390 | `multimon-ng` | AFSK1200 APRS position/telemetry |
| `aprs_ax25` | AX.25 / APRS packet | amateur | 144.390 | `direwolf` | AX.25/APRS via the direwolf soundmodem |
| `acars` | ACARS aircraft messaging | aviation | 131.550 | `acarsdec` | Aircraft/ground text messaging (~131 MHz) |
| `vdl2` | VDL Mode 2 | aviation | 136.975 | `dumpvdl2` | VHF Digital Link Mode 2 aircraft data |
| `radiosonde` | Weather-balloon radiosondes | aviation | 403.000 | `radiosonde_auto_rx` | Radiosonde telemetry (~400–406 MHz) |
| `uat978` | ADS-B UAT 978 | aviation | 978.000 | `dump978-fa` | US general-aviation ADS-B on 978 MHz |
| `adsb` | ADS-B 1090ES | aviation | 1090.000 | `dump1090` | Aircraft ICAO id, position, altitude, velocity |
| `hdradio` | HD Radio / NRSC-5 | broadcast | 98.100 | `nrsc5` | Digital HD Radio subchannels on FM |
| `rtl433` | ISM device decoder | ism | 433.920 | `rtl_433` | Hundreds of 300–928 MHz devices: TPMS, weather, sensors, remotes |
| `ert` | Smart utility meters (ERT) | ism | 912.600 | `rtlamr` | ERT/SCM electricity/gas/water meters |
| `ais` | AIS vessel tracking | maritime | 162.000 | `AIS-catcher` | Ship position/identity beacons (MMSI, position, course) |
| `pocsag` | POCSAG pagers | paging | 929.000 | `multimon-ng` | POCSAG pager messages (often unencrypted) |
| `flex` | FLEX pagers | paging | 929.000 | `multimon-ng` | FLEX pager messages (often unencrypted) |
| `satdump` | Satellites & imagery | satellite | 137.100 | `satdump` | Many weather/L-band satellites → imagery |
| `noaa_apt` | NOAA APT weather imagery | satellite | 137.500 | `noaa-apt` | NOAA APT images from a recorded WAV pass |
| `iridium` | Iridium bursts | satellite | 1621.250 | `iridium-extractor` | L-band bursts for iridium-toolkit |
| `tetra` | TETRA trunked radio | voice | 395.000 | `tetra-rx` | Unencrypted TETRA control/voice |
| `dsd` | Digital voice DMR/P25/NXDN | voice | 450.000 | `dsd` | Unencrypted DMR/P25/NXDN/D-STAR voice |

> Encrypted traffic (much DMR/P25/TETRA) is **not** decodable and must not be
> targeted. Pager/messaging content may be personal data — handle it per your
> rules of engagement (see [LEGAL.md](LEGAL.md)).

Some recipes (pagers, APRS, DSD) need an FM-demod front-end feeding stdin — see
[USAGE.md](USAGE.md) for the pipeline. Install any missing tool with the hint
from `rfhound doctor`.

## Auto-identify a signal

Not sure which decoder a mystery signal needs? RFHound can **guess the signal
type with a confidence score** from its frequency, bandwidth, and (optionally)
modulation:

```bash
rfhound classify 1090 --bw 1500          # → ADS-B 1090ES (high %), decoder: adsb
rfhound classify 433.92 --mod ook        # → ISM remote/sensor (OOK), decoder: rtl433
rfhound classify 162.0 --bw 25           # → AIS (marine), decoder: ais

rfhound sweep 430 440 --identify         # auto-identify every peak in a sweep
```

The web dashboard's peak table shows the same **Bandwidth · Likely signal ·
Decoder** columns automatically. See [HELP.md](HELP.md) for all options.
