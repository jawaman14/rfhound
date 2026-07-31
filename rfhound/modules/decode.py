"""Protocol decoders.

Rather than re-implementing DSP, RFHound keeps a registry of *decoder recipes*.
Each recipe knows which external tool it needs, how to build the command for a
given frequency, and what it produces. This keeps RFHound honest (it never
pretends to decode something it can't) and extensible (add a recipe = add a
capability).

All recipes are receive-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import proc
from ..config import Config
from ..exceptions import DependencyMissingError


@dataclass
class Recipe:
    id: str
    name: str
    category: str
    tool: str
    default_freq_hz: int
    description: str
    # Build the argv for this recipe given (cfg, freq_hz, seconds).
    build: Callable[[Config, int, float], list[str]]
    # Legal / usage note surfaced to the operator.
    note: str = ""


def _rtl433(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    # rtl_433 with a SoapySDR HackRF source; -F json for machine-readable output.
    return [
        "rtl_433",
        "-d", "driver=hackrf",
        "-f", str(freq_hz),
        "-F", "json",
        "-M", "level",
    ]


def _adsb(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    # dump1090 built with SoapySDR/HackRF support.
    return [
        "dump1090",
        "--device-type", "hackrf",
        "--freq", str(freq_hz),
        "--net",
    ]


def _pocsag(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    # multimon-ng expects demodulated audio on stdin; RFHound documents the
    # canonical pipeline. Here we surface the multimon-ng half; the front-end
    # FM demod is provided in docs/USAGE.md (hackrf_transfer | csdr | ...).
    return [
        "multimon-ng",
        "-a", "POCSAG512",
        "-a", "POCSAG1200",
        "-a", "POCSAG2400",
        "-f", "alpha",
        "-",
    ]


def _aprs(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["multimon-ng", "-a", "AFSK1200", "-A", "-"]


def _ais(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["AIS-catcher", "-d", "driver=hackrf", "-v"]


def _acars(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["acarsdec", "-r", "hackrf", str(freq_hz)]


def _flex(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["multimon-ng", "-a", "FLEX", "-f", "alpha", "-"]


def _uat978(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["dump978-fa", "--sdr", "driver=hackrf", "--json-stdout"]


def _vdl2(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["dumpvdl2", "--soapysdr", "driver=hackrf", "--centerfreq", str(freq_hz)]


def _ert(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    # rtlamr reads from an rtl_tcp-style source; documented pipeline in USAGE.
    return ["rtlamr", "-format", "json"]


def _dsd(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    # Digital voice: consumes discriminator audio on stdin (see USAGE.md).
    return ["dsd", "-i", "-", "-o", "/dev/null", "-w", "dsd_out.wav"]


def _aprs_ax25(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["direwolf", "-n", "1", "-r", "48000", "-"]


def _hdradio(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["nrsc5", "-d", "driver=hackrf", str(int(freq_hz)), "0"]


def _wspr(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["wsprd", "-f", f"{freq_hz/1e6:.6f}", "wspr.wav"]


def _tetra(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["tetra-rx", "-"]


def _noaa_apt(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["noaa-apt", "-o", "noaa.png", "input.wav"]


def _radiosonde(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["radiosonde_auto_rx"]


def _satdump(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["satdump", "live", "auto", "./satout",
            "--source", "hackrf", "--frequency", str(freq_hz)]


def _iridium(cfg: Config, freq_hz: int, seconds: float) -> list[str]:
    return ["iridium-extractor", "-D", "4", "hackrf.conf"]


RECIPES: dict[str, Recipe] = {
    "rtl433": Recipe(
        "rtl433", "ISM device decoder (rtl_433)", "ism", "rtl_433",
        433_920_000,
        "Decodes hundreds of 300-928 MHz devices: TPMS, weather stations, "
        "temperature/door/PIR sensors, some remotes. The best first decoder.",
        _rtl433,
        note="Passive receive. Great for asset discovery in a facility.",
    ),
    "adsb": Recipe(
        "adsb", "ADS-B aircraft (dump1090)", "aviation", "dump1090",
        1_090_000_000,
        "Decodes aircraft ICAO id, position, altitude, velocity at 1090 MHz.",
        _adsb,
        note="Passive, legal to receive in most jurisdictions.",
    ),
    "pocsag": Recipe(
        "pocsag", "POCSAG/FLEX pagers (multimon-ng)", "paging", "multimon-ng",
        929_000_000,
        "Decodes pager messages, which are frequently unencrypted. Demonstrates "
        "cleartext-messaging risk in an environment.",
        _pocsag,
        note="Requires an FM-demod front-end feeding stdin (see docs/USAGE.md). "
             "Pager content may be personal data — handle per your rules of "
             "engagement.",
    ),
    "aprs": Recipe(
        "aprs", "APRS packet radio (multimon-ng)", "amateur", "multimon-ng",
        144_390_000,
        "Decodes AFSK1200 APRS position/telemetry packets.",
        _aprs,
        note="Requires FM-demod front-end feeding stdin.",
    ),
    "ais": Recipe(
        "ais", "AIS vessel tracking (AIS-catcher)", "maritime", "AIS-catcher",
        162_000_000,
        "Decodes ship position/identity beacons (MMSI, position, course).",
        _ais,
        note="Passive receive.",
    ),
    "acars": Recipe(
        "acars", "ACARS aircraft messaging (acarsdec)", "aviation", "acarsdec",
        131_550_000,
        "Decodes aircraft/ground text messaging around 131 MHz.",
        _acars,
        note="Passive receive.",
    ),
    "uat978": Recipe(
        "uat978", "ADS-B UAT 978 MHz (dump978-fa)", "aviation", "dump978-fa",
        978_000_000,
        "Decodes US general-aviation ADS-B on the 978 MHz UAT link.",
        _uat978, note="Passive receive.",
    ),
    "vdl2": Recipe(
        "vdl2", "VDL Mode 2 aviation data (dumpvdl2)", "aviation", "dumpvdl2",
        136_975_000,
        "Decodes VHF Digital Link Mode 2 aircraft data around 136 MHz.",
        _vdl2, note="Passive receive.",
    ),
    "flex": Recipe(
        "flex", "FLEX pagers (multimon-ng)", "paging", "multimon-ng",
        929_000_000,
        "Decodes FLEX pager messages (often unencrypted).",
        _flex,
        note="Requires an FM-demod front-end feeding stdin; pager content may be "
             "personal data — handle per your rules of engagement.",
    ),
    "ert": Recipe(
        "ert", "Smart utility meters / ERT (rtlamr)", "ism", "rtlamr",
        912_600_000,
        "Decodes ERT/SCM smart electricity/gas/water meters near 912 MHz.",
        _ert, note="Utility-metering recon; passive receive.",
    ),
    "dsd": Recipe(
        "dsd", "Digital voice DMR/P25/NXDN (dsd)", "voice", "dsd",
        450_000_000,
        "Decodes unencrypted digital voice (DMR, P25, NXDN, D-STAR).",
        _dsd,
        note="Requires a discriminator-audio front-end feeding stdin. Encrypted "
             "traffic is not decodable and must not be targeted.",
    ),
    "aprs_ax25": Recipe(
        "aprs_ax25", "AX.25 / APRS packet (direwolf)", "amateur", "direwolf",
        144_390_000,
        "Decodes AX.25/APRS packet radio via the direwolf soundmodem.",
        _aprs_ax25, note="Requires an FM-demod front-end feeding stdin.",
    ),
    "hdradio": Recipe(
        "hdradio", "HD Radio / NRSC-5 (nrsc5)", "broadcast", "nrsc5",
        98_100_000,
        "Decodes digital HD Radio subchannels on the FM broadcast band.",
        _hdradio, note="Passive receive; a good strong-signal reference.",
    ),
    "wspr": Recipe(
        "wspr", "WSPR weak-signal beacons (wsprd)", "amateur", "wsprd",
        14_095_600,
        "Decodes WSPR propagation beacons (HF). Needs frequency conversion for "
        "HF on a HackRF (1 MHz+ only).",
        _wspr, note="Passive receive.",
    ),
    "tetra": Recipe(
        "tetra", "TETRA trunked radio (tetra-rx)", "voice", "tetra-rx",
        395_000_000,
        "Decodes unencrypted TETRA control/voice (osmo-tetra).",
        _tetra,
        note="Requires a front-end feeding stdin. Encrypted networks are not "
             "decodable and must not be targeted.",
    ),
    "noaa_apt": Recipe(
        "noaa_apt", "NOAA APT weather imagery (noaa-apt)", "satellite", "noaa-apt",
        137_500_000,
        "Decodes NOAA APT weather-satellite images from a recorded WAV pass.",
        _noaa_apt, note="Two-step: record the pass, then decode the WAV.",
    ),
    "radiosonde": Recipe(
        "radiosonde", "Weather-balloon radiosondes (auto_rx)", "aviation",
        "radiosonde_auto_rx", 403_000_000,
        "Auto-detects and decodes radiosonde telemetry (~400-406 MHz).",
        _radiosonde, note="Passive receive.",
    ),
    "satdump": Recipe(
        "satdump", "Satellites & imagery (SatDump)", "satellite", "satdump",
        137_100_000,
        "Live-decodes many weather/L-band satellites and produces imagery.",
        _satdump, note="Passive receive; see SatDump docs for per-satellite setup.",
    ),
    "iridium": Recipe(
        "iridium", "Iridium bursts (gr-iridium)", "satellite", "iridium-extractor",
        1_621_250_000,
        "Captures Iridium L-band bursts for offline processing with "
        "iridium-toolkit.",
        _iridium, note="Passive receive; legal sensitivity varies by jurisdiction.",
    ),
}


def list_recipes() -> list[Recipe]:
    return list(RECIPES.values())


def get_recipe(recipe_id: str) -> Recipe | None:
    return RECIPES.get(recipe_id)


def check_recipe(recipe: Recipe) -> tuple[bool, str | None]:
    """Return (available, path) for a recipe's required tool."""
    path = proc.find_tool(recipe.tool)
    return path is not None, path


def build_command(
    recipe: Recipe, cfg: Config, *, freq_hz: int | None = None, seconds: float = 30
) -> list[str]:
    return recipe.build(cfg, freq_hz or recipe.default_freq_hz, seconds)


def run_decoder(
    recipe: Recipe,
    cfg: Config,
    *,
    freq_hz: int | None = None,
    seconds: float = 30,
    on_line: Callable[[str], None] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Run a decoder recipe, collecting output lines. Returns the lines.

    With dry_run=True, returns a single element: the command that *would* run.
    """
    cmd = build_command(recipe, cfg, freq_hz=freq_hz, seconds=seconds)
    if dry_run:
        return [proc.format_command(cmd)]
    if not proc.find_tool(recipe.tool):
        from ..proc import KNOWN_TOOLS
        hint = KNOWN_TOOLS[recipe.tool].install_hint if recipe.tool in KNOWN_TOOLS else None
        raise DependencyMissingError(recipe.tool, hint)
    lines: list[str] = []

    def _collect(line: str) -> None:
        lines.append(line)
        if on_line:
            on_line(line)

    proc.stream(cmd, on_line=_collect, timeout=seconds)
    return lines
