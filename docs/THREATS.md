# RF threat model & attack surface

A defensive reference: for each **attack class**, each **frequency band**, and
each **encoding/modulation**, what attacks are possible, how you *detect* them,
how you *defend*, and where **RFHound** fits (today and on the roadmap).

> **Framing — read this.** This is threat-modelling for defenders, at the
> conceptual level you'd find in an RF-security course or a NIST/ENISA guide. It
> describes *what attacks exist and why*, and — the point of the document — how
> to **detect and mitigate** them. It is **not** an attack how-to: no parameters,
> payloads, or step-by-step procedures. Consistent with the whole project,
> RFHound performs **Electronic Support and Protection** (detect / measure /
> identify / locate / harden) and never **Electronic Attack** (jamming, spoofing,
> deception). See [LEGAL.md](LEGAL.md).

---

## Part 1 — Attack-class taxonomy

The recurring ways RF systems are attacked, independent of band. Each row lists
the mechanism, the detectable signature, and RFHound's coverage.

| Attack class | Mechanism (conceptual) | Detectable signature | RFHound |
|---|---|---|---|
| **Jamming / DoS** | Radiate energy to deny a channel: *barrage* (broadband noise), *spot* (one carrier), *swept/chirp*, *pulsed*, or *reactive/selective* (jam only certain frames) | Noise-floor rise across a band; expected signals vanish; a moving or pulsed strong carrier | `defense monitor` (detect) + `sigint jamming` (classify type) |
| **Replay** | Capture a valid transmission and re-send it later | The *identical* payload seen again; implausibly fast repeats | `defense replay-check` |
| **Rolling-code defeat** | Against hopping/counter codes: *RollJam* (jam+capture an unused code, replay it), *RollBack* (replay a sequence to roll the counter back), or crypto weaknesses (e.g. classic KeeLoq key recovery) | Jamming coincident with a fob press; out-of-order counters; duplicate rolling codes | `defense rolling-assess` (posture) + `defense monitor` (the jam half) |
| **Relay / amplification** | Extend a short-range challenge-response (e.g. PKE) by relaying the RF between two points | Valid exchange with impossible round-trip timing / geometry | Roadmap (timing/geometry checks; distance-bounding is a device-side fix) |
| **Spoofing / injection** | Transmit forged messages a receiver trusts (ghost aircraft, fake vessels, false sensors) | Impossible kinematics; duplicate identities; values inconsistent with physics or other sensors | `defense spoof-check adsb\|ais`; `intel` plausibility checks |
| **Meaconing** | Record authentic signals and rebroadcast (delayed) to induce false position/time (esp. GNSS) | Sudden position/time jump; power step; loss-then-return | Roadmap (GNSS interference monitor) |
| **Bit-flipping / integrity** | Alter ciphertext to change decrypted meaning without the key (weak/absent MIC) | Protocol-anomaly at the app layer (needs decode) | Roadmap (decoder → anomaly wiring) |
| **Downgrade** | Force a device onto a weaker legacy protocol (e.g. 5G/4G → 2G) to strip protections | A cell advertising legacy tech / forcing re-selection; encryption dropped | `defense imsi-catcher` (rogue-BTS indicators) |
| **Rogue infrastructure** | Impersonate trusted infrastructure (IMSI catcher / cell-site simulator, rogue AP) | New strong cell, unknown LAC/TAC, A5/0, empty neighbour list, ID reuse | `defense imsi-catcher` |
| **Brute-force / weak-crypto** | Exhaust a small keyspace or exploit a broken cipher | Rapid repeated attempts at one target | Detection only (rate/anomaly); RFHound ships **no** brute-forcer |
| **Traffic analysis** | Infer activity from metadata even when payloads are encrypted (timing, volume, emitter presence) | Emitter on/off patterns, duty cycles | `sigint emitters` (EOB), `track`, hop-detect |

