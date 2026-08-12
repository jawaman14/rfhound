"""Self-test / fault-finding diagnostics.

``doctor`` tells you what tools are installed; this goes further and actually
exercises the environment — config parses, output dir is writable, disk isn't
full, optional deps import, the HackRF answers, and the core tools respond to a
probe. Every check returns a status and, when it fails, an actionable hint, so a
user (or a bug report) can see exactly what's wrong and how to fix it.

Tool probes are run concurrently (they each shell out) via ``rfhound.parallel``.
"""

from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import parallel, proc
from ..config import Config, config_path

OK = "ok"
WARN = "warn"
FAIL = "fail"

# Tools whose absence is worth surfacing in a self-test (the rest are optional
# decoders that only matter if you use that band).
CORE_TOOLS = ("hackrf_info", "hackrf_sweep", "hackrf_transfer")


@dataclass
class Check:
    name: str
    status: str            # ok | warn | fail
    detail: str
    hint: str = ""

    @property
    def symbol(self) -> str:
        return {"ok": "✓", "warn": "!", "fail": "✗"}.get(self.status, "?")


def _check_python() -> Check:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 9):
        return Check("Python", FAIL, f"{ver} (need >= 3.9)", "Upgrade to Python 3.9+")
    return Check("Python", OK, f"{ver} on {platform.system()}")


def _check_config(cfg: Config) -> Check:
    path = config_path()
    if not path.exists():
        return Check("Config", OK, "using built-in defaults (no file yet)",
                     "Write one with: rfhound config init")
    try:
        from ..config import load_config
        load_config()
        return Check("Config", OK, f"parsed {path}")
    except Exception as exc:  # noqa: BLE001
        return Check("Config", FAIL, f"{path}: {exc}",
                     "Fix the JSON, or reset with: rfhound config init")


def _check_writable(label: str, directory: Path, hint: str) -> Check:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".rfhound-probe-", delete=True):
            pass
        return Check(label, OK, f"writable: {directory}")
    except OSError as exc:
        return Check(label, FAIL, f"{directory}: {exc}", hint)


def _check_disk(cfg: Config) -> Check:
    target = Path(cfg.output_dir)
    probe = target if target.exists() else target.parent
    try:
        usage = shutil.disk_usage(probe if probe.exists() else Path.home())
    except OSError as exc:
        return Check("Disk space", WARN, f"could not stat {probe}: {exc}")
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 100:
        return Check("Disk space", FAIL, f"{free_mb:.0f} MB free at {probe}",
                     "Free space before capturing IQ (recordings are large)")
    if free_mb < 1024:
        return Check("Disk space", WARN, f"{free_mb:.0f} MB free at {probe}",
                     "IQ captures fill space fast; keep an eye on it")
    return Check("Disk space", OK, f"{free_mb / 1024:.1f} GB free at {probe}")


def _check_numpy() -> Check:
    try:
        import numpy  # noqa: F401
        return Check("numpy (IQ tools)", OK, f"v{numpy.__version__}")
    except ImportError:
        return Check("numpy (IQ tools)", WARN, "not installed",
                     "IQ analysis is limited; install with: pip install 'rfhound[iq]'")


def _check_rich() -> Check:
    try:
        import rich  # noqa: F401
    except ImportError:
        return Check("rich (UI)", WARN, "not installed — plain-text fallback",
                     "For the full UI: pip install rich")
    try:
        from importlib.metadata import version
        ver = version("rich")
    except Exception:  # noqa: BLE001
        ver = getattr(rich, "__version__", "?")
    return Check("rich (UI)", OK, f"v{ver}")


def _check_device() -> Check:
    from .. import device
    from ..exceptions import RFHoundError
    try:
        info = device.get_info()
        return Check("HackRF device", OK, f"serial {info.serial}, fw {info.firmware}")
    except RFHoundError as exc:
        return Check("HackRF device", WARN, str(exc).splitlines()[0],
                     "Use --simulate to run without hardware; check USB / 'rf' group perms")


def _probe_tool(name: str) -> Check:
    path = proc.find_tool(name)
    if not path:
        hint = proc.KNOWN_TOOLS[name].install_hint if name in proc.KNOWN_TOOLS else ""
        return Check(name, WARN, "not on PATH", hint)
    return Check(name, OK, path)


def run_diagnostics(cfg: Config, *, deep: bool = True) -> list[Check]:
    """Run all checks and return them in display order.

    ``deep`` also probes the core external tools concurrently. Set it False for
    a quick environment-only pass.
    """
    checks = [
        _check_python(),
        _check_config(cfg),
        _check_writable("Output dir", Path(cfg.output_dir),
                        "Set a writable path: rfhound config set output_dir <dir>"),
        _check_writable("Config dir", config_path().parent,
                        "Check permissions on ~/.config/rfhound"),
        _check_disk(cfg),
        _check_numpy(),
        _check_rich(),
        _check_device(),
    ]
    if deep:
        jobs = {name: (lambda n=name: _probe_tool(n)) for name in CORE_TOOLS}
        res = parallel.run_jobs(jobs, workers=getattr(cfg, "scan_workers", 4))
        # Preserve CORE_TOOLS order regardless of completion order.
        checks.extend(res[name].value for name in CORE_TOOLS)
    return checks


def summarize(checks: list[Check]) -> dict:
    counts = {OK: 0, WARN: 0, FAIL: 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    return {"ok": counts[OK], "warn": counts[WARN], "fail": counts[FAIL],
            "healthy": counts[FAIL] == 0}
