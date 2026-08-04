"""Frequency knowledge base.

A curated map of what lives across the HackRF's 1 MHz - 6 GHz range, why a
security researcher cares, and which decoder RFHound can point at it. This is
what turns a wall of spectrum into "oh, that's a TPMS sensor".

Frequencies are regional; the defaults below lean toward a mix of ITU Region 1
(EU) and Region 2 (US) allocations and are documented as such. Always confirm
your local band plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Band:
    name: str
    low_hz: int
    high_hz: int
    category: str
    description: str
    # Suggested RFHound decoder recipe id (see modules/decode.py), if any.
    decoder: str | None = None
    # Typical center used for tuning a decoder / capture.
    center_hz: int | None = None
    # Region note, e.g. "US", "EU", "global".
    region: str = "global"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def span_hz(self) -> int:
        return self.high_hz - self.low_hz

    @property
    def tune_hz(self) -> int:
        return self.center_hz or (self.low_hz + self.high_hz) // 2


# Ordered low-to-high. Not exhaustive (the spectrum is vast) but covers the
# bands that matter most for RF security work.
BANDS: list[Band] = [
    Band("AM broadcast", 530_000, 1_710_000, "broadcast",
         "Commercial AM radio. Useful as a strong known reference signal.",
         region="global", tags=("reference",)),
    Band("160m/80m HF ham", 1_800_000, 4_000_000, "amateur",
         "Lower HF amateur allocations. HF propagation experiments.",
         region="global", tags=("ham",)),
    Band("Shortwave / HF utility", 3_000_000, 30_000_000, "utility",
         "Shortwave broadcast, HF data modes, utility stations.",
         region="global", tags=("hf",)),
    Band("CB radio", 26_965_000, 27_405_000, "voice",
         "Citizens Band AM/SSB voice.", region="global", tags=("voice",)),
    Band("6m ham", 50_000_000, 54_000_000, "amateur",
         "50 MHz amateur band.", region="global", tags=("ham",)),
    Band("FM broadcast", 87_500_000, 108_000_000, "broadcast",
         "Wideband FM radio + RDS data. Great first signal to demodulate.",
         center_hz=100_000_000, region="global", tags=("reference", "rds")),
    Band("Aircraft VHF (AM)", 108_000_000, 137_000_000, "aviation",
         "VOR/ILS navaids and AM aircraft voice. Receive-only.",
         region="global", tags=("aviation", "voice")),
    Band("ACARS", 129_000_000, 137_000_000, "aviation",
         "Aircraft ACARS text messaging (~131.5 MHz US, 131.725 EU).",
         decoder="acars", center_hz=131_550_000, region="global",
         tags=("aviation", "data")),
    Band("2m ham / VHF", 144_000_000, 148_000_000, "amateur",
         "2m amateur voice, APRS at 144.39 (US) / 144.80 (EU).",
         decoder="aprs", center_hz=144_390_000, region="global",
         tags=("ham", "aprs")),
    Band("Marine VHF / AIS", 156_000_000, 162_100_000, "maritime",
         "Marine voice; AIS vessel tracking at 161.975 & 162.025 MHz.",
         decoder="ais", center_hz=162_000_000, region="global",
         tags=("maritime", "ais")),
    Band("Weather / NOAA sats", 137_000_000, 138_000_000, "satellite",
         "NOAA APT & Meteor weather-satellite downlinks.",
         center_hz=137_500_000, region="global", tags=("satellite", "imagery")),
    Band("Business/public-safety VHF", 150_000_000, 174_000_000, "voice",
         "Land-mobile radio, some trunked systems. Receive-only.",
         region="global", tags=("lmr", "voice")),
    Band("POCSAG/FLEX pagers", 137_000_000, 160_000_000, "paging",
         "Pager traffic (often unencrypted). Common: 138-153 MHz, 929-932 MHz.",
         decoder="pocsag", center_hz=148_000_000, region="global",
         tags=("paging", "cleartext")),
    Band("Wildlife / ISM 315", 314_900_000, 315_100_000, "ism",
         "315 MHz ISM: US key fobs, TPMS, garage remotes.",
         decoder="rtl433", center_hz=315_000_000, region="US",
         tags=("ism", "keyfob", "tpms", "iot")),
    Band("UHF public-safety / LMR", 380_000_000, 470_000_000, "voice",
         "UHF land-mobile, TETRA (EU), P25 (US). Receive-only.",
         region="global", tags=("lmr", "tetra", "p25")),
    Band("ISM 433 MHz", 433_050_000, 434_790_000, "ism",
         "The busiest hobby ISM band: remotes, weather stations, sensors, "
         "TPMS, alarms, doorbells. Start here.",
         decoder="rtl433", center_hz=433_920_000, region="EU/global",
         tags=("ism", "keyfob", "tpms", "iot", "sensors")),
    Band("LoRa 433", 433_050_000, 434_790_000, "iot",
         "LoRa long-range IoT in the 433 ISM band.",
         center_hz=433_920_000, region="EU/global", tags=("lora", "iot")),
    Band("70cm ham", 430_000_000, 440_000_000, "amateur",
         "UHF amateur band overlapping ISM 433.",
         region="global", tags=("ham",)),
    Band("PMR446 / FRS/GMRS", 446_000_000, 470_000_000, "voice",
         "Licence-free handhelds (PMR446 EU, FRS/GMRS US).",
         region="global", tags=("voice",)),
    Band("ISM 868 MHz", 863_000_000, 870_000_000, "ism",
         "EU sub-GHz ISM: smart meters, LoRaWAN, home automation, alarms.",
         decoder="rtl433", center_hz=868_300_000, region="EU",
         tags=("ism", "lorawan", "smartmeter", "iot")),
    Band("GSM-900 downlink", 925_000_000, 960_000_000, "cellular",
         "Legacy 2G GSM downlink. Analysis with gr-gsm (RX only, sensitive).",
         center_hz=942_000_000, region="EU/global", tags=("cellular", "2g")),
    Band("ISM 915 MHz", 902_000_000, 928_000_000, "ism",
         "US sub-GHz ISM: smart meters (rtlamr), LoRa, Z-Wave (US 908.4), "
         "industrial telemetry, fobs.",
         decoder="rtl433", center_hz=915_000_000, region="US",
         tags=("ism", "lora", "zwave", "smartmeter", "iot")),
    Band("Pagers 929-932", 929_000_000, 932_000_000, "paging",
         "US POCSAG/FLEX paging downlink.",
         decoder="pocsag", center_hz=930_000_000, region="US",
         tags=("paging", "cleartext")),
    Band("ADS-B (1090ES)", 1_089_000_000, 1_091_000_000, "aviation",
         "Aircraft ADS-B position/ID broadcasts at 1090 MHz. Passive, rich.",
         decoder="adsb", center_hz=1_090_000_000, region="global",
         tags=("aviation", "adsb", "tracking")),
    Band("ADS-B UAT (978)", 977_000_000, 979_000_000, "aviation",
         "US general-aviation ADS-B on 978 MHz UAT.",
         center_hz=978_000_000, region="US", tags=("aviation", "adsb")),
    Band("GPS L1", 1_574_420_000, 1_576_420_000, "gnss",
         "GPS L1 downlink at 1575.42 MHz. Receive-only; TX is illegal & unsafe.",
         center_hz=1_575_420_000, region="global", tags=("gnss", "gps")),
    Band("Inmarsat / Iridium", 1_616_000_000, 1_626_500_000, "satellite",
         "Iridium (1616-1626.5) & Inmarsat L-band downlinks.",
         center_hz=1_621_000_000, region="global", tags=("satellite",)),
    Band("DECT cordless", 1_880_000_000, 1_900_000_000, "voice",
         "EU DECT cordless phones (US: 1920-1930).",
         center_hz=1_890_000_000, region="EU", tags=("voice", "dect")),
    Band("Drone control 900 MHz", 902_000_000, 928_000_000, "cuas",
         "Long-range drone control/telemetry links (e.g. some ELRS/915 sets).",
         center_hz=915_000_000, region="US", tags=("drone", "cuas", "control")),
    Band("Drone video 1.2/1.3 GHz", 1_150_000_000, 1_300_000_000, "cuas",
         "Analog FPV video downlink band used by some drones.",
         center_hz=1_280_000_000, region="global", tags=("drone", "cuas", "video")),
    Band("Drone control/video 2.4 GHz", 2_400_000_000, 2_483_500_000, "cuas",
         "Most common consumer drone control + video (DJI OcuSync, etc.).",
         center_hz=2_442_000_000, region="global", tags=("drone", "cuas", "control", "video")),
    Band("Drone FPV video 5.8 GHz", 5_645_000_000, 5_945_000_000, "cuas",
         "Analog/HD FPV video downlink — the classic racing/FPV band.",
         center_hz=5_800_000_000, region="global", tags=("drone", "cuas", "video")),
    Band("2.4 GHz ISM (Wi-Fi/BLE/ZigBee)", 2_400_000_000, 2_483_500_000, "ism",
         "Wi-Fi, Bluetooth/BLE, ZigBee, RC, microwave leakage. Wideband. Note: "
         "Wi-Fi/BLE are better attacked with dedicated NICs; use SDR for the "
         "PHY view and non-standard emitters.",
         center_hz=2_442_000_000, region="global",
         tags=("wifi", "ble", "zigbee", "ism")),
    Band("5 GHz ISM/U-NII (Wi-Fi)", 5_150_000_000, 5_850_000_000, "ism",
         "5 GHz Wi-Fi and other emitters (near the HackRF's upper edge).",
         center_hz=5_500_000_000, region="global", tags=("wifi", "ism")),
]


CATEGORIES: dict[str, str] = {
    "ism": "Licence-free ISM — the richest hunting ground (fobs, TPMS, IoT)",
    "aviation": "Aircraft telemetry & messaging (passive, legal to receive)",
    "maritime": "Ship tracking (AIS) and marine voice",
    "paging": "Pager networks — frequently sent in the clear",
    "cellular": "Cellular (2G+) — receive/analysis only, legally sensitive",
    "satellite": "Satellite downlinks (weather imagery, L-band)",
    "gnss": "Global navigation (GPS) — receive-only",
    "broadcast": "Commercial broadcast — great calibration references",
    "amateur": "Amateur radio allocations",
    "voice": "Land-mobile / voice services",
    "utility": "HF utility and data",
    "iot": "IoT / long-range radio (LoRa, LoRaWAN)",
    "cuas": "Counter-UAS — drone control & video bands (detection only)",
}


# ITU frequency-band designations (the "what range am I in?" chart).
ITU_BANDS: list[tuple[str, str, int, int]] = [
    ("VLF", "Very Low Frequency", 3_000, 30_000),
    ("LF", "Low Frequency", 30_000, 300_000),
    ("MF", "Medium Frequency", 300_000, 3_000_000),
    ("HF", "High Frequency", 3_000_000, 30_000_000),
    ("VHF", "Very High Frequency", 30_000_000, 300_000_000),
    ("UHF", "Ultra High Frequency", 300_000_000, 3_000_000_000),
    ("SHF", "Super High Frequency (microwave)", 3_000_000_000, 30_000_000_000),
    ("EHF", "Extremely High Frequency (mmWave)", 30_000_000_000, 300_000_000_000),
]


def itu_band(freq_hz: int) -> tuple[str, str, int, int] | None:
    """Return the ITU band designation (abbr, name, low_hz, high_hz) for a freq."""
    for abbr, name, lo, hi in ITU_BANDS:
        if lo <= freq_hz < hi:
            return (abbr, name, lo, hi)
    return None


def itu_label(freq_hz: int) -> str:
    """Short human label, e.g. 'UHF (300 MHz–3 GHz)'."""
    b = itu_band(freq_hz)
    if not b:
        return "—"
    _, _, lo, hi = b

    def fmt(h):
        if h >= 1e9:
            return f"{h/1e9:.0f} GHz"
        if h >= 1e6:
            return f"{h/1e6:.0f} MHz"
        return f"{h/1e3:.0f} kHz"

    return f"{b[0]} ({fmt(lo)}–{fmt(hi)})"


def find_band(freq_hz: int) -> Band | None:
    """Return the most specific band containing *freq_hz*, if any.

    Broad service allocations (e.g. UHF LMR 380-470 MHz) overlap narrow, more
    interesting ones (e.g. ISM 433 MHz). When several bands match we return the
    narrowest, and among equal spans we prefer one that has a decoder — the more
    actionable answer for a security researcher.
    """
    matches = [b for b in BANDS if b.low_hz <= freq_hz <= b.high_hz]
    if not matches:
        return None
    matches.sort(key=lambda b: (b.span_hz, b.decoder is None))
    return matches[0]


def bands_by_category(category: str) -> list[Band]:
    return [b for b in BANDS if b.category == category]


def bands_by_tag(tag: str) -> list[Band]:
    return [b for b in BANDS if tag in b.tags]


def survey_targets() -> list[Band]:
    """Bands worth auto-sweeping in a recon run (active, decodable, legal RX)."""
    wanted = {"ism", "aviation", "maritime", "paging", "iot"}
    return [b for b in BANDS if b.category in wanted]