Definitions: [SIGINT/EW disciplines](https://www.trentonsystems.com/en-us/resource-hub/blog/sigint-vs-comint-vs-elint);
RollJam/RollBack ([paper](https://arxiv.org/pdf/2210.11923)); LoRaWAN classes ([Trend Micro](https://www.trendmicro.com/en_us/research/21/a/Low-Powered-but-High-Risk-Evaluating-Possible-Attacks-on-LoRaWAN-Devices.html)).

---

## Part 2 — Attack surface by frequency band

For each band: what lives there, the typical encoding, the applicable attack
classes, real-world prevalence, detection indicators, and RFHound coverage.

### Sub-GHz ISM — 315 / 433.92 / 868 / 915 MHz
- **Devices:** car key fobs (RKE), TPMS, garage/gate remotes, alarms, doorbells,
  weather/PIR sensors, smart meters (ERT), sub-GHz IoT.
- **Encoding:** mostly OOK/ASK or (G)FSK; *fixed* codes on cheap devices, *rolling*
  codes (KeeLoq-class and better) on modern RKE.
- **Attacks:** **replay** (trivial on fixed codes); **RollJam / RollBack** and
  crypto attacks on rolling codes; **jamming** the lock command; **TPMS spoofing**
  (forge sensor IDs/pressures) and **TPMS tracking** (IDs are static → presence);
  **sensor spoofing** (false alarm/weather data).
- **Prevalence:** very high — the richest, cheapest attack surface.
- **Detect:** duplicate payloads (replay); jam-then-press pattern (RollJam);
  static IDs recurring (TPMS tracking); a strong new emitter over the band.
- **RFHound:** `defense replay-check`, `rolling-assess`, `monitor`; `decode run
  rtl433 --track` logs recurring sensor/TPMS IDs; `sigint jamming`.

### LoRa / LoRaWAN — 433 / 868 / 915 MHz
- **Encoding:** CSS (chirp) PHY; LoRaWAN adds AES-128 (MIC + payload) — but
  security hinges on key management.
- **Attacks:** **selective jamming** (classify a frame on-air, jam only it);
  **replay** of join/uplink frames (esp. LoRaWAN 1.0.x with weak nonce handling);
  **bit-flipping** between network-layer decrypt and app-layer re-encrypt (1.0.x);
  **key compromise** (hardcoded/reused/derivable keys → decrypt & impersonate).
- **Detect:** repeated join requests; DevAddr/counter anomalies; targeted jamming
  synced to frames; sudden gateway-visible duplicates.
- **RFHound:** `monitor` + `sigint jamming` for the jamming/selective-jamming half;
  roadmap: LoRaWAN join-replay + counter-anomaly detection via decoder wiring.

### VHF services — ACARS (~131), APRS (144.39/144.80), marine voice, POCSAG/FLEX pagers (138–160 / 929–932)
- **Encoding:** AM/MSK (ACARS), AFSK (APRS), FSK (POCSAG/FLEX) — **unauthenticated,
  usually unencrypted**.
- **Attacks:** **interception** (pagers/ACARS often carry sensitive cleartext);
  **injection/spoofing** (forge ACARS/APRS/pager messages); **jamming**.
- **Detect:** implausible/forged message content; cleartext exposure; interference.
- **RFHound:** `decode run pocsag|flex|acars|aprs` (receive/observe), `monitor`.
  Handle pager/ACARS content per your rules of engagement — it may be personal data.

### AIS (maritime) — 161.975 / 162.025 MHz
- **Encoding:** GMSK, **unauthenticated broadcast**.
- **Attacks:** **vessel spoofing** (ghost ships, false position/identity), **AIS
  "sinking"/relocation**, **jamming**; frequently a *symptom* of GNSS spoofing
  upstream (a spoofed ship reports a spoofed position).
- **Detect:** impossible speed/teleport, invalid MMSI, duplicate identity,
  disagreement with radar/EO.
- **RFHound:** `defense spoof-check ais`; correlate across `hub` nodes.

### Aviation surveillance — ADS-B 1090ES, UAT 978 MHz
- **Encoding:** PPM/pulse (1090), **unauthenticated broadcast**.
- **Attacks:** **ghost-aircraft injection**, **replay**, **flooding/DoS**, **target
  deletion** (jam a real aircraft's slot); like AIS, often downstream of **GNSS
  spoofing** (the aircraft honestly reports a spoofed position).
- **Detect:** impossible kinematics/altitude, duplicate ICAO, tracks that fail
  cross-checks against radar/MLAT/independent feeds; power/DOA anomalies.
- **RFHound:** `defense spoof-check adsb`; roadmap: multi-node MLAT-style
  cross-check and DOA via the hub.

### GNSS — GPS L1 1575.42 (and L2/L5, GLONASS/Galileo/BeiDou)
- **Encoding:** BPSK spread-spectrum; **civil signals are unauthenticated** (Galileo
  OSNMA is the emerging exception).
- **Attacks:** **jamming** (deny), **spoofing** (false position/time), **meaconing**
  (rebroadcast). This is now a daily operational reality for aviation & maritime.
- **Detect:** C/N0 anomalies, AGC changes, position/time jumps, disagreement with
  INS/known-location/network time, high-antenna-motion & DOA checks, cross-check
  with ADS-B/AIS at scale.
- **RFHound:** roadmap — passive **GNSS interference monitor** (jamming/spoofing
  indicators; detection only, never TX). Today: `defense respond gps_spoof`
  playbook. Never transmit near GNSS.

### Cellular — GSM/2G (925–960, 1805–1880), 3G/4G/5G
- **Encoding:** GMSK (2G), W-CDMA/OFDMA (3G/4G/5G).
- **Attacks:** **IMSI catcher / cell-site simulator** (rogue base station harvests
  identifiers, can MITM on 2G), **2G downgrade** (force legacy to strip protection —
  still viable via backward compatibility even on 5G phones), **SS7/Diameter**
  signalling abuse (network-side location/intercept — *not* an RF/HackRF attack),
  **jamming**. 5G's SUPI concealment defeats the classic catcher but downgrade
  keeps it alive.
- **Detect (RF side):** A5/0 or downgraded ciphering, unknown/changing LAC-TAC,
  an implausibly strong new cell, unexpected MCC/MNC, Cell-ID reused across ARFCNs,
  missing neighbour list.
- **RFHound:** `defense imsi-catcher` (ingest observed cell parameters, score
  rogue-BTS likelihood). RFHound performs **no** cellular transmission and no SS7
  tooling — detection only.

### 2.4 / 5 GHz ISM — Wi-Fi, BLE, Zigbee/Z-Wave, drones
- **Encoding:** OFDM (Wi-Fi), GFSK (BLE/Zigbee), etc.
- **Attacks:** **jamming/DoS**, **deauth/disassoc floods** (Wi-Fi — link-layer),
  **BLE spoofing/MITM**, **Zigbee/Z-Wave replay/spoofing/MITM/sinkhole**, **drone
  C2/video interception & jamming**. Note: link-layer Wi-Fi/BLE/Zigbee attacks are
  better done with dedicated NICs (Ubertooth, nRF, Wi-Fi cards) than an SDR; the
  SDR's value here is the **PHY/spectrum view** and spotting non-standard emitters.
- **Detect:** broadband occupancy/jamming; drone control/video RF signatures;
  anomalous emitters.
- **RFHound:** `defense drone-scan` (counter-UAS detection), `sweep`, `monitor`.

### Satellite & weather — NOAA APT 137, Meteor, Inmarsat/Iridium L-band
- **Encoding:** FM (APT), QPSK bursts (Iridium), etc.; downlinks largely
  unauthenticated to the receiver.
- **Attacks:** mostly **interception** (legal sensitivity varies) and **jamming**;
  uplink spoofing is a high-barrier, high-consequence act.
- **RFHound:** `decode run noaa_apt|satdump|iridium` (receive), `monitor`.

---

## Part 3 — Attack surface by encoding / modulation

The *encoding* often decides the attack more than the frequency does.

| Encoding scheme | Security property | Primary attack(s) | Why it works / fails | Defense |
|---|---|---|---|---|
| **OOK/ASK fixed code** | none (static secret in the clear) | **replay** | one capture reopens it forever | move to rolling/challenge-response |
| **Rolling code (counter + cipher)** | freshness via counter | **RollJam**, **RollBack**, crypto attacks (weak KeeLoq) | jam-and-hold defeats "use once"; replaying a window can roll the counter; weak ciphers leak keys | enforce forward-only window, reject reuse; strong cipher; detect jam-then-press |
| **Unauthenticated broadcast** (ADS-B, AIS, APRS) | integrity: none | **injection / spoofing**, **replay**, **flooding** | anyone can craft valid frames | multi-sensor cross-check (radar/MLAT/EO); plausibility checks |
| **Unencrypted digital** (POCSAG/FLEX, some ACARS) | confidentiality: none | **interception** | payload is cleartext | don't send secrets in the clear; encrypt |
| **Unauthenticated spread-spectrum** (civil GNSS) | integrity: none (civil) | **spoofing**, **meaconing**, **jamming** | signal structure is public, power is tiny | authenticated GNSS (OSNMA), INS/holdover, DOA/power monitoring |
| **GMSK w/o mutual auth** (GSM/2G) | one-way auth | **IMSI catcher**, **downgrade**, **MITM (2G)** | network isn't authenticated to the phone; legacy fallback | 5G SUPI concealment; disable 2G; rogue-BTS detection |
| **AES w/ weak key mgmt** (LoRaWAN 1.0.x, some Zigbee) | good cipher, fragile keys/MIC | **bit-flip**, **replay**, **key compromise** | reused/hardcoded keys; MIC gaps between layers | LoRaWAN 1.1; per-device keys; rotate; nonce hygiene |
| **Encrypted digital voice/data** (DMR/P25/TETRA *with* encryption) | confidentiality + integrity | **traffic analysis**, **jamming** only | payload not decodable | resilient/diverse comms; jamming detection |

---

## Part 4 — RFHound coverage matrix (and gaps)

| Threat | Detect today | Command | Roadmap gap |
|---|---|---|---|
| Jamming (any type) | ✅ + type classification | `defense monitor`, `sigint jamming` | jamming-from-IQ (swept/pulsed) |
| Replay | ✅ | `defense replay-check` | live decoder wiring |
| Rolling-code posture / RollJam | ✅ posture + jam-half | `defense rolling-assess`, `monitor` | correlated jam-then-press detector |
| ADS-B / AIS spoofing | ✅ | `defense spoof-check` | multi-node MLAT/DOA cross-check |
| GNSS jamming/spoofing | ⚠️ playbook only | `defense respond gps_spoof` | passive GNSS interference monitor |
| Rogue base station / downgrade | ✅ (RF indicators) | `defense imsi-catcher` | live gr-gsm ingest |
| Counter-UAS | ✅ | `defense drone-scan` | RF-fingerprint drone models |
| Emitter presence / traffic analysis | ✅ | `sigint emitters`, `track`, `hop-detect` | on/off-pattern alerting |
| Geolocation of an emitter | ✅ RSSI centroid | `sigint locate` | **TDOA multilateration** (see ROADMAP) |

Every row here is a receive-and-analyse capability. RFHound characterises and
locates these threats so a defender can respond; it never performs the attack.

---

## References

- SIGINT/COMINT/ELINT — [Trenton Systems](https://www.trentonsystems.com/en-us/resource-hub/blog/sigint-vs-comint-vs-elint) ·
  [Naval War College LibGuide](https://usnwc.libguides.com/c.php?g=494120&p=3381559)
- RKE / rolling code — [RollJam on SDR (paper)](https://ceur-ws.org/Vol-3731/paper40.pdf) ·
  [RollBack (paper)](https://arxiv.org/pdf/2210.11923) ·
  [Attacking Automotive RKE (2024)](https://eprint.iacr.org/2024/1816.pdf)
- GNSS/ADS-B/AIS — [Maritime GNSS jamming/spoofing guide](https://www.maritimeglobalsecurity.org/media/2cwigtc4/2025-jamming-and-spoofing-2nd-ed-web.pdf) ·
  [FAA GPS interference guide](https://www.faa.gov/about/office_org/headquarters_offices/avs/offices/afx/afs/afs400/afs410/GNSS/GPS_GNSS_Interference_Resource_Guide.pdf) ·
  [ADS-B spoof-detection (Stanford)](https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Liu_ION_GNSS_2024_ADSB_Spoof_Detection.pdf)
- LoRaWAN / IoT — [Trend Micro LoRaWAN attacks](https://www.trendmicro.com/en_us/research/21/a/Low-Powered-but-High-Risk-Evaluating-Possible-Attacks-on-LoRaWAN-Devices.html) ·
  [Selective jamming of LoRaWAN](https://dl.acm.org/doi/pdf/10.1145/3144457.3144478) ·
  [LoRaWAN security review](https://arxiv.org/pdf/2105.00384)
- Cellular — [Cellcrypt air-interface threats](https://www.cellcrypt.com/threats/air-interface/) ·
  [2G→5G security analysis](https://palindrometech.com/applied-security-research-blog/an-evolutionary-analysis-of-cellular-network-security-vulnerabilities-and-protections-from-2g-to-5g) ·
  [IMSI-catcher detection (NDSS)](https://www.ndss-symposium.org/wp-content/uploads/2025-1115-paper.pdf)
- Direction finding / geolocation — [Rohde & Schwarz DF methodologies](https://cdn.rohde-schwarz.com/am/us/campaigns_2/a_d/Intro-to-direction-finding-methodologies.pdf) ·
  [CRFS AoA/DF white paper](https://pages.crfs.com/hubfs/whitepapers/Angle%20of%20Arrival-Direction%20Finding.pdf) ·
  [CRFS DF for EW/SIGINT](https://www.crfs.com/blog/radio-direction-finding-techniques-and-applications-for-ew-and-sigint)
