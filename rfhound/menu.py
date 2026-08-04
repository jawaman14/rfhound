"""Guided interactive menu — the friendly front door.

For people who don't want to memorise subcommands. Every action maps onto the
same modules the CLI uses, and it runs in ``--simulate`` mode when no HackRF is
attached. Kept in step with the CLI so newcomers can reach every capability.
"""

from __future__ import annotations

from pathlib import Path

from . import bandplan, console, device
from .config import Config, save_config
from .exceptions import RFHoundError
from .modules import cellular as cellular_mod
from .modules import classify as classify_mod
from .modules import decode as decode_mod
from .modules import defense as defense_mod
from .modules import intel as intel_mod
from .modules import recon as recon_mod
from .modules import response as response_mod
from .modules import sweep as sweep_mod
from .modules import toolbox as toolbox_mod


def _hardware_or_simulate() -> bool:
    if device.is_present():
        return False
    console.warn("No HackRF detected — running in SIMULATE mode.")
    return True


# --------------------------------------------------------------------------- #
def _menu_recon(cfg: Config, simulate: bool) -> None:
    console.rule("Recon survey — what's around me?")
    with console.status("Surveying high-value bands…"):
        report = recon_mod.run_recon(cfg, simulate=simulate, progress=False)
    recon_mod.summarize(report)
    if console.confirm("Save a report?", default=False):
        out = Path(console.ask("Report path", default="rfhound-recon.md"))
        from .modules import report as report_mod
        fmt = "html" if out.suffix.lower() in (".html", ".htm") else "md"
        report_mod.write_report(report, out, fmt=fmt)
        console.success(f"Wrote {out}")


def _menu_sweep(cfg: Config, simulate: bool) -> None:
    console.rule("Spectrum sweep")
    start = float(console.ask("Start MHz", default="430"))
    stop = float(console.ask("Stop MHz", default="440"))
    with console.status(f"Sweeping {start}-{stop} MHz…"):
        result = sweep_mod.sweep(cfg, start, stop, simulate=simulate)
    sweep_mod.render_spectrum(result)
    if result.peaks:
        rows = []
        for p in result.peaks[:15]:
            bw = classify_mod.estimate_bandwidth_khz(result, p.freq_hz)
            g = classify_mod.classify(p.freq_mhz, bandwidth_khz=bw)[0]
            rows.append([f"{p.freq_mhz:.4f}", f"{p.power_db}",
                         f"{bw:.0f} kHz" if bw else "—", f"{g.name} ({g.likelihood}%)",
                         g.decoder or "—"])
        console.table("Peaks — auto-identified",
                      ["Freq (MHz)", "Power dB", "Bandwidth", "Likely signal", "Decoder"], rows)
    else:
        console.warn("No peaks found.")


def _menu_identify(cfg: Config, simulate: bool) -> None:
    console.rule("Identify a frequency / protocol")
    q = console.ask("Frequency in MHz, or a protocol name (adsb, tpms, pager…)",
                    default="433.92")
    try:
        freq = float(q)
    except ValueError:
        matches = toolbox_mod.tune_search(q)
        if not matches:
            console.warn(f"No band matches '{q}'.")
            return
        rows = [[f"{m.tune_mhz:.4f}", m.name, m.category, m.decoder or "—"] for m in matches]
        console.table(f"Tune to — '{q}'", ["Freq (MHz)", "Band", "Category", "Decoder"], rows)
        return
    tb = toolbox_mod.at_frequency(freq)
    itu = bandplan.itu_label(int(freq * 1e6))
    guess = classify_mod.classify(freq)[0]
    if tb:
        console.print_(f"[bold]{tb.band.name}[/bold] · {itu} · likely: {guess.name} "
                       f"({guess.likelihood}%)" if console.have_rich() else
                       f"{tb.band.name} · {itu} · likely: {guess.name} ({guess.likelihood}%)")
        console.print_("Decoders: " + (", ".join(tb.decoders) or "—"))
        console.print_("Detectors: " + ", ".join(tb.detectors[:3]))
        console.print_("Try: " + (tb.commands[2] if len(tb.commands) > 2 else tb.commands[0]))
    else:
        console.print_(f"{itu} · likely: {guess.name} ({guess.likelihood}%) "
                       "(outside the curated band plan)")


def _menu_threats(cfg: Config, simulate: bool) -> None:
    items = [
        "Jamming / interference monitor",
        "Counter-UAS (drone) scan",
        "ADS-B spoofing check",
        "Rogue base station / IMSI-catcher",
        "Frequency-hopping detection",
        "Response playbook for a threat",
        "Back",
    ]
    while True:
        console.rule("Threat detection")
        for i, label in enumerate(items, 1):
            console.print_(f"  {i}. {label}")
        c = console.ask("Choose", default="7")
        if c in ("7", "b", "back", ""):
            return
        try:
            if c == "1":
                lo = float(console.ask("Start MHz", default="433"))
                hi = float(console.ask("Stop MHz", default="435"))
                rep = defense_mod.monitor_interference(cfg, lo, hi, iterations=12, simulate=simulate)
                defense_mod.print_interference(rep)
            elif c == "2":
                hits = intel_mod.drone_scan(cfg, simulate=simulate)
                if hits:
                    console.error(f"{len(hits)} drone-band detection(s):")
                    for h in hits:
                        console.print_(f"  • {h.band} {h.freq_mhz} MHz ({h.confidence})")
                else:
                    console.success("No drone activity.")
            elif c == "3":
                msgs = intel_mod.simulate_adsb_messages() if simulate else []
                f = intel_mod.detect_adsb_spoofing(msgs)
                (console.error if f else console.success)(f"{len(f)} ADS-B spoof indicator(s).")
                for x in f:
                    console.print_(f"  • {x.entity_id}: {x.kind} — {x.detail}")
            elif c == "4":
                obs = cellular_mod.simulate_observations() if simulate else []
                al = cellular_mod.detect_rogue_bts(obs)
                sc = cellular_mod.score(al)
                (console.error if al else console.success)(f"Rogue-BTS likelihood {sc}/100.")
                for a in al:
                    console.print_(f"  • [{a.severity}] {a.indicator}")
            elif c == "5":
                sl = intel_mod.simulate_hopping_slices(hopping=True) if simulate else []
                r = intel_mod.detect_frequency_hopping(sl)
                (console.error if r.hopping_suspected else console.success)(r.detail)
            elif c == "6":
                t = console.ask("Threat", default="jamming",
                                choices=response_mod.list_threats())
                pb = response_mod.get_playbook(t)
                if pb:
                    console.print_(pb.summary)
                    for step in pb.immediate:
                        console.print_(f"  • {step}")
            else:
                console.warn("Invalid choice.")
        except (RFHoundError, ValueError) as exc:
            console.error(str(exc))


