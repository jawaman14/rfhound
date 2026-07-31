"""Guided interactive menu — the friendly front door.

For people who don't want to memorise subcommands. Every action here maps onto
the same modules the CLI uses, and it will happily run in ``--simulate`` mode
when no HackRF is attached.
"""

from __future__ import annotations

from pathlib import Path

from . import bandplan, console, device
from .config import Config
from .exceptions import RFHoundError
from .modules import decode as decode_mod
from .modules import recon as recon_mod
from .modules import sweep as sweep_mod


def _hardware_or_simulate() -> bool:
    """Return True if we should simulate (no hardware present)."""
    if device.is_present():
        return False
    console.warn("No HackRF detected — running in SIMULATE mode.")
    return True


def _menu_recon(cfg: Config, simulate: bool) -> None:
    console.rule("Recon survey")
    report = recon_mod.run_recon(cfg, simulate=simulate)
    recon_mod.summarize(report)
    if console.confirm("Save a report?", default=False):
        name = console.ask("Report path", default="rfhound-recon.md")
        out = Path(name)
        from .modules import report as report_mod
        fmt = "html" if out.suffix.lower() in (".html", ".htm") else "md"
        report_mod.write_report(report, out, fmt=fmt)
        console.success(f"Wrote {out}")


def _menu_sweep(cfg: Config, simulate: bool) -> None:
    console.rule("Spectrum sweep")
    start = float(console.ask("Start MHz", default="430"))
    stop = float(console.ask("Stop MHz", default="440"))
    result = sweep_mod.sweep(cfg, start, stop, simulate=simulate)
    sweep_mod.render_spectrum(result)
    rows = [
        [f"{p.freq_mhz:.4f}", f"{p.power_db}", p.band.name if p.band else "unknown"]
        for p in result.peaks[:15]
    ]
    if rows:
        console.table("Peaks", ["Freq (MHz)", "Power (dB)", "Band"], rows)
    else:
        console.warn("No peaks found.")


def _menu_bands(cfg: Config) -> None:
    console.rule("Frequency knowledge base")
    console.print_("Categories: " + ", ".join(sorted({b.category for b in bandplan.BANDS})))
    cat = console.ask("Filter by category (blank = all)", default="")
    bands = bandplan.bands_by_category(cat) if cat else bandplan.BANDS
    rows = [
        [f"{b.low_hz/1e6:.3f}-{b.high_hz/1e6:.3f}", b.name, b.category, b.decoder or "-"]
        for b in bands
    ]
    console.table("Bands (MHz)", ["Range", "Name", "Category", "Decoder"], rows)


def _menu_decoders(cfg: Config, simulate: bool) -> None:
    console.rule("Protocol decoders")
    recipes = decode_mod.list_recipes()
    rows = []
    for i, r in enumerate(recipes, 1):
        available, _ = decode_mod.check_recipe(r)
        rows.append([str(i), r.id, r.name, "ready" if available else "tool missing"])
    console.table("Recipes", ["#", "ID", "Name", "Status"], rows)
    choice = console.ask("Recipe id to run (blank to cancel)", default="")
    if not choice:
        return
    recipe = decode_mod.get_recipe(choice)
    if not recipe:
        console.error("Unknown recipe.")
        return
    console.print_(f"note: {recipe.note}")
    cmd = decode_mod.run_decoder(recipe, cfg, dry_run=True)
    console.print_(f"Command: {cmd[0]}")
    if simulate:
        console.warn("Simulate mode: not executing decoder (no hardware).")
        return
    if console.confirm("Run it now?", default=False):
        try:
            decode_mod.run_decoder(recipe, cfg, seconds=20, on_line=console.print_)
        except RFHoundError as exc:
            console.error(str(exc))


def _menu_doctor(cfg: Config) -> None:
    from .cli import cmd_doctor
    import argparse
    cmd_doctor(argparse.Namespace(), cfg)


MENU = [
    ("Recon survey (what's around me?)", _menu_recon),
    ("Spectrum sweep (custom range)", _menu_sweep),
    ("Browse frequency knowledge base", None),
    ("Protocol decoders", _menu_decoders),
    ("Environment check (doctor)", None),
    ("Quit", None),
]


def run_menu(cfg: Config) -> int:
    simulate = _hardware_or_simulate()
    while True:
        console.rule("RFHound — main menu")
        for i, (label, _) in enumerate(MENU, 1):
            console.print_(f"  {i}. {label}")
        choice = console.ask("Choose", default="1")
        if choice in ("6", "q", "quit", "exit"):
            console.print_("73! (goodbye)")
            return 0
        try:
            n = int(choice)
        except ValueError:
            console.warn("Enter a number.")
            continue
        try:
            if n == 1:
                _menu_recon(cfg, simulate)
            elif n == 2:
                _menu_sweep(cfg, simulate)
            elif n == 3:
                _menu_bands(cfg)
            elif n == 4:
                _menu_decoders(cfg, simulate)
            elif n == 5:
                _menu_doctor(cfg)
            else:
                console.warn("Invalid choice.")
        except (RFHoundError, ValueError) as exc:
            console.error(str(exc))
        except KeyboardInterrupt:
            console.print_("")
            continue
