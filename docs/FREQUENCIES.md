# The frequency knowledge base — what lives across 1 MHz – 6 GHz

This is the "search all the pentesting things you can do within those
frequencies" reference. Frequencies are **regional** — the ITU splits the world
into three regions and allocations differ (notably US vs EU). Always confirm your
local band plan. RFHound's live copy of this table is in
[`rfhound/bandplan.py`](../rfhound/bandplan.py); browse it with `rfhound bands`.

Legend: **RX** = receive/analyse (commonly permitted) · **TX** = transmitting is
restricted/illegal without a licence.

## Sub-GHz — the richest hunting ground

| Band | Freq | What's there | Security relevance | Decoder |
|---|---|---|---|---|
| ISM 315 MHz | 314.9–315.1 | US key fobs, TPMS, garage/gate remotes | Weak/static-code remotes, sensor spoofing research | `rtl433` |
| ISM 433 MHz | 433.05–434.79 | Remotes, weather stations, doorbells, alarms, TPMS, LoRa | **Start here.** Huge attack surface of cheap OOK/FSK devices | `rtl433` |
| ISM 868 MHz | 863–870 (EU) | Smart meters, LoRaWAN, home automation, alarms | IoT/utility recon, LoRaWAN join analysis | `rtl433` |
| ISM 915 MHz | 902–928 (US) | Smart meters (rtlamr), Z-Wave (908.4), LoRa, telemetry | Utility metering, home-automation recon | `rtl433` |
| POCSAG/FLEX pagers | 138–160, 929–932 | Pager networks | **Frequently unencrypted** — demonstrates cleartext-messaging risk | `pocsag` |

**Typical findings & why they matter**
- **TPMS** leaks per-vehicle sensor IDs → passive vehicle tracking / presence.
- **Fixed-code remotes** (old garage/gate) → replayable; motivates upgrading to
  rolling-code. (RFHound helps you *identify* these; it does not ship a grabber.)
- **Weather/temperature/PIR sensors** → facility occupancy & asset inventory.
- **Smart meters** → consumption profiling; sometimes unauthenticated.

## VHF / aviation / maritime

| Band | Freq | What's there | Relevance | Decoder |
|---|---|---|---|---|
| FM broadcast (+RDS) | 87.5–108 | Radio + RDS data | Best first demod / calibration reference | — |
| NOAA/Meteor weather sats | 137–138 | Satellite image downlinks | APT/LRPT imagery capture | — |
| Aircraft VHF (AM) | 108–137 | Nav aids + voice | Situational awareness (RX only) | — |
| ACARS | ~131 | Aircraft text messaging | Ops/telemetry intel (RX only) | `acars` |
| APRS | 144.39/144.80 | Ham position/telemetry | Tracking demos | `aprs` |
| AIS | 161.975/162.025 | Ship positions (MMSI) | Maritime tracking/OSINT | `ais` |

## UHF services

| Band | Freq | What's there | Relevance |
|---|---|---|---|
| UHF LMR | 380–470 | Land-mobile, TETRA (EU), P25 (US) | Voice-system recon (RX). Many encrypted. |
| PMR446 / FRS/GMRS | 446 / 462–467 | Licence-free handhelds | Cleartext voice discovery |
| 70cm ham | 430–440 | Amateur | Overlaps ISM 433 |

## L-band & above

| Band | Freq | What's there | Relevance | Decoder |
|---|---|---|---|---|
| ADS-B UAT | 978 (US) | GA aircraft telemetry | Aircraft tracking | — |
| GSM-900 downlink | 925–960 | Legacy 2G | Cell recon/analysis (RX, sensitive) | — |
| **ADS-B 1090ES** | 1090 | Aircraft position/ID | Rich, passive, legal to receive | `adsb` |
| GPS L1 | 1575.42 | GNSS | **RX only — never TX** | — |
| Iridium / Inmarsat | 1616–1626 | Satphone/L-band | SATCOM research | — |
| DECT | 1880–1900 (EU) | Cordless phones | Cordless-phone recon | — |
| 2.4 GHz ISM | 2400–2483.5 | Wi-Fi, BLE, ZigBee, RC | PHY-level view; non-standard emitters | — |
| 5 GHz U-NII | 5150–5850 | Wi-Fi | Near HackRF's 6 GHz upper edge | — |

> For Wi-Fi/BLE/ZigBee *protocol* attacks, dedicated NICs (Wi-Fi adapters,
> Ubertooth, an nRF/CC2531 sniffer) are far more effective than an SDR. Use the
> HackRF for the spectrum/PHY view and for spotting non-standard emitters.

## A sensible learning path

1. `rfhound recon --simulate` — see the whole workflow with no hardware.
2. Demodulate **FM broadcast** — an easy, strong, known signal.
3. Sweep **433 MHz** and run `rtl433` — you'll almost certainly see real devices.
4. Receive **ADS-B at 1090 MHz** — instant, satisfying, legal.
5. Capture an interesting signal → open it in **URH** to reverse the protocol.