def _menu_bands(cfg: Config) -> None:
    console.rule("Frequency knowledge base")
    console.print_("Categories: " + ", ".join(sorted({b.category for b in bandplan.BANDS})))
    cat = console.ask("Filter by category (blank = all)", default="")
    bands = bandplan.bands_by_category(cat) if cat else bandplan.BANDS
    rows = [[f"{b.low_hz/1e6:.3f}-{b.high_hz/1e6:.3f}", b.name, b.category, b.decoder or "-"]
            for b in bands]
    console.table("Bands (MHz)", ["Range", "Name", "Category", "Decoder"], rows)


def _menu_decoders(cfg: Config, simulate: bool) -> None:
    console.rule("Protocol decoders")
    rows = []
    for r in decode_mod.list_recipes():
        available, _ = decode_mod.check_recipe(r)
        rows.append([r.id, r.name, "ready" if available else "tool missing"])
    console.table("Recipes", ["ID", "Name", "Status"], rows)
    choice = console.ask("Recipe id to inspect (blank to cancel)", default="")
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
        console.warn("Simulate mode: not executing (no hardware).")
        return
    if console.confirm("Run it now?", default=False):
        try:
            decode_mod.run_decoder(recipe, cfg, seconds=20, on_line=console.print_)
        except RFHoundError as exc:
            console.error(str(exc))


def _menu_bookmarks(cfg: Config) -> None:
    console.rule("Bookmarks / memory channels")
    if cfg.bookmarks:
        rows = [[b.get("name", ""), f"{b.get('freq_mhz', 0):.4f}", b.get("note", "")]
                for b in sorted(cfg.bookmarks, key=lambda x: x.get("freq_mhz", 0))]
        console.table("Saved", ["Name", "Freq (MHz)", "Note"], rows)
    else:
        console.print_("(none yet)")
    if console.confirm("Add a bookmark?", default=False):
        name = console.ask("Name")
        freq = float(console.ask("Frequency MHz"))
        note = console.ask("Note", default="")
        cfg.bookmarks = [b for b in cfg.bookmarks if b.get("name") != name]
        cfg.bookmarks.append({"name": name, "freq_mhz": freq, "note": note})
        save_config(cfg)
        console.success(f"Saved '{name}'.")


def _menu_web(cfg: Config) -> None:
    console.rule("Web dashboard")
    console.print_("Launch the browser dashboard + REST API with:")
    console.print_("  rfhound web --open            # real hardware")
    console.print_("  rfhound --simulate web --open # no hardware")
    console.print_("(It runs until Ctrl-C, so start it in its own terminal.)")


def _menu_doctor(cfg: Config) -> None:
    from .cli import cmd_doctor
    import argparse
    cmd_doctor(argparse.Namespace(), cfg)


MENU = [
    ("Recon survey (what's around me?)", lambda c, s: _menu_recon(c, s)),
    ("Spectrum sweep (+ auto-identify)", lambda c, s: _menu_sweep(c, s)),
    ("Identify a frequency / protocol", lambda c, s: _menu_identify(c, s)),
    ("Threat detection", lambda c, s: _menu_threats(c, s)),
    ("Protocol decoders", lambda c, s: _menu_decoders(c, s)),
    ("Frequency knowledge base", lambda c, s: _menu_bands(c)),
    ("Bookmarks", lambda c, s: _menu_bookmarks(c)),
    ("Web dashboard", lambda c, s: _menu_web(c)),
    ("Environment check (doctor)", lambda c, s: _menu_doctor(c)),
    ("Quit", None),
]


def run_menu(cfg: Config) -> int:
    simulate = _hardware_or_simulate()
    quit_n = len(MENU)
    while True:
        console.rule("RFHound — main menu")
        for i, (label, _) in enumerate(MENU, 1):
            console.print_(f"  {i}. {label}")
        choice = console.ask("Choose", default="1").strip().lower()
        if choice in (str(quit_n), "q", "quit", "exit"):
            console.print_("73! (goodbye)")
            return 0
        try:
            n = int(choice)
            handler = MENU[n - 1][1]
        except (ValueError, IndexError):
            console.warn("Enter a valid number.")
            continue
        if handler is None:
            return 0
        try:
            handler(cfg, simulate)
        except (RFHoundError, ValueError) as exc:
            console.error(str(exc))
        except KeyboardInterrupt:
            console.print_("")
            continue
