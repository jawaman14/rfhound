"""Subprocess orchestration and external-tool dependency detection.

RFHound's whole job is to drive other people's excellent CLI tools, so this
module centralises how we find them and how we run them (with timeouts,
streaming, and clean error reporting).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

from .exceptions import DependencyMissingError, ProcessError


@dataclass(frozen=True)
class Tool:
    """Metadata about an external CLI tool RFHound can drive."""

    name: str
    purpose: str
    install_hint: str
    # A command that, if it exits 0, proves the tool works (usually --help).
    probe: tuple[str, ...] | None = None


# The catalogue of external tools RFHound knows how to use.
KNOWN_TOOLS: dict[str, Tool] = {
    "hackrf_info": Tool(
        "hackrf_info",
        "Detect and query the HackRF device",
        "apt install hackrf   (or: brew install hackrf)",
    ),
    "hackrf_sweep": Tool(
        "hackrf_sweep",
        "Wideband spectrum sweeping (1 MHz - 6 GHz)",
        "apt install hackrf",
    ),
    "hackrf_transfer": Tool(
        "hackrf_transfer",
        "Raw IQ record and replay",
        "apt install hackrf",
    ),
    "hackrf_operacake": Tool(
        "hackrf_operacake",
        "Control an Opera Cake antenna-switch add-on (1x8 / dual 1x4)",
        "apt install hackrf   (Opera Cake board required)",
    ),
    "hackrf_clock": Tool(
        "hackrf_clock",
        "Query/configure the clock (onboard 25 MHz or external 10 MHz ref)",
        "apt install hackrf",
    ),
    "rtl_433": Tool(
        "rtl_433",
        "Decode 300-928 MHz ISM devices (TPMS, weather, sensors, fobs)",
        "apt install rtl-433   (build with SoapySDR for HackRF input)",
    ),
    "dump1090": Tool(
        "dump1090",
        "Decode ADS-B aircraft telemetry at 1090 MHz",
        "https://github.com/flightaware/dump1090  (dump1090-fa)",
    ),
    "multimon-ng": Tool(
        "multimon-ng",
        "Decode POCSAG/FLEX pagers, APRS, and more",
        "apt install multimon-ng",
    ),
    "AIS-catcher": Tool(
        "AIS-catcher",
        "Decode AIS marine vessel traffic (161.975 / 162.025 MHz)",
        "https://github.com/jvde-github/AIS-catcher",
    ),
    "acarsdec": Tool(
        "acarsdec",
        "Decode ACARS aircraft messaging (~131 MHz)",
        "https://github.com/TLeconte/acarsdec",
    ),
    "dumpvdl2": Tool(
        "dumpvdl2",
        "Decode VDL Mode 2 aviation data link",
        "https://github.com/szpajder/dumpvdl2",
    ),
    "urh_cli": Tool(
        "urh_cli",
        "Universal Radio Hacker CLI for deep protocol reverse engineering",
        "pip install urh",
    ),
    "soapy_power": Tool(
        "soapy_power",
        "SoapySDR-based power spectrum backend (alternative to hackrf_sweep)",
        "pip install soapy_power",
    ),
    # --- Extended decoder toolset (all receive-only) ---
    "dump978-fa": Tool(
        "dump978-fa", "Decode 978 MHz UAT ADS-B (US general aviation)",
        "https://github.com/flightaware/dump978",
    ),
    "rtlamr": Tool(
        "rtlamr", "Decode ERT smart utility meters (~912 MHz)",
        "https://github.com/bemasher/rtlamr",
    ),
    "satdump": Tool(
        "satdump", "Decode weather/Inmarsat/many satellites and produce imagery",
        "https://github.com/SatDump/SatDump",
    ),
    "iridium-extractor": Tool(
        "iridium-extractor", "Capture Iridium bursts for iridium-toolkit",
        "https://github.com/muccc/gr-iridium",
    ),
    "dsd": Tool(
        "dsd", "Decode digital voice: DMR, P25, NXDN, D-STAR",
        "https://github.com/szechyjs/dsd  (or dsd-fme / dsd-neo)",
    ),
    "direwolf": Tool(
        "direwolf", "Decode AX.25 / APRS packet radio (soundmodem)",
        "apt install direwolf",
    ),
    "nrsc5": Tool(
        "nrsc5", "Decode HD Radio (NRSC-5) digital FM",
        "https://github.com/theori-io/nrsc5",
    ),
    "wsprd": Tool(
        "wsprd", "Decode WSPR weak-signal beacons (HF)",
        "part of WSJT-X: https://wsjt.sourceforge.io/",
    ),
    "tetra-rx": Tool(
        "tetra-rx", "Decode TETRA trunked radio (osmo-tetra)",
        "https://github.com/osmocom/osmo-tetra",
    ),
    "noaa-apt": Tool(
        "noaa-apt", "Decode NOAA APT weather-satellite images (137 MHz)",
        "https://github.com/martinber/noaa-apt",
    ),
    "radiosonde_auto_rx": Tool(
        "radiosonde_auto_rx", "Auto-decode weather-balloon radiosondes (~400 MHz)",
        "https://github.com/projecthorus/radiosonde_auto_rx",
    ),
}


def find_tool(name: str) -> str | None:
    """Return the resolved path of *name* on PATH, or None."""
    return shutil.which(name)


def require_tool(name: str) -> str:
    """Return the path of *name* or raise DependencyMissingError with a hint."""
    path = find_tool(name)
    if path:
        return path
    hint = KNOWN_TOOLS[name].install_hint if name in KNOWN_TOOLS else None
    raise DependencyMissingError(name, hint)


def tool_status() -> list[tuple[Tool, bool, str | None]]:
    """Return (tool, installed, path) for every known tool."""
    out = []
    for tool in KNOWN_TOOLS.values():
        path = find_tool(tool.name)
        out.append((tool, path is not None, path))
    return out


def run(
    args: list[str],
    *,
    timeout: float | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command to completion.

    Returns the CompletedProcess. Raises ProcessError on non-zero exit when
    *check* is True.
    """
    try:
        proc = subprocess.run(
            args,
            timeout=timeout,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DependencyMissingError(args[0]) from exc
    except subprocess.TimeoutExpired as exc:
        # Treat a timeout as a successful bounded capture for sampling tools.
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return subprocess.CompletedProcess(args, 0, stdout, stderr)

    if check and proc.returncode != 0:
        raise ProcessError(" ".join(args), proc.returncode, proc.stderr or "")
    return proc


def stream(
    args: list[str],
    *,
    on_line: Callable[[str], None],
    timeout: float | None = None,
) -> int:
    """Run a command, invoking *on_line* for each stdout line as it arrives.

    Returns the process exit code. A timeout terminates the process cleanly and
    is reported as exit code 0 (useful for "listen for N seconds" style tools).
    """
    import time

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise DependencyMissingError(args[0]) from exc

    start = time.monotonic()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
            if timeout is not None and (time.monotonic() - start) > timeout:
                break
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    return proc.returncode or 0


def hackrf_common_args(cfg, *, for_sweep: bool = False) -> list[str]:
    """Build the shared HackRF hardware flags from config.

    Covers device selection (-d), front-end amp (-a), bias-tee antenna power
    (-p), and — for hackrf_transfer only — baseband filter (-b) and clock ppm
    correction (-C). hackrf_sweep does not accept -b/-C, so they are omitted
    when *for_sweep* is True.
    """
    args: list[str] = []
    if getattr(cfg, "device_serial", ""):
        args += ["-d", cfg.device_serial]
    if getattr(cfg, "amp_enable", False):
        args += ["-a", "1"]
    if getattr(cfg, "antenna_power", False):
        args += ["-p", "1"]
    if not for_sweep:
        if getattr(cfg, "baseband_filter_hz", 0):
            args += ["-b", str(cfg.baseband_filter_hz)]
        if getattr(cfg, "freq_correction_ppm", 0):
            args += ["-C", str(cfg.freq_correction_ppm)]
    return args


def format_command(args: Iterable[str]) -> str:
    """Render a command list as a copy-pasteable shell string."""
    out = []
    for a in args:
        if any(c in a for c in " \t'\"$"):
            a = "'" + a.replace("'", "'\\''") + "'"
        out.append(a)
    return " ".join(out)
