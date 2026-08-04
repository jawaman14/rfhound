# References & further reading

A curated library RFHound draws on — for identifying signals, learning SDR, and
finding the right decoder. (Links are informational; verify anything legal or
safety-critical against primary sources.)

## Signal identification
- **Signal Identification Guide (sigidwiki)** — https://www.sigidwiki.com/ —
  audio/waterfall samples for hundreds of signals; the go-to "what is this?".
- **RTL-SDR.com** — https://www.rtl-sdr.com/ — tutorials, the big supported-software list.
- **priyom.org** — https://priyom.org/ — HF utility & number-station reference.

## Handbooks & courses
- **"Software-Defined Radio for Engineers"** (Analog Devices, free PDF) —
  https://www.analog.com/en/education/education-library/software-defined-radio-for-engineers.html
- **PySDR: A Guide to SDR and DSP using Python** — https://pysdr.org/
- **The ARRL Handbook** (radio theory reference; print/paid).
- **GNU Radio tutorials** — https://wiki.gnuradio.org/index.php/Tutorials

## Tool & decoder lists
- **Awesome SDR** — https://github.com/vkvbit/awesome-sdr and
  https://github.com/CanYoleri/awesome-SDR
- **The BIG list of RTL-SDR supported software** — https://www.rtl-sdr.com/big-list-rtl-sdr-supported-software/

## Decoders RFHound drives (upstream)
- rtl_433 — https://github.com/merbanan/rtl_433
- dump1090 (ADS-B) — https://github.com/flightaware/dump1090
- dump978 (UAT) — https://github.com/flightaware/dump978
- dumpvdl2 — https://github.com/szpajder/dumpvdl2
- acarsdec — https://github.com/TLeconte/acarsdec
- multimon-ng (POCSAG/FLEX/APRS) — https://github.com/EliasOenal/multimon-ng
- AIS-catcher — https://github.com/jvde-github/AIS-catcher
- rtlamr (ERT meters) — https://github.com/bemasher/rtlamr
- dsd / dsd-fme (DMR/P25) — https://github.com/szechyjs/dsd
- direwolf (AX.25/APRS) — https://github.com/wb2osz/direwolf
- nrsc5 (HD Radio) — https://github.com/theori-io/nrsc5
- SatDump — https://github.com/SatDump/SatDump
- gr-iridium — https://github.com/muccc/gr-iridium
- radiosonde_auto_rx — https://github.com/projecthorus/radiosonde_auto_rx
- noaa-apt — https://github.com/martinber/noaa-apt

## Analysis & platforms (interoperate)
- **Universal Radio Hacker (URH)** — https://github.com/jopohl/urh — protocol RE & fuzzing.
- **inspectrum** — https://github.com/miek/inspectrum — offline capture inspection.
- **GNU Radio** — https://www.gnuradio.org/ — custom DSP flowgraphs.
- **SDRangel / GQRX / CubicSDR** — full-featured SDR receivers (UX inspiration).

## Defensive / detection research
- **SnoopSnitch** (IMSI-catcher/SS7 detection) — https://github.com/srlabs/snoopsnitch
- **EFF Crocodile Hunter** (fake base stations) — https://github.com/EFForg/crocodilehunter
- **ADS-B spoofing detection** (paper) — https://arxiv.org/pdf/1904.09969

## Standards & regulation
- **SigMF** (IQ metadata) — https://github.com/sigmf/SigMF
- Know your local regulator before transmitting (FCC / Ofcom / ITU / your national body).
  See [LEGAL.md](LEGAL.md).
