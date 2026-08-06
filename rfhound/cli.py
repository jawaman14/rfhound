"""RFHound command-line interface.

Run ``rfhound`` with no arguments for the guided interactive menu, or use the
subcommands below for scripting. Everything is receive-first; transmit paths are
gated behind ``rfhound tx enable`` + an explicit ``--authorized`` flag.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, bandplan, console, device, proc, safety
from .config import Config, TxAllowRange, load_config, save_config, config_path
from .exceptions import RFHoundError
from .modules import capture as capture_mod
from .modules import decode as decode_mod
from .modules import defense as defense_mod
from .modules import intel as intel_mod
from .modules import gnuradio as gr_mod
from .modules import response as response_mod
from .modules import cellular as cellular_mod
from .modules import toolbox as toolbox_mod
from .modules import classify as classify_mod
from . import plugins
from .modules import recon as recon_mod
from .modules import replay as replay_mod
from .modules import report as report_mod
from .modules import sweep as sweep_mod


# HackRF One tunes 1 MHz – 6 GHz. Reject requests outside that up front with a
# clear message instead of letting them fail obscurely downstream.
HACKRF_MIN_MHZ = 1.0
HACKRF_MAX_MHZ = 6000.0


def _valid_freq(freq_mhz: float) -> str | None:
    """Return an error message if *freq_mhz* is outside the HackRF range, else None."""
    if freq_mhz != freq_mhz:  # NaN
        return "Frequency is not a number."
    if freq_mhz < HACKRF_MIN_MHZ or freq_mhz > HACKRF_MAX_MHZ:
        return (f"{freq_mhz:g} MHz is outside the HackRF range "
                f"({HACKRF_MIN_MHZ:g}–{HACKRF_MAX_MHZ:g} MHz).")
    return None


def _valid_range(start_mhz: float, stop_mhz: float) -> str | None:
    """Validate a [start, stop] sweep range; return an error message or None."""
    for f in (start_mhz, stop_mhz):
        err = _valid_freq(f)
        if err:
            return err
    if start_mhz >= stop_mhz:
        return (f"Start ({start_mhz:g} MHz) must be below stop ({stop_mhz:g} MHz).")
    return None


# --------------------------------------------------------------------------- #
# Subcommand handlers
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace, cfg: Config) -> int:
    if getattr(args, "json", False):
        import json
        from .web.server import status_dict
        data = status_dict(cfg)
        data["config_path"] = str(config_path())
        data["output_dir"] = cfg.output_dir
        console.raw(json.dumps(data, indent=2))
        return 0
    console.rule("Environment check")
    # External tools.
    rows = []
    for tool, installed, path in proc.tool_status():
        rows.append([
            tool.name,
            "✓" if installed else "✗",
            tool.purpose,
            path or tool.install_hint,
        ])
    console.table("External tools", ["Tool", "OK", "Purpose", "Path / install hint"], rows)

    # Device.
    console.rule("HackRF device")
    try:
        info = device.get_info()
        console.success(f"HackRF detected (serial {info.serial}, fw {info.firmware})")
    except RFHoundError as exc:
        console.warn(str(exc).splitlines()[0])
        console.print_("  Tip: use --simulate on sweep/recon to try RFHound without hardware.")

    # rich?
    console.rule("RFHound")
    console.print_(f"Version: {__version__}")
    console.print_(f"Rich UI: {'yes' if console.have_rich() else 'no (plain text fallback)'}")
    console.print_(f"Config:  {config_path()} ({'exists' if config_path().exists() else 'defaults'})")
    console.print_(f"Output:  {cfg.output_dir}")
    console.print_(f"Transmit: {'ENABLED' if cfg.tx_enabled else 'disabled'}")
    return 0


def cmd_device(args: argparse.Namespace, cfg: Config) -> int:
    if args.device_cmd == "operacake":
        proc.require_tool("hackrf_operacake")
        cmd = ["hackrf_operacake"]
        if args.a:
            cmd += ["-a", args.a]
        if args.b:
            cmd += ["-b", args.b]
        if not args.a and not args.b:
            cmd += ["-l"]  # list boards
        console.info(f"Opera Cake: {proc.format_command(cmd)}")
        r = proc.run(cmd, check=False, timeout=15)
        console.print_((r.stdout or "") + (r.stderr or ""))
        return r.returncode
    if args.device_cmd == "clock":
        proc.require_tool("hackrf_clock")
        r = proc.run(["hackrf_clock", "-r"], check=False, timeout=15)
        console.print_((r.stdout or "") + (r.stderr or ""))
        return 0
    # info
    try:
        info = device.get_info()
        console.print_(info.raw)
    except RFHoundError as exc:
        console.warn(str(exc).splitlines()[0])
        return 1
    return 0


def cmd_setup(args: argparse.Namespace, cfg: Config) -> int:
    """One-time, no-friction setup summary: config, tools, device, next steps."""
    console.banner(__version__)
    path = config_path()
    if not path.exists():
        save_config(cfg)
        console.success(f"Wrote a default config to {path}")
    else:
        console.info(f"Config already present at {path}")
    console.print_(f"Captures will be saved to: {cfg.output_dir}")

    statuses = proc.tool_status()
    installed = sum(1 for _, ok, _ in statuses if ok)
    console.print_(f"External SDR tools detected: {installed}/{len(statuses)} "
                   f"(run 'rfhound doctor' for the full list + install hints)")
    console.print_(f"HackRF: {'detected ✓' if device.is_present() else 'not detected — use --simulate'}")

    console.rule("Next steps")
    console.print_("  rfhound --simulate recon        # try the whole workflow, no hardware")
    console.print_("  rfhound at 433.92               # what's on a frequency + every tool for it")
    console.print_("  rfhound tune adsb               # what frequency do I need?")
    console.print_("  rfhound --simulate web --open   # open the dashboard")
    console.print_("  Full walkthrough: docs/TUTORIAL.md")
    return 0


def cmd_bands(args: argparse.Namespace, cfg: Config) -> int:
    bands = bandplan.BANDS
    if args.category:
        bands = [b for b in bands if b.category == args.category]
    if args.tag:
        bands = [b for b in bands if args.tag in b.tags]
    if args.search:
        q = args.search.lower()
        bands = [b for b in bands if q in b.name.lower() or q in b.description.lower()]
    if not bands:
        console.warn("No bands match that filter.")
        return 1
    rows = [
        [
            f"{b.low_hz/1e6:.3f}-{b.high_hz/1e6:.3f}",
            b.name,
            b.category,
            b.region,
            b.decoder or "-",
        ]
        for b in bands
    ]
    console.table(
        "Band plan (MHz)", ["Range", "Name", "Category", "Region", "Decoder"], rows
    )
    if args.verbose:
        for b in bands:
            console.rule(b.name)
            console.print_(b.description)
    return 0


def cmd_classify(args: argparse.Namespace, cfg: Config) -> int:
    freq, bw, mod = args.freq, args.bw, args.mod
    if args.file:
        from .modules import iqtools
        try:
            a = iqtools.analyze(Path(args.file))
        except (RuntimeError, OSError) as exc:
            console.error(str(exc))
            return 2
        bw = a.bandwidth_khz
        mod = a.modulation.modulation
        if freq is None and a.center_mhz is not None:
            freq = a.center_mhz
        console.info(f"IQ analysis of {Path(args.file).name}: "
                     f"center {a.center_mhz or '?'} MHz · {a.sample_rate/1e6:.1f} MSPS")
        console.print_(f"  measured bandwidth: {bw} kHz  ·  modulation: {mod} "
                       f"({a.modulation.confidence}% · {a.modulation.continuity}, "
                       f"SNR {a.modulation.snr_db:.0f} dB)")
    if freq is None:
        console.error("Provide a frequency (MHz) or --file with a capture that has metadata.")
        return 1
    err = _valid_freq(freq)
    if err:
        console.error(err)
        return 2
    matches = classify_mod.classify(freq, bandwidth_khz=bw, modulation=mod)
    if args.json:
        import json
        console.raw(json.dumps([{
            "name": m.name, "likelihood": m.likelihood, "decoder": m.decoder,
            "category": m.category, "reasons": m.reasons} for m in matches], indent=2))
        return 0
    ctx = f"{freq} MHz · {bandplan.itu_label(int(freq * 1e6))}"
    if bw:
        ctx += f", ~{bw:.0f} kHz"
    if mod:
        ctx += f", {mod}"
    rows = [[f"{m.likelihood}%", m.name, m.decoder or "—", m.category] for m in matches[:8]]
    console.table(f"Signal match — {ctx}", ["Likelihood", "Likely signal", "Decoder", "Category"], rows)
    top = matches[0]
    console.print_(f"\nBest guess: [bold]{top.name}[/bold] ({top.likelihood}%)"
                   if console.have_rich() else f"\nBest guess: {top.name} ({top.likelihood}%)")
    console.print_("  why: " + "; ".join(top.reasons))
    if top.decoder:
        console.print_(f"  try: rfhound decode run {top.decoder} --freq {freq}")
    console.print_(f"  more: rfhound at {freq}")
    return 0


def cmd_at(args: argparse.Namespace, cfg: Config) -> int:
    tb = toolbox_mod.at_frequency(args.freq)
    if not tb:
        console.warn(f"{args.freq} MHz is not in RFHound's band plan "
                     f"(HackRF covers 1-6000 MHz).")
        return 1
    if args.json:
        import json
        console.raw(json.dumps({
            "freq_mhz": args.freq, "band": tb.band.name, "category": tb.band.category,
            "range_mhz": [tb.band.low_hz / 1e6, tb.band.high_hz / 1e6],
            "decoders": tb.decoders, "detectors": tb.detectors,
            "gnuradio": tb.gnuradio, "commands": tb.commands}, indent=2))
        return 0
    b = tb.band
    itu = bandplan.itu_label(int(args.freq * 1e6))
    console.panel(
        f"{b.name}   ({b.low_hz/1e6:.3f}–{b.high_hz/1e6:.3f} MHz · {b.category} · {b.region})\n"
        f"ITU range: {itu}\n\n"
        f"{b.description}",
        title=f"You are at {args.freq} MHz", style="cyan")
    console.rule("Decoders for this band")
    if tb.decoders:
        rows = []
        for rid in tb.decoders:
            r = decode_mod.get_recipe(rid)
            ready, _ = decode_mod.check_recipe(r) if r else (False, None)
            rows.append([rid, r.name if r else "—", "✓" if ready else "✗ (install)"])
        console.table("", ["ID", "Name", "Tool ready"], rows)
    else:
        console.print_("  (no protocol decoder — try a GNU Radio preset below)")
    console.rule("Threat detectors that apply here")
    for d in tb.detectors:
        console.print_(f"  • rfhound defense {d}")
    console.rule("GNU Radio presets")
    console.print_("  " + ", ".join(tb.gnuradio))
    console.rule("Try these")
    for c in tb.commands:
        console.print_(f"  $ {c}")
    return 0


def cmd_tune(args: argparse.Namespace, cfg: Config) -> int:
    matches = toolbox_mod.tune_search(args.query)
    if not matches:
        console.warn(f"No band matches '{args.query}'. Try: adsb, tpms, pager, "
                     f"drone, cellular, ais, weather…")
        return 1
    if args.json:
        import json
        console.raw(json.dumps([m.__dict__ for m in matches], indent=2))
        return 0
    rows = [[f"{m.tune_mhz:.4f}", m.name, f"{m.low_mhz:.3f}–{m.high_mhz:.3f}",
             m.category, m.decoder or "—"] for m in matches]
    console.table(f"Tune to — matches for '{args.query}'",
                  ["Tune (MHz)", "Band", "Range", "Category", "Decoder"], rows)
    top = matches[0]
    console.print_(f"\n→ Best match: tune to [bold]{top.tune_mhz:.4f} MHz[/bold] for {top.name}"
                   if console.have_rich() else
                   f"\n-> Best match: tune to {top.tune_mhz:.4f} MHz for {top.name}")
    console.print_(f"  $ rfhound at {top.tune_mhz:.3f}      # see the full toolbox here")
    return 0


def cmd_sweep(args: argparse.Namespace, cfg: Config) -> int:
    err = _valid_range(args.start, args.stop)
    if err:
        console.error(err)
        return 2
    if getattr(args, "watch", False):
        return _sweep_watch(args, cfg)
    with console.status(f"Sweeping {args.start}-{args.stop} MHz…"):
        result = sweep_mod.sweep(
            cfg,
            args.start,
            args.stop,
            bin_khz=args.bin,
            snr_db=args.snr,
            sweeps=args.sweeps,
            simulate=args.simulate,
        )
    sweep_mod.render_spectrum(result)
    if result.peaks:
        if args.identify:
            rows = []
            for p in result.peaks[: args.top]:
                bw = classify_mod.estimate_bandwidth_khz(result, p.freq_hz)
                guess = classify_mod.classify(p.freq_mhz, bandwidth_khz=bw)[0]
                rows.append([
                    f"{p.freq_mhz:.4f}", f"{p.power_db}",
                    f"{bw:.0f} kHz" if bw else "—",
                    f"{guess.name} ({guess.likelihood}%)",
                    guess.decoder or "-",
                ])
            console.table(
                f"Top {min(args.top, len(result.peaks))} peaks — auto-identified",
                ["Freq (MHz)", "Power (dB)", "Bandwidth", "Likely signal", "Decoder"],
                rows,
            )
        else:
            rows = [
                [
                    f"{p.freq_mhz:.4f}",
                    f"{p.power_db}",
                    p.band.name if p.band else "unknown",
                    p.band.decoder if p.band and p.band.decoder else "-",
                ]
                for p in result.peaks[: args.top]
            ]
            console.table(
                f"Top {min(args.top, len(result.peaks))} peaks",
                ["Freq (MHz)", "Power (dB)", "Band", "Decoder"],
                rows,
            )
    else:
        console.warn("No peaks above the noise floor. Try lowering --snr or adding gain.")
    return 0


def _sweep_watch(args: argparse.Namespace, cfg: Config) -> int:
    """Continuously sweep and redraw a live terminal spectrogram (rich.Live)."""
    import time
    console.info(f"Live spectrum {args.start}-{args.stop} MHz — Ctrl-C to stop.")
    try:
        for _ in range(args.count if args.count else 10_000_000):
            result = sweep_mod.sweep(cfg, args.start, args.stop, bin_khz=args.bin,
                                     snr_db=args.snr, simulate=args.simulate)
            sweep_mod.render_spectrum(result)
            if result.peaks:
                top = result.peaks[0]
                console.print_(f"  peak {top.freq_mhz:.3f} MHz @ {top.power_db} dB "
                               f"({top.band.name if top.band else 'unknown'})")
            time.sleep(max(0.2, args.interval))
    except KeyboardInterrupt:
        console.warn("stopped.")
    return 0


def cmd_recon(args: argparse.Namespace, cfg: Config) -> int:
    targets = None
    if args.category:
        targets = bandplan.bands_by_category(args.category)
        if not targets:
            console.error(f"No bands in category '{args.category}'.")
            return 1
    with console.status("Surveying bands…"):
        report = recon_mod.run_recon(
            cfg, targets=targets, snr_db=args.snr, bin_khz=args.bin,
            simulate=args.simulate, progress=False,
        )
    recon_mod.summarize(report)

    # Suggest next steps.
    suggestions = [
        f.band for f in report.active_findings if f.band.decoder
    ]
    if suggestions:
        console.rule("Suggested next steps")
        for b in suggestions[:8]:
            console.print_(
                f"  rfhound decode run {b.decoder} --freq {b.tune_hz/1e6:.3f}   "
                f"# {b.name}"
            )

    if args.report:
        out = Path(args.report)
        fmt = "html" if out.suffix.lower() in (".html", ".htm") else "md"
        report_mod.write_report(report, out, fmt=fmt)
        console.success(f"Report written to {out}")
    return 0


def cmd_capture(args: argparse.Namespace, cfg: Config) -> int:
    err = _valid_freq(args.freq)
    if err:
        console.error(err)
        return 2
    if args.seconds <= 0:
        console.error("Capture length (seconds) must be positive.")
        return 2
    cap = capture_mod.capture_iq(
        cfg,
        args.freq,
        args.seconds,
        name=args.name,
        sample_rate=args.rate,
        note=args.note or "",
        simulate=args.simulate,
    )
    console.success(f"Captured {cap.seconds}s @ {cap.freq_hz/1e6:.3f} MHz")
    console.print_(f"  data: {cap.data_path}")
    console.print_(f"  meta: {cap.meta_path}")
    if getattr(args, "classify", False):
        from .modules import recordings
        try:
            r = recordings.classify_recording(cap.data_path, cfg)
            console.success(f"Classified: {r.guess} ({r.guess_confidence}%) · "
                            f"{r.modulation} · ~{r.bandwidth_khz} kHz"
                            + (f" · decoder {r.decoder}" if r.decoder else ""))
        except (RuntimeError, OSError) as exc:
            console.warn(f"Classify skipped: {exc}")
    console.print_("  Open in URH / inspectrum / GNU Radio, or 'rfhound recordings list'.")
    return 0


def cmd_recordings(args: argparse.Namespace, cfg: Config) -> int:
    from .modules import recordings
    if args.rec_cmd == "show":
        rec = recordings.find_recording(cfg.output_dir, args.name)
        if not rec:
            console.error(f"No recording named '{args.name}' in {cfg.output_dir}")
            return 1
        import json
        console.raw(json.dumps(recordings._read_meta(rec.meta_path), indent=2))
        return 0
    if args.rec_cmd == "classify":
        rec = recordings.find_recording(cfg.output_dir, args.name)
        if not rec:
            console.error(f"No recording named '{args.name}'.")
            return 1
        try:
            r = recordings.classify_recording(rec.data_path, cfg)
        except (RuntimeError, OSError) as exc:
            console.error(str(exc))
            return 2
        console.success(f"{rec.name}: {r.guess} ({r.guess_confidence}%) · {r.modulation} · "
                        f"~{r.bandwidth_khz} kHz · decoder {r.decoder or '—'}")
        return 0
    # list
    recs = recordings.list_recordings(cfg.output_dir)
    if not recs:
        console.warn(f"No recordings in {cfg.output_dir}. Make one: rfhound capture <MHz> <sec>")
        return 0
    rows = [[r.name, f"{r.freq_mhz:.3f}" if r.freq_mhz else "—",
             f"{r.seconds}s" if r.seconds else "—",
             f"{r.guess} ({r.guess_confidence}%)" if r.guess else "unclassified",
             r.modulation or "—", r.decoder or "—"] for r in recs]
    console.table(f"Recordings in {cfg.output_dir}",
                  ["Name", "Freq MHz", "Length", "Likely signal", "Mod", "Decoder"], rows)
    console.print_("\nClassify one:  rfhound recordings classify <name>")
    return 0


def cmd_decode(args: argparse.Namespace, cfg: Config) -> int:
    if args.decode_cmd == "list":
        rows = []
        for r in decode_mod.list_recipes():
            available, path = decode_mod.check_recipe(r)
            rows.append([
                r.id,
                r.name,
                r.category,
                f"{r.default_freq_hz/1e6:.3f}",
                "✓" if available else "✗ (missing)",
            ])
        console.table(
            "Decoder recipes", ["ID", "Name", "Category", "Def. MHz", "Tool ready"], rows
        )
        console.print_("\nRun one with:  rfhound decode run <id> [--freq MHz] [--seconds N]")
        return 0

    # run
    recipe = decode_mod.get_recipe(args.recipe)
    if not recipe:
        console.error(f"Unknown recipe '{args.recipe}'. Try: rfhound decode list")
        return 1
    freq_hz = int(args.freq * 1e6) if args.freq else recipe.default_freq_hz
    console.info(f"{recipe.name} @ {freq_hz/1e6:.3f} MHz for {args.seconds}s")
    if recipe.note:
        console.print_(f"  note: {recipe.note}")
    if args.dry_run:
        cmd = decode_mod.run_decoder(recipe, cfg, freq_hz=freq_hz, seconds=args.seconds, dry_run=True)
        console.print_(f"  would run: {cmd[0]}")
        return 0
    store = None
    if getattr(args, "track", False):
        from .modules import sightings
        store = sightings.SightingsStore()

        def on_line(line):
            console.print_(line)
            sightings.ingest_json_line(store, recipe.id, line,
                                       freq_mhz=freq_hz / 1e6, save=False)
    else:
        on_line = console.print_

    try:
        lines = decode_mod.run_decoder(
            recipe, cfg, freq_hz=freq_hz, seconds=args.seconds, on_line=on_line,
        )
    except RFHoundError as exc:
        console.error(str(exc))
        return 1
    if store is not None:
        store.save()
        console.success(f"Tracked {len(store.data)} unique ID(s) — see 'rfhound track list'.")
    console.success(f"Decoder finished ({len(lines)} lines).")
    return 0


def cmd_track(args: argparse.Namespace, cfg: Config) -> int:
    from .modules import sightings
    import time
    store = sightings.SightingsStore()
    if args.track_cmd == "add":
        s = store.record(args.kind, args.id, freq_mhz=args.freq, note=args.note or "")
        console.success(f"Recorded {s.kind}:{s.id} (count {s.count})")
        return 0
    if args.track_cmd == "clear":
        n = store.clear(args.kind)
        console.success(f"Cleared {n} sighting(s).")
        return 0
    if args.track_cmd == "show":
        matches = [s for s in store.list() if s.id == args.id]
        if not matches:
            console.warn(f"No sightings for id '{args.id}'.")
            return 1
        for s in matches:
            console.print_(f"{s.kind}:{s.id}  count={s.count}  "
                           f"freq={s.freq_mhz or '?'} MHz  note={s.note}")
            console.print_(f"  first: {time.ctime(s.first_seen)}  last: {time.ctime(s.last_seen)}")
            if s.extra:
                console.print_(f"  extra: {s.extra}")
        return 0
    # list
    items = store.list(args.kind)
    if not items:
        console.warn("No sightings yet. Decode with --track, or 'rfhound track add <kind> <id>'.")
        return 0
    rows = [[s.kind, s.id, str(s.count), f"{s.freq_mhz:.3f}" if s.freq_mhz else "—",
             time.strftime("%m-%d %H:%M", time.localtime(s.last_seen)),
             (s.extra.get("model") or s.note or "")] for s in items[:args.top]]
    console.table(f"Sightings ({len(items)} unique IDs)",
                  ["Kind", "ID", "Count", "Freq MHz", "Last seen", "Model/note"], rows)
    return 0


def cmd_replay(args: argparse.Namespace, cfg: Config) -> int:
    data_path = Path(args.file)
    # Surface any stored classification so the operator knows what's being replayed.
    meta_path = data_path.with_suffix(".sigmf-meta")
    if meta_path.exists():
        import json
        try:
            g = json.loads(meta_path.read_text()).get("global", {})
            if g.get("rfhound:guess"):
                console.info(f"This recording looks like: {g['rfhound:guess']} "
                             f"({g.get('rfhound:guess_confidence', '?')}%) · "
                             f"{g.get('rfhound:modulation', '?')} · decoder "
                             f"{g.get('rfhound:suggested_decoder') or '—'}")
        except (json.JSONDecodeError, OSError):
            pass
    try:
        plan = replay_mod.replay(
            cfg,
            data_path,
            authorized=args.authorized,
            freq_hz=int(args.freq * 1e6) if args.freq else None,
            tx_gain=args.gain,
            dry_run=args.dry_run,
        )
    except RFHoundError as exc:
        console.error(str(exc))
        return 2
    if args.dry_run:
        console.rule("Transmit preflight (dry-run — nothing was keyed)")
        itu = bandplan.itu_label(plan.freq_hz)
        console.print_(f"  frequency : {plan.freq_hz/1e6:.4f} MHz  ({itu})")
        dur = (f"{plan.duration_s:.2f} s" if plan.duration_s is not None
               else "unknown (no sample count in metadata)")
        console.print_(f"  duration  : {dur}  ·  cap {cfg.tx_max_seconds}s")
        console.print_(f"  tx gain   : {plan.tx_gain} dB  ·  sample rate {plan.sample_rate/1e6:.3f} MSPS")
        allowed = "inside a declared allow-range" if cfg.is_tx_range_allowed(plan.freq_hz) \
            else "NOT in any allow-range"
        console.print_(f"  allow-list: {allowed}")
        if plan.protected:
            console.error(f"  PROTECTED : safety-of-life band ({plan.protected}) — real transmit is refused")
        console.print_(f"  would run : {proc.format_command(plan.command)}")
    else:
        console.success(f"Replayed {data_path.name} @ {plan.freq_hz/1e6:.3f} MHz")
    return 0


def cmd_tx(args: argparse.Namespace, cfg: Config) -> int:
    if args.tx_cmd == "status":
        console.print_(f"Transmit: {'ENABLED' if cfg.tx_enabled else 'disabled'}")
        console.print_(f"Consent recorded: {cfg.tx_consent_at or '(none)'}")
        console.print_(f"Jurisdiction: {cfg.jurisdiction or '(unset)'}")
        console.print_(f"Max replay duration: {cfg.tx_max_seconds}s (tx_max_seconds)")
        if cfg.tx_allow_ranges:
            for r in cfg.tx_allow_ranges:
                console.print_(f"  allow: {r.low_hz/1e6:.3f}-{r.high_hz/1e6:.3f} MHz  {r.note}")
        else:
            console.print_("  allow: (no ranges declared)")
        console.print_(f"Safety-of-life bands are always refused ({len(safety.PROTECTED_BANDS)} "
                       "ranges: GNSS, aviation, marine distress, emergency beacons).")
        recent = safety.read_tx_audit(3)
        if recent:
            console.print_("Recent transmit audit:")
            for e in recent:
                console.print_(f"  {e['t']}  {e.get('freq_mhz','?')} MHz  {e['outcome']}"
                               + (f" — {e['reason']}" if e.get('reason') else ""))
        return 0

    if args.tx_cmd == "audit":
        import json
        if args.clear:
            n = safety.clear_tx_audit()
            console.success(f"Cleared {n} audit record(s).")
            return 0
        entries = safety.read_tx_audit(args.top)
        if args.json:
            console.raw(json.dumps(entries, indent=2))
            return 0
        if not entries:
            console.warn("No transmit events recorded yet.")
            return 0
        rows = [[e["t"], f"{e.get('freq_mhz','?')}", e["outcome"],
                 "yes" if e.get("dry_run") else "no",
                 f"{e['duration_s']}s" if e.get("duration_s") is not None else "—",
                 e.get("reason", "")] for e in entries]
        console.table(f"Transmit audit log ({len(entries)})",
                      ["Time (UTC)", "MHz", "Outcome", "Dry-run", "Duration", "Reason"], rows)
        return 0

    if args.tx_cmd == "disable":
        safety.disable_tx(cfg)
        console.success("Transmit disabled.")
        return 0

    # enable
    console.panel(safety.CONSENT_TEXT, title="Transmit legal terms", style="yellow")
    if not args.yes and not console.confirm("Do you accept these terms?", default=False):
        console.warn("Transmit not enabled.")
        return 1
    ranges = []
    for spec in args.allow or []:
        try:
            lo, hi = spec.split("-")
            ranges.append(TxAllowRange(int(float(lo) * 1e6), int(float(hi) * 1e6), "cli"))
        except ValueError:
            console.error(f"Bad --allow range '{spec}'. Use MHZ-MHZ, e.g. 433.0-434.8")
            return 1
    if not ranges:
        console.error("Provide at least one --allow MHZ-MHZ range you are authorized to use.")
        return 1
    try:
        safety.enable_tx(cfg, ranges, jurisdiction=args.jurisdiction or "")
    except RFHoundError as exc:
        console.error(str(exc))
        return 1
    console.success("Transmit enabled with the declared allow-list.")
    console.print_("Replay still requires an explicit --authorized flag per invocation.")
    return 0


def _load_json_list(path: str | None) -> list:
    if not path:
        raise RFHoundError("Provide --file <messages.json> (a JSON array) or use --simulate.")
    import json
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise RFHoundError(f"{path} must contain a JSON array of message objects.")
    return data


def cmd_mods(args: argparse.Namespace, cfg: Config) -> int:
    if args.mods_cmd == "sample":
        path = plugins.write_sample_mod()
        console.success(f"Wrote a sample mod to {path}")
        console.print_("Edit it, then run 'rfhound mods list' to load it.")
        return 0
    # list (also the default): load and report
    directory = Path(args.dir) if args.dir else plugins.mods_dir()
    loaded = plugins.load_mods(directory)
    console.print_(f"Mods directory: {directory}")
    if not loaded:
        console.warn("No mods found. Create one with 'rfhound mods sample'.")
        return 0
    rows = []
    for m in loaded:
        status = "ok" if not m.error else f"ERROR: {m.error}"
        rows.append([m.name, m.version,
                     f"{len(m.bands)}b/{len(m.recipes)}r/{len(m.detectors)}d", status])
    console.table("Loaded mods", ["Name", "Version", "Adds", "Status"], rows)
    return 0


def cmd_defense(args: argparse.Namespace, cfg: Config) -> int:
    if args.defense_cmd == "monitor":
        report = defense_mod.monitor_interference(
            cfg, args.start, args.stop,
            iterations=args.samples, interval_s=args.interval,
            threshold_db=args.threshold, simulate=args.simulate,
        )
        defense_mod.print_interference(report)
        return 1 if report.jammed else 0

    if args.defense_cmd == "rolling-assess":
        if args.simulate:
            payloads = defense_mod.simulate_payloads(args.kind)
        elif args.file:
            payloads = Path(args.file).read_text().splitlines()
        else:
            console.error("Provide --file <payloads.txt> (one code per line) or --simulate.")
            return 1
        assessment = defense_mod.assess_rolling_code(payloads)
        defense_mod.print_rolling(assessment)
        return 0

    if args.defense_cmd == "replay-check":
        # Observations file: 'timestamp payload' per line, or --simulate.
        if args.simulate:
            t0 = 1000.0
            obs = [  # same fixed code re-sent 3x in <1s => replay signature
                defense_mod.Observation(t0, "10101100"),
                defense_mod.Observation(t0 + 0.4, "10101100"),
                defense_mod.Observation(t0 + 0.7, "10101100"),
            ]
        elif args.file:
            obs = []
            for line in Path(args.file).read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    obs.append(defense_mod.Observation(float(parts[0]), parts[1]))
        else:
            console.error("Provide --file <observations.txt> ('ts payload' per line) or --simulate.")
            return 1
        findings = defense_mod.detect_replays(obs, rolling_expected=not args.fixed)
        if not findings:
            console.success("No replay signatures detected.")
            return 0
        console.error(f"Possible replay attack(s) detected: {len(findings)}")
        for f in findings:
            console.print_(f"  • payload {f.payload}: seen {f.count}x, "
                           f"min gap {f.min_gap_s}s — {f.reason}")
        return 1

    if args.defense_cmd == "baseline":
        if args.baseline_cmd == "save":
            path = intel_mod.save_baseline(
                cfg, args.start, args.stop, Path(args.out), simulate=args.simulate
            )
            console.success(f"Baseline saved to {path}")
            return 0
        # diff
        findings = intel_mod.diff_baseline(
            cfg, Path(args.file), new_threshold_db=args.threshold, simulate=args.simulate
        )
        if not findings:
            console.success("No new or elevated emitters vs baseline — area clean.")
            return 0
        console.error(f"TSCM: {len(findings)} new/elevated emitter(s) vs baseline:")
        rows = [
            [f"{f.freq_mhz:.4f}", f"{f.power_db}", f.kind,
             f"+{f.delta_db}" if f.baseline_db is not None else "new",
             f.band or "unknown"]
            for f in findings
        ]
        console.table("Rogue emitters", ["Freq (MHz)", "Power dB", "Kind", "Δ dB", "Band"], rows)
        return 1

    if args.defense_cmd == "spoof-check":
        if args.protocol == "adsb":
            msgs = intel_mod.simulate_adsb_messages() if args.simulate else _load_json_list(args.file)
            findings = intel_mod.detect_adsb_spoofing(msgs)
        else:
            msgs = intel_mod.simulate_ais_messages() if args.simulate else _load_json_list(args.file)
            findings = intel_mod.detect_ais_spoofing(msgs)
        if not findings:
            console.success(f"No {args.protocol.upper()} spoofing indicators found.")
            return 0
        console.error(f"{args.protocol.upper()} spoofing indicators: {len(findings)}")
        for f in findings:
            console.print_(f"  • [{f.severity}] {f.entity_id} — {f.kind}: {f.detail}")
        return 1

    if args.defense_cmd == "drone-scan":
        hits = intel_mod.drone_scan(cfg, simulate=args.simulate)
        if not hits:
            console.success("No drone-band activity detected.")
            return 0
        console.error(f"Counter-UAS: activity in {len(hits)} drone-band bin(s):")
        rows = [[h.band, f"{h.freq_mhz:.3f}", f"{h.power_db}", h.confidence] for h in hits]
        console.table("Drone-band detections", ["Band", "Freq (MHz)", "Power dB", "Confidence"], rows)
        return 1

    if args.defense_cmd == "imsi-catcher":
        if args.simulate:
            obs = cellular_mod.simulate_observations()
        elif args.file:
            import json
            raw = json.loads(Path(args.file).read_text())
            obs = [cellular_mod.CellObservation(**o) for o in raw]
        else:
            console.error("Provide --file <cells.json> or --simulate.")
            return 1
        alerts = cellular_mod.detect_rogue_bts(obs)
        sc = cellular_mod.score(alerts)
        console.rule("Rogue base station / IMSI-catcher detection")
        if not alerts:
            console.success(f"No rogue-BTS indicators (score {sc}/100).")
            return 0
        console.error(f"Rogue-BTS indicators: {len(alerts)}  ·  likelihood {sc}/100")
        for a in alerts:
            console.print_(f"  • [{a.severity}] CID={a.cid} {a.indicator}: {a.detail}")
        return 1

    if args.defense_cmd == "hop-detect":
        if args.simulate:
            slices = intel_mod.simulate_hopping_slices(hopping=True)
        else:
            console.error("Live hop-detect needs sweep peak data; use --simulate for a demo.")
            return 1
        report = intel_mod.detect_frequency_hopping(slices)
        console.rule("Frequency-hopping detection")
        console.print_(report.detail)
        if report.hopping_suspected:
            console.error("Frequency-hopping emitter SUSPECTED (frequency-agile transmitter).")
            return 1
        console.success("No hopping pattern detected.")
        return 0

    if args.defense_cmd == "respond":
        pb = response_mod.get_playbook(args.threat)
        if not pb:
            console.error(f"Unknown threat '{args.threat}'. "
                          f"Options: {', '.join(response_mod.list_threats())}")
            return 1
        console.rule(f"Counter-threat playbook: {pb.threat}")
        console.print_(pb.summary)
        for title, items in [("Immediate actions", pb.immediate),
                             ("Preserve evidence", pb.evidence),
                             ("Mitigations / hardening", pb.mitigations),
                             ("Escalation", pb.escalation)]:
            console.rule(title)
            for it in items:
                console.print_(f"  • {it}")
        return 0

    if args.defense_cmd == "resilience":
        payloads = None
        if args.payloads:
            payloads = Path(args.payloads).read_text().splitlines()
        result = defense_mod.run_resilience_test(
            cfg,
            device=args.device or "device-under-test",
            payloads=payloads,
            replayed=args.replayed,
            device_actuated=(None if args.actuated is None else args.actuated),
            simulate=args.simulate,
        )
        defense_mod.print_resilience(result)
        return 0

    console.error("Unknown defense subcommand.")
    return 1


def cmd_web(args: argparse.Namespace, cfg: Config) -> int:
    from .web import server as web_server
    force_sim = args.simulate or cfg.simulate_mode or not device.is_present()
    if force_sim and not args.simulate:
        console.warn("No HackRF detected — dashboard will run in SIMULATE mode.")
    token = args.token
    if token == "auto" or (token is None and args.host not in web_server._LOOPBACK):
        import secrets
        token = secrets.token_urlsafe(18)
        console.info(f"Generated dashboard token: {token}")
    url = f"http://{args.host}:{args.port}"
    if token:
        url += f"/?token={token}"
    if args.open:
        import webbrowser
        webbrowser.open(url)
    web_server.serve(cfg, host=args.host, port=args.port, force_simulate=force_sim, token=token)
    return 0


def cmd_gnuradio(args: argparse.Namespace, cfg: Config) -> int:
    if args.gr_cmd == "status":
        st = gr_mod.gnuradio_status()
        (console.success if st.installed else console.warn)(st.detail)
        return 0
    if args.gr_cmd == "list":
        rows = [[p.id, p.name, p.category, p.description] for p in gr_mod.list_presets()]
        console.table("GNU Radio flowgraph presets (receive/analysis only)",
                      ["ID", "Name", "Category", "Description"], rows)
        console.print_("\nGenerate one:  rfhound gnuradio gen <id> --freq MHz [--out file.py]")
        return 0
    # gen
    try:
        dest = gr_mod.generate_flowgraph(
            args.preset, cfg, freq_mhz=args.freq, sample_rate=args.rate,
            out_file=args.data_out,
            dest_path=Path(args.out) if args.out else None,
        )
    except ValueError as exc:
        console.error(str(exc))
        return 1
    console.success(f"Wrote GNU Radio flowgraph to {dest}")
    if not args.quiet:
        console.syntax(dest.read_text(), "python", title=f"{dest.name} (preview)")
    st = gr_mod.gnuradio_status()
    if not st.installed:
        console.warn("GNU Radio isn't installed here; the script will run where it is "
                     "(apt install gnuradio gr-osmosdr).")
    else:
        console.print_(f"Run it:  python3 {dest}")
    return 0


def cmd_dev(args: argparse.Namespace, cfg: Config) -> int:
    console.set_debug(True)
    console.rule("RFHound developer diagnostics")
    console.print_(f"version: {__version__}")
    console.print_(f"rich: {console.have_rich()}  ·  config: {config_path()}")
    console.print_(f"bands: {len(bandplan.BANDS)}  ·  decoder recipes: "
                   f"{len(decode_mod.list_recipes())}  ·  "
                   f"threats: {len(response_mod.list_threats())}")
    from .llm import actions as llm_actions
    console.print_(f"llm actions (safe, RX-only): {len(llm_actions.ACTIONS)}")
    console.print_(f"gnuradio presets: {len(gr_mod.list_presets())}")
    console.rule("External tools")
    for tool, ok, path in proc.tool_status():
        console.print_(f"  [{'✓' if ok else '✗'}] {tool.name}: {path or 'not found'}")
    console.debug("dev mode active — full tracebacks enabled")
    return 0


def cmd_ai(args: argparse.Namespace, cfg: Config) -> int:
    from .ai_menu import run_ai_menu
    return run_ai_menu(cfg, provider=args.provider)


def cmd_ask(args: argparse.Namespace, cfg: Config) -> int:
    from .llm import Copilot
    copilot = Copilot(cfg, provider=args.provider)
    console.print_(f"[copilot:{copilot.provider}]")
    try:
        result = copilot.ask(args.query)
    except Exception as exc:
        console.error(f"Copilot error: {exc}")
        if not args.provider or args.provider == "offline":
            raise
        console.print_("Tip: check ANTHROPIC_API_KEY / --provider / llm_base_url, "
                       "or use --provider offline.")
        return 2
    for a in result.actions_run:
        console.info(f"ran {a['action']}({a['params']})")
    console.print_(result.text)
    return 0


def cmd_hub(args: argparse.Namespace, cfg: Config) -> int:
    from .net import serve_hub
    serve_hub(host=args.host, port=args.port, token=args.token or cfg.hub_token)
    return 0


def cmd_node(args: argparse.Namespace, cfg: Config) -> int:
    from .net import node_register, node_report
    hub = args.hub or cfg.hub_url
    node_id = args.id or cfg.node_id or "node-1"
    token = args.token or cfg.hub_token
    if not hub:
        console.error("No hub URL. Pass --hub http://host:port (or set hub_url in config).")
        return 1
    try:
        node_register(hub, node_id, name=args.name or node_id, location=args.location or "",
                      token=token)
        console.success(f"Registered node '{node_id}' with hub {hub}")
        sim = args.simulate or cfg.simulate_mode or not device.is_present()
        if args.scan == "recon":
            rep = recon_mod.run_recon(cfg, simulate=sim, progress=False)
            data = {"active": len(rep.active_findings), "total": len(rep.findings)}
        elif args.scan == "drone":
            hits = intel_mod.drone_scan(cfg, simulate=sim)
            data = {"drone_hits": len(hits)}
        elif args.scan == "imsi":
            obs = cellular_mod.simulate_observations() if sim else []
            alerts = cellular_mod.detect_rogue_bts(obs)
            data = {"rogue_bts_score": cellular_mod.score(alerts), "alerts": len(alerts)}
        else:
            data = {"status": "online"}
        if args.scan or True:
            node_report(hub, node_id, args.scan or "status", data, token=token)
            console.success(f"Pushed report ({args.scan or 'status'}): {data}")
    except Exception as exc:
        console.error(f"Node link failed: {exc}")
        return 2
    return 0


def cmd_automate(args: argparse.Namespace, cfg: Config) -> int:
    from .modules import automation as auto_mod
    sim = args.simulate or cfg.simulate_mode or not device.is_present()
    sub = args.automate_cmd
    if sub in (None, "menu"):
        from .automation_menu import run_automation_menu
        return run_automation_menu(cfg)
    if sub == "list":
        if not cfg.automations:
            console.warn("No automations. Add one: rfhound automate add <name> <task>")
            return 0
        rows = []
        for a in cfg.automations:
            n = auto_mod._norm(a)
            rows.append([n["name"], n["task"], f"{n['interval_s']}s", n["alert_on"],
                         "on" if n["enabled"] else "off",
                         " ".join(f"{k}={v}" for k, v in n["params"].items()) or "—"])
        console.table("Automations", ["Name", "Task", "Every", "Alert", "On", "Params"], rows)
        return 0
    if sub == "add":
        params = {}
        if args.start is not None:
            params["start"] = args.start
        if args.stop is not None:
            params["stop"] = args.stop
        auto_mod.add_automation(cfg, args.name, args.task, interval_s=args.interval,
                                params=params, alert_on=args.alert_on, webhook=args.webhook or "")
        console.success(f"Added automation '{args.name}' ({args.task}, every {args.interval}s).")
        return 0
    if sub == "remove":
        ok = auto_mod.remove_automation(cfg, args.name)
        console.success(f"Removed '{args.name}'." if ok else f"No automation '{args.name}'.")
        return 0
    if sub in ("enable", "disable"):
        ok = auto_mod.set_enabled(cfg, args.name, sub == "enable")
        console.success(f"'{args.name}' {sub}d." if ok else f"No automation '{args.name}'.")
        return 0
    if sub == "once":
        autos = [a for a in cfg.automations if not args.name or a.get("name") == args.name]
        if not autos:
            console.warn("No matching automation.")
            return 1
        for a in autos:
            res = auto_mod.run_task(cfg, a, simulate=sim)
            alerting = auto_mod.should_alert(a, res)
            auto_mod.fire(cfg, a, res, alerting=alerting)
            (console.error if alerting else console.success)(
                f"{auto_mod._norm(a)['name']} · {'ALERT' if alerting else 'ok'}: {res.summary}")
        return 0
    if sub == "run":
        auto_mod.run_scheduler(cfg, simulate=sim)
        return 0
    console.error("Unknown automate subcommand.")
    return 1


def cmd_sigint(args: argparse.Namespace, cfg: Config) -> int:
    from .modules import sigint
    sim = args.simulate or cfg.simulate_mode or not device.is_present()
    sub = args.sigint_cmd

    if sub == "pulse":
        if not args.file:
            console.error("Provide an IQ capture: rfhound sigint pulse --file capture.sigmf-data")
            return 1
        try:
            prof = sigint.analyze_pulses_file(Path(args.file))
        except (RuntimeError, OSError) as exc:
            console.error(str(exc))
            return 2
        console.rule("ELINT pulse analysis")
        console.print_(f"Classification: {prof.classification}")
        console.print_(f"  {prof.detail}")
        return 0

    if sub == "jamming":
        result = sweep_mod.sweep(cfg, args.start, args.stop, simulate=sim)
        spectrum = [b.power_db for b in result.bins]
        prof = sigint.characterize_interference(spectrum, result.noise_floor_db)
        console.rule("Interference / jamming characterisation")
        if prof.kind == "none":
            console.success(f"No jamming signature (occupancy {prof.occupancy:.0%}).")
            return 0
        console.error(f"Jamming type: {prof.kind.upper()} ({prof.confidence}%)")
        console.print_(f"  {prof.detail}")
        return 1

    if sub == "emitters":
        cat = sigint.EmitterCatalog()
        if args.scan:
            result = sweep_mod.sweep(cfg, args.start, args.stop, simulate=sim)
            from .modules import classify as classify_mod
            for p in result.peaks:
                bw = classify_mod.estimate_bandwidth_khz(result, p.freq_hz)
                g = classify_mod.classify(p.freq_mhz, bandwidth_khz=bw)[0]
                cat.ingest(p.freq_mhz, power_db=p.power_db, bandwidth_khz=bw,
                           guess=g.name, save=False)
            cat.save()
            console.success(f"Ingested {len(result.peaks)} peak(s) into the catalogue.")
        if args.clear:
            n = cat.clear()
            console.success(f"Cleared {n} emitter(s).")
            return 0
        emitters = cat.list()
        if not emitters:
            console.warn("Empty catalogue. Populate it: rfhound sigint emitters --scan <lo> <hi>")
            return 0
        rows = [[f"{e.freq_mhz:.4f}", e.itu, f"{e.max_power_db}" if e.max_power_db else "—",
                 f"{e.bandwidth_khz:.0f}" if e.bandwidth_khz else "—",
                 e.guess or "—", str(e.count)] for e in emitters]
        console.table(f"Emitter catalogue / EOB ({len(emitters)})",
                      ["Freq MHz", "ITU", "Max dB", "BW kHz", "Likely", "Seen"], rows)
        return 0

    if sub == "locate":
        import json
        if args.tdoa:
            import time
            from .modules import tdoa as tdoa_mod
            geom = [(51.520, -0.120), (51.505, -0.100), (51.500, -0.130), (51.515, -0.140)]
            if args.hub:
                from .net import node as node_mod
                if args.simulate:
                    # Seed the hub: simulate aligned captures and push one per node.
                    trig = args.trigger or f"sim-{int(time.time())}"
                    caps = tdoa_mod.simulate_captures((51.510, -0.118), geom,
                                                      sample_rate=20_000_000, n_samples=8192)
                    for c in caps:
                        b64, n = tdoa_mod.encode_iq_b64(c["iq"])
                        node_mod.push_tdoa(args.hub, c["node"], c["lat"], c["lon"], trig,
                                           iq_b64=b64, n=n, sample_rate=20_000_000,
                                           token=args.token)
                    console.info(f"Pushed {len(caps)} TDOA snippets to {args.hub} (trigger {trig}).")
                try:
                    state = node_mod.hub_state(args.hub, token=args.token)
                except Exception as exc:
                    console.error(f"Could not reach hub {args.hub}: {exc}")
                    return 2
                nodes = tdoa_mod.nodes_from_hub_reports(state.get("reports", []),
                                                        trigger=args.trigger)
                if not nodes:
                    console.warn("No TDOA contributions on the hub for that trigger yet.")
                    return 1
            elif args.simulate:
                nodes = tdoa_mod.simulate_scenario((51.510, -0.118), geom, sigma_tdoa_s=2e-8)
            elif args.file:
                raw = json.loads(Path(args.file).read_text())
                nodes = [tdoa_mod.Node(**n) for n in raw]
            else:
                console.error("Provide --hub URL, --file nodes.json, or --simulate.")
                return 1
            try:
                fix = tdoa_mod.geolocate_tdoa(nodes)
            except RuntimeError as exc:
                console.error(str(exc))
                return 2
            console.rule("TDOA multilateration")
            if fix.lat is None:
                console.warn(fix.detail)
                return 1
            console.success(f"Estimated position: {fix.lat}, {fix.lon}  ({fix.method})")
            extra = []
            if fix.confidence_m is not None:
                extra.append(f"±{fix.confidence_m} m")
            if fix.gdop is not None:
                extra.append(f"GDOP {fix.gdop}")
            if fix.residual_m is not None:
                extra.append(f"residual {fix.residual_m} m")
            console.print_(f"  {fix.n_nodes} nodes · " + " · ".join(extra) + f" · {fix.detail}")
            return 0
        if args.simulate:
            reports = sigint.simulate_reports()
        elif args.file:
            reports = json.loads(Path(args.file).read_text())
        else:
            console.error("Provide --file reports.json (or --simulate).")
            return 1
        est = sigint.geolocate(reports)
        console.rule("Multi-node RSSI geolocation")
        if est.lat is None:
            console.warn(est.detail)
            return 1
        console.success(f"Estimated position: {est.lat}, {est.lon} "
                        f"({est.confidence}% · {est.n_receivers} receivers)")
        console.print_(f"  strongest receiver: {est.strongest}  ·  {est.detail}")
        return 0

    if sub == "gnss":
        import json
        from .modules import gnss as gnss_mod
        as_json = getattr(args, "json", False)
        if not as_json:
            console.rule("GNSS interference & spoofing detection")

        observations = []
        if args.simulate:
            sim_map = {"nominal": gnss_mod.simulate_nominal,
                       "jamming": gnss_mod.simulate_jamming,
                       "spoofing": gnss_mod.simulate_spoofing}
            observations = sim_map[args.simulate]()
            if not as_json:
                console.info(f"Simulated scenario: {args.simulate}")
        elif args.file:
            try:
                raw = json.loads(Path(args.file).read_text())
            except (OSError, ValueError) as exc:
                console.error(f"Could not read observations: {exc}")
                return 2
            for o in raw:
                observations.append(gnss_mod.GnssObservation(
                    t=float(o.get("t", 0.0)),
                    lat=o.get("lat"), lon=o.get("lon"), alt=o.get("alt"),
                    cn0=list(o.get("cn0", [])), elevations=list(o.get("elevations", [])),
                    agc=o.get("agc"), num_sats=o.get("num_sats"),
                    fix=bool(o.get("fix", True))))

        report = None
        if observations:
            known = tuple(args.known) if args.known else None
            report = gnss_mod.detect_gnss_interference(
                observations, known_location=known, static=args.static)
            if as_json:
                console.raw(json.dumps({
                    "status": report.status, "confidence": report.confidence,
                    "samples": report.samples,
                    "findings": [{"indicator": f.indicator, "kind": f.kind,
                                  "severity": f.severity, "detail": f.detail}
                                 for f in report.findings]}, indent=2))
                return 0 if report.status == "nominal" else 1
            if report.status == "nominal":
                console.success(f"Nominal — no interference indicators ({report.samples} obs).")
            else:
                console.error(f"{report.status.upper()} suspected ({report.confidence}% · "
                              f"{report.samples} obs)")
                for f in report.findings:
                    tag = "JAM" if f.kind == "jamming" else "SPOOF"
                    console.print_(f"  [{tag}/{f.severity}] {f.indicator}: {f.detail}")
        elif not args.iq:
            console.error("Provide --simulate [scenario], --file observations.json, or --iq capture.")
            return 1

        if args.iq:
            from .modules import iqtools
            try:
                iq = iqtools.load_iq(Path(args.iq))
                l1 = gnss_mod.analyze_l1_power(iq, args.sample_rate)
            except (RuntimeError, OSError, ImportError) as exc:
                console.error(f"L1 power check failed (needs NumPy + IQ file): {exc}")
                return 2
            if l1.get("anomaly"):
                console.error(f"L1 anomaly: {l1['note']} "
                              f"(power {l1.get('power')}, flatness {l1.get('flatness')})")
            else:
                console.success(f"L1 check: {l1['note']}")
        return 0

    console.error("Unknown sigint subcommand.")
    return 1


def cmd_bookmark(args: argparse.Namespace, cfg: Config) -> int:
    if args.bm_cmd == "add":
        cfg.bookmarks = [b for b in cfg.bookmarks if b.get("name") != args.name]
        cfg.bookmarks.append({"name": args.name, "freq_mhz": args.freq,
                              "note": args.note or ""})
        save_config(cfg)
        console.success(f"Bookmarked '{args.name}' at {args.freq} MHz")
        return 0
    if args.bm_cmd == "remove":
        before = len(cfg.bookmarks)
        cfg.bookmarks = [b for b in cfg.bookmarks if b.get("name") != args.name]
        save_config(cfg)
        console.success(f"Removed '{args.name}'" if len(cfg.bookmarks) < before
                        else f"No bookmark named '{args.name}'")
        return 0
    # list
    if not cfg.bookmarks:
        console.warn("No bookmarks yet. Add one: rfhound bookmark add <name> <MHz>")
        return 0
    rows = []
    for b in sorted(cfg.bookmarks, key=lambda x: x.get("freq_mhz", 0)):
        f = b.get("freq_mhz", 0)
        itu = bandplan.itu_band(int(f * 1e6))
        rows.append([b.get("name", ""), f"{f:.4f}", itu[0] if itu else "—", b.get("note", "")])
    console.table("Bookmarks / memory channels", ["Name", "Freq (MHz)", "ITU", "Note"], rows)
    return 0


def cmd_config(args: argparse.Namespace, cfg: Config) -> int:
    if args.config_cmd == "path":
        console.print_(str(config_path()))
        return 0
    if args.config_cmd == "init":
        path = save_config(cfg)
        console.success(f"Wrote default config to {path}")
        return 0
    # show
    import json
    console.raw(json.dumps(cfg.to_dict(), indent=2))
    return 0


def cmd_menu(args: argparse.Namespace, cfg: Config) -> int:
    from .menu import run_menu
    return run_menu(cfg)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rfhound",
        description="HackRF reconnaissance & RF situational-awareness toolkit (receive-first).",
        epilog=(
            "quick start:\n"
            "  rfhound                      guided menu (run with no args)\n"
            "  rfhound setup                one-time setup summary\n"
            "  rfhound --simulate recon     try it with no hardware\n"
            "  rfhound at 433.92            what's here + every tool for it\n"
            "  rfhound tune adsb            what frequency do I need?\n"
            "  rfhound sweep 430 440 --identify   auto-identify signals\n"
            "  rfhound defense respond jamming    a threat's response playbook\n"
            "  rfhound web --open           browser dashboard + REST API\n"
            "\nfull reference: docs/HELP.md  ·  tutorial: docs/TUTORIAL.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"rfhound {__version__}")
    p.add_argument("--dev", action="store_true", help="Developer mode: verbose debug + tracebacks")
    p.add_argument("--simulate", dest="simulate_global", action="store_true",
                   help="Global simulate mode: run everything against synthetic data")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("setup", help="One-time setup summary + next steps").set_defaults(func=cmd_setup)

    pdev = sub.add_parser("device", help="HackRF device: info, Opera Cake switch, clock")
    devsub = pdev.add_subparsers(dest="device_cmd")
    devsub.add_parser("info", help="Show hackrf_info output")
    devop = devsub.add_parser("operacake", help="Control an Opera Cake antenna switch")
    devop.add_argument("--a", help="Port for primary A (e.g. A0..A3/B0..B3)")
    devop.add_argument("--b", help="Port for primary B")
    devsub.add_parser("clock", help="Read clock reference status")
    pdev.set_defaults(func=cmd_device, device_cmd="info", a=None, b=None)
    pdoc = sub.add_parser("doctor", help="Check tools, HackRF device and config")
    pdoc.add_argument("--json", action="store_true", help="Machine-readable health output")
    pdoc.set_defaults(func=cmd_doctor)
    sub.add_parser("menu", help="Launch the guided interactive menu").set_defaults(func=cmd_menu)

    pw = sub.add_parser("web", help="Launch the browser dashboard + REST API")
    pw.add_argument("--host", default="127.0.0.1", help="Bind address (default localhost)")
    pw.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    pw.add_argument("--simulate", action="store_true", help="Force simulate mode")
    pw.add_argument("--open", action="store_true", help="Open a browser window")
    pw.add_argument("--token", nargs="?", const="auto", default=None,
                    help="Require this API token (or 'auto'/no value to generate one). "
                         "Auto-generated when binding to a non-localhost host.")
    pw.set_defaults(func=cmd_web)

    pb = sub.add_parser("bands", help="Browse the frequency knowledge base")
    pb.add_argument("--category", help="Filter by category (ism, aviation, ...)")
    pb.add_argument("--tag", help="Filter by tag (tpms, keyfob, adsb, ...)")
    pb.add_argument("--search", help="Substring search of name/description")
    pb.add_argument("-v", "--verbose", action="store_true", help="Show descriptions")
    pb.set_defaults(func=cmd_bands)

    pat = sub.add_parser("at", help="Identify the band at a frequency and list its tools")
    pat.add_argument("freq", type=float, help="Frequency (MHz)")
    pat.add_argument("--json", action="store_true", help="Machine-readable output")
    pat.set_defaults(func=cmd_at)

    ptu = sub.add_parser("tune", help="Find the frequency to tune to for a protocol/name")
    ptu.add_argument("query", help="Protocol/name, e.g. adsb, tpms, pager, drone")
    ptu.add_argument("--json", action="store_true", help="Machine-readable output")
    ptu.set_defaults(func=cmd_tune)

    pcl = sub.add_parser("classify", help="Guess a signal's type + likelihood from its characteristics")
    pcl.add_argument("freq", type=float, nargs="?", help="Center frequency (MHz)")
    pcl.add_argument("--bw", type=float, help="Occupied bandwidth (kHz), if known")
    pcl.add_argument("--mod", help="Modulation hint: ook, fsk, gfsk, fm, am, ofdm, gmsk, pulse…")
    pcl.add_argument("--file", help="Analyze an IQ capture (.sigmf-data) for real bw + modulation")
    pcl.add_argument("--json", action="store_true", help="Machine-readable output")
    pcl.set_defaults(func=cmd_classify)

    ps = sub.add_parser("sweep", help="Wideband spectrum sweep")
    ps.add_argument("start", type=float, help="Start frequency (MHz)")
    ps.add_argument("stop", type=float, help="Stop frequency (MHz)")
    ps.add_argument("--bin", type=int, default=100, help="Bin width (kHz)")
    ps.add_argument("--snr", type=float, default=12.0, help="Peak threshold above floor (dB)")
    ps.add_argument("--sweeps", type=int, default=1, help="Number of peak-held passes")
    ps.add_argument("--top", type=int, default=15, help="Show top-N peaks")
    ps.add_argument("--identify", action="store_true",
                    help="Auto-identify each peak (bandwidth + likely signal + decoder)")
    ps.add_argument("--watch", action="store_true", help="Live, continuously-updating spectrum")
    ps.add_argument("--interval", type=float, default=1.0, help="Seconds between watch frames")
    ps.add_argument("--count", type=int, default=0, help="Watch frames to draw (0 = until Ctrl-C)")
    ps.add_argument("--simulate", action="store_true", help="Synthesise data (no hardware)")
    ps.set_defaults(func=cmd_sweep)

    pr = sub.add_parser("recon", help="Auto-survey the high-value bands")
    pr.add_argument("--category", help="Restrict to one band category")
    pr.add_argument("--snr", type=float, default=12.0, help="Peak threshold (dB)")
    pr.add_argument("--bin", type=int, default=100, help="Bin width (kHz)")
    pr.add_argument("--report", help="Write a report to this path (.md or .html)")
    pr.add_argument("--simulate", action="store_true", help="Synthesise data (no hardware)")
    pr.set_defaults(func=cmd_recon)

    pc = sub.add_parser("capture", help="Record IQ to disk (with SigMF metadata)")
    pc.add_argument("freq", type=float, help="Center frequency (MHz)")
    pc.add_argument("seconds", type=float, help="Duration (s)")
    pc.add_argument("--name", help="Base filename")
    pc.add_argument("--rate", type=int, help="Sample rate (Hz)")
    pc.add_argument("--note", help="Free-text note stored in metadata")
    pc.add_argument("--classify", action="store_true",
                    help="Analyze the capture and store bandwidth/modulation/decoder in metadata")
    pc.add_argument("--simulate", action="store_true", help="Write placeholder (no hardware)")
    pc.set_defaults(func=cmd_capture)

    prec = sub.add_parser("recordings", help="Catalog captures + their classification/decode settings")
    recsub = prec.add_subparsers(dest="rec_cmd")
    recsub.add_parser("list", help="List recordings with classification")
    recshow = recsub.add_parser("show", help="Show a recording's full metadata")
    recshow.add_argument("name")
    reccl = recsub.add_parser("classify", help="Classify a recording and store the result")
    reccl.add_argument("name")
    prec.set_defaults(func=cmd_recordings, rec_cmd="list", name=None)

    pd = sub.add_parser("decode", help="Protocol decoders (rtl_433, ADS-B, pagers, AIS...)")
    dsub = pd.add_subparsers(dest="decode_cmd", required=True)
    dsub.add_parser("list", help="List decoder recipes")
    drun = dsub.add_parser("run", help="Run a decoder recipe")
    drun.add_argument("recipe", help="Recipe id (see 'decode list')")
    drun.add_argument("--freq", type=float, help="Override frequency (MHz)")
    drun.add_argument("--seconds", type=float, default=30, help="Listen duration (s)")
    drun.add_argument("--track", action="store_true",
                      help="Record decoded IDs (ICAO/MMSI/sensor/capcode) to the sightings log")
    drun.add_argument("--dry-run", action="store_true", help="Print the command only")
    pd.set_defaults(func=cmd_decode)

    prp = sub.add_parser("replay", help="Replay a captured IQ file (GATED, authorized only)")
    prp.add_argument("file", help="Path to a .sigmf-data / .iq capture")
    prp.add_argument("--freq", type=float, help="Override frequency (MHz)")
    prp.add_argument("--gain", type=int, help="TX VGA gain (0-47 dB)")
    prp.add_argument("--authorized", action="store_true",
                     help="Assert you are authorized to transmit this signal")
    prp.add_argument("--dry-run", action="store_true", help="Show command, do not transmit")
    prp.set_defaults(func=cmd_replay)

    pt = sub.add_parser("tx", help="Manage transmit authorization")
    tsub = pt.add_subparsers(dest="tx_cmd", required=True)
    tsub.add_parser("status", help="Show transmit settings + recent audit")
    tsub.add_parser("disable", help="Disable transmit")
    ta = tsub.add_parser("audit", help="Show the append-only transmit audit log")
    ta.add_argument("--top", type=int, default=50, help="Show the most recent N events")
    ta.add_argument("--json", action="store_true", help="Machine-readable output")
    ta.add_argument("--clear", action="store_true", help="Clear the audit log")
    te = tsub.add_parser("enable", help="Enable transmit with a frequency allow-list")
    te.add_argument("--allow", action="append", metavar="MHZ-MHZ",
                    help="Allowed TX range (repeatable), e.g. --allow 433.0-434.8")
    te.add_argument("--jurisdiction", help="Your jurisdiction (for reports)")
    te.add_argument("--yes", action="store_true", help="Accept legal terms non-interactively")
    pt.set_defaults(func=cmd_tx, top=50, json=False, clear=False)

    pdf = sub.add_parser("defense", help="Defensive analysis: detect attacks, assess resilience")
    fsub = pdf.add_subparsers(dest="defense_cmd", required=True)

    fm = fsub.add_parser("monitor", help="Detect jamming / interference on a band")
    fm.add_argument("start", type=float, help="Start frequency (MHz)")
    fm.add_argument("stop", type=float, help="Stop frequency (MHz)")
    fm.add_argument("--samples", type=int, default=12, help="Number of sweeps to take")
    fm.add_argument("--interval", type=float, default=1.0, help="Seconds between sweeps")
    fm.add_argument("--threshold", type=float, default=10.0,
                    help="Noise-floor rise over baseline that triggers an alarm (dB)")
    fm.add_argument("--simulate", action="store_true", help="Synthesise a jamming event")

    fr = fsub.add_parser("rolling-assess", help="Assess a device's fixed/rolling-code posture")
    fr.add_argument("--file", help="Text file of captured payloads, one per line")
    fr.add_argument("--kind", default="fixed", choices=["fixed", "counter", "rolling"],
                    help="With --simulate, which synthetic device to model")
    fr.add_argument("--simulate", action="store_true", help="Use synthetic payloads")

    frc = fsub.add_parser("replay-check", help="Detect replay attacks in observed transmissions")
    frc.add_argument("--file", help="'timestamp payload' per line")
    frc.add_argument("--fixed", action="store_true",
                     help="Device uses a fixed code (only flag implausibly fast repeats)")
    frc.add_argument("--simulate", action="store_true", help="Use a synthetic replay trace")

    fbl = fsub.add_parser("baseline", help="TSCM: save a known-good spectrum and diff for rogue emitters")
    blsub = fbl.add_subparsers(dest="baseline_cmd", required=True)
    bsave = blsub.add_parser("save", help="Save a baseline sweep")
    bsave.add_argument("start", type=float, help="Start MHz")
    bsave.add_argument("stop", type=float, help="Stop MHz")
    bsave.add_argument("--out", required=True, help="Baseline output path (.json)")
    bsave.add_argument("--simulate", action="store_true")
    bdiff = blsub.add_parser("diff", help="Diff current spectrum against a saved baseline")
    bdiff.add_argument("file", help="Saved baseline .json")
    bdiff.add_argument("--threshold", type=float, default=10.0,
                       help="dB increase over baseline that flags an emitter")
    bdiff.add_argument("--simulate", action="store_true")

    fsc = fsub.add_parser("spoof-check", help="Detect ADS-B / AIS spoofing in decoded messages")
    fsc.add_argument("protocol", choices=["adsb", "ais"])
    fsc.add_argument("--file", help="JSON array of decoded messages")
    fsc.add_argument("--simulate", action="store_true", help="Use a synthetic spoofed stream")

    fds = fsub.add_parser("drone-scan", help="Counter-UAS: scan drone control/video bands")
    fds.add_argument("--simulate", action="store_true")

    fhp = fsub.add_parser("hop-detect", help="Detect frequency-hopping (agile) emitters")
    fhp.add_argument("--simulate", action="store_true")

    fic = fsub.add_parser("imsi-catcher",
                          help="Detect rogue base station / IMSI-catcher indicators (defensive)")
    fic.add_argument("--file", help="JSON array of observed cell records")
    fic.add_argument("--simulate", action="store_true")

    frs = fsub.add_parser("respond", help="Show the defensive counter-threat playbook for a threat")
    frs.add_argument("threat", help="jamming|gps_spoof|adsb_spoof|ais_spoof|drone|rogue_emitter|replay")

    fres = fsub.add_parser("resilience", help="Resilience-test YOUR OWN device and report")
    fres.add_argument("--device", help="Name/label of the device under test")
    fres.add_argument("--payloads", help="Text file of captured payloads (one per line)")
    fres.add_argument("--replayed", action="store_true",
                      help="You performed the gated replay (rfhound replay --authorized)")
    fres.add_argument("--actuated", type=lambda s: s.lower() in ("1", "true", "yes", "y"),
                      default=None, help="Did the device actuate on replay? true/false")
    fres.add_argument("--simulate", action="store_true", help="Run a synthetic resilience test")
    pdf.set_defaults(func=cmd_defense)

    sub.add_parser("dev", help="Developer diagnostics").set_defaults(func=cmd_dev)

    pai = sub.add_parser("ai", help="Interactive AI copilot console (receive/analysis only)")
    pai.add_argument("--provider", choices=["offline", "anthropic", "local"],
                     help="LLM backend (default: config or offline)")
    pai.set_defaults(func=cmd_ai)

    pa = sub.add_parser("ask", help="One-shot LLM copilot query (receive/analysis only)")
    pa.add_argument("query", help="Natural-language request")
    pa.add_argument("--provider", choices=["offline", "anthropic", "local"],
                    help="LLM backend (default: config or offline)")
    pa.set_defaults(func=cmd_ask)

    ph = sub.add_parser("hub", help="Run the multi-node aggregator hub")
    ph.add_argument("--host", default="127.0.0.1")
    ph.add_argument("--port", type=int, default=8787)
    ph.add_argument("--token", default="", help="Shared bearer token for node auth")
    ph.set_defaults(func=cmd_hub)

    pn = sub.add_parser("node", help="Push this receiver's findings to a hub")
    pn.add_argument("--hub", help="Hub URL, e.g. http://10.0.0.5:8787")
    pn.add_argument("--id", help="Node id")
    pn.add_argument("--name", help="Node display name")
    pn.add_argument("--location", help="Node location label")
    pn.add_argument("--scan", choices=["recon", "drone", "imsi"],
                    help="Run this scan and push the result")
    pn.add_argument("--token", default="", help="Shared bearer token")
    pn.add_argument("--simulate", action="store_true")
    pn.set_defaults(func=cmd_node)

    pg = sub.add_parser("gnuradio", help="GNU Radio receive/analysis flowgraph presets")
    gsub = pg.add_subparsers(dest="gr_cmd")
    gsub.add_parser("status", help="Check whether GNU Radio + gr-osmosdr are installed")
    gsub.add_parser("list", help="List prebuilt flowgraph presets")
    ggen = gsub.add_parser("gen", help="Generate a runnable flowgraph")
    ggen.add_argument("preset", help="Preset id (see 'gnuradio list')")
    ggen.add_argument("--freq", type=float, required=True, help="Center frequency (MHz)")
    ggen.add_argument("--rate", type=int, help="Sample rate (Hz)")
    ggen.add_argument("--out", help="Output .py path")
    ggen.add_argument("--data-out", help="Preset output file (wav/iq/f32)")
    ggen.add_argument("--quiet", action="store_true", help="Don't print the generated code")
    pg.set_defaults(func=cmd_gnuradio, gr_cmd="list")

    psi = sub.add_parser("sigint", help="SIGINT/EW-support: ELINT, jamming char., EOB, geolocation")
    sisub = psi.add_subparsers(dest="sigint_cmd")
    sip = sisub.add_parser("pulse", help="ELINT pulse analysis (PW/PRI) from an IQ capture")
    sip.add_argument("--file", help="IQ capture (.sigmf-data)")
    sij = sisub.add_parser("jamming", help="Characterise interference type on a band")
    sij.add_argument("start", type=float, help="Start MHz")
    sij.add_argument("stop", type=float, help="Stop MHz")
    sij.add_argument("--simulate", action="store_true")
    sie = sisub.add_parser("emitters", help="Emitter catalogue / Electronic Order of Battle")
    sie.add_argument("--scan", action="store_true", help="Sweep and ingest peaks first")
    sie.add_argument("start", type=float, nargs="?", default=430.0, help="Scan start MHz")
    sie.add_argument("stop", type=float, nargs="?", default=440.0, help="Scan stop MHz")
    sie.add_argument("--clear", action="store_true", help="Clear the catalogue")
    sie.add_argument("--simulate", action="store_true")
    sil = sisub.add_parser("locate", help="Estimate emitter position (RSSI centroid or TDOA)")
    sil.add_argument("--file", help="JSON array of {node,lat,lon,rssi} (or +tdoa_s for --tdoa)")
    sil.add_argument("--tdoa", action="store_true",
                     help="TDOA multilateration (needs >=3 synchronised nodes with tdoa_s)")
    sil.add_argument("--hub", help="Pull TDOA contributions from this hub URL and solve")
    sil.add_argument("--trigger", help="Collection trigger tag to solve (default: latest)")
    sil.add_argument("--token", default="", help="Hub bearer token")
    sil.add_argument("--simulate", action="store_true")
    sig = sisub.add_parser(
        "gnss", help="GNSS jamming/spoofing DETECTION from receiver observations (EP)")
    sig.add_argument("--file", help="JSON array of GNSS observations "
                     "[{t,lat,lon,alt,cn0[],elevations[],agc,num_sats,fix}, ...]")
    sig.add_argument("--iq", help="IQ capture near L1 (1575.42 MHz) for a power/carrier check")
    sig.add_argument("--sample-rate", type=int, default=2_000_000,
                     help="Sample rate of the --iq capture (Hz)")
    sig.add_argument("--static", action="store_true",
                     help="Receiver is fixed — flag any reported movement as spoofing")
    sig.add_argument("--known", nargs=2, type=float, metavar=("LAT", "LON"),
                     help="Known receiver location; flag disagreement as spoofing")
    sig.add_argument("--simulate", nargs="?", const="spoofing",
                     choices=["nominal", "jamming", "spoofing"],
                     help="Run a built-in scenario (default: spoofing)")
    sig.add_argument("--json", action="store_true", help="Machine-readable output")
    psi.set_defaults(func=cmd_sigint, sigint_cmd=None, simulate=False,
                     start=430.0, stop=440.0, file=None, scan=False, clear=False,
                     tdoa=False, hub=None, trigger=None, token="",
                     iq=None, sample_rate=2_000_000, static=False, known=None, json=False)

    pau = sub.add_parser("automate", help="Automation: scheduled/looping RF tasks with alerting")
    ausub = pau.add_subparsers(dest="automate_cmd")
    ausub.add_parser("menu", help="Interactive automation menu")
    ausub.add_parser("list", help="List automations")
    auadd = ausub.add_parser("add", help="Define an automation")
    auadd.add_argument("name")
    auadd.add_argument("task", choices=["recon", "monitor", "drone", "imsi", "hop", "sweep"])
    auadd.add_argument("--interval", type=int, default=60, help="Run every N seconds")
    auadd.add_argument("--start", type=float, help="Start MHz (monitor/sweep)")
    auadd.add_argument("--stop", type=float, help="Stop MHz (monitor/sweep)")
    auadd.add_argument("--alert-on", dest="alert_on", default="threat",
                       choices=["threat", "always", "change"])
    auadd.add_argument("--webhook", help="POST alerts to this URL")
    aurm = ausub.add_parser("remove", help="Delete an automation")
    aurm.add_argument("name")
    auen = ausub.add_parser("enable", help="Enable an automation")
    auen.add_argument("name")
    audi = ausub.add_parser("disable", help="Disable an automation")
    audi.add_argument("name")
    auon = ausub.add_parser("once", help="Run an automation (or all) once now")
    auon.add_argument("name", nargs="?")
    auon.add_argument("--simulate", action="store_true")
    aur = ausub.add_parser("run", help="Run the scheduler loop (Ctrl-C to stop)")
    aur.add_argument("--simulate", action="store_true")
    pau.set_defaults(func=cmd_automate, automate_cmd=None, simulate=False, name=None)

    ptr = sub.add_parser("track", help="Track decoded IDs (aircraft/vessel/sensor/pager)")
    trsub = ptr.add_subparsers(dest="track_cmd")
    trl = trsub.add_parser("list", help="List tracked sightings")
    trl.add_argument("--kind", help="Filter by kind (adsb, ais, rtl433, pocsag, cell…)")
    trl.add_argument("--top", type=int, default=50, help="Show top-N")
    tra = trsub.add_parser("add", help="Manually record a sighting")
    tra.add_argument("kind")
    tra.add_argument("id")
    tra.add_argument("--freq", type=float, help="Frequency (MHz)")
    tra.add_argument("--note")
    trs = trsub.add_parser("show", help="Show details for an id")
    trs.add_argument("id")
    trc = trsub.add_parser("clear", help="Clear sightings")
    trc.add_argument("--kind", help="Only clear this kind")
    ptr.set_defaults(func=cmd_track, track_cmd="list", kind=None, top=50)

    pbm = sub.add_parser("bookmark", help="Save/list frequency bookmarks (memory channels)")
    bmsub = pbm.add_subparsers(dest="bm_cmd")
    bmadd = bmsub.add_parser("add", help="Save a frequency")
    bmadd.add_argument("name")
    bmadd.add_argument("freq", type=float, help="Frequency (MHz)")
    bmadd.add_argument("--note", help="Optional note")
    bmsub.add_parser("list", help="List bookmarks")
    bmrm = bmsub.add_parser("remove", help="Remove a bookmark by name")
    bmrm.add_argument("name")
    pbm.set_defaults(func=cmd_bookmark, bm_cmd="list")

    pm = sub.add_parser("mods", help="Manage extension mods/plugins")
    msub = pm.add_subparsers(dest="mods_cmd")
    ml = msub.add_parser("list", help="Load and list mods")
    ml.add_argument("--dir", help="Mods directory (default ~/.config/rfhound/mods)")
    msub.add_parser("sample", help="Write a sample mod to the mods directory")
    pm.set_defaults(func=cmd_mods, mods_cmd="list", dir=None)

    pcfg = sub.add_parser("config", help="Show / init configuration")
    csub = pcfg.add_subparsers(dest="config_cmd")
    csub.add_parser("show", help="Print current config")
    csub.add_parser("init", help="Write a default config file")
    csub.add_parser("path", help="Print config file path")
    pcfg.set_defaults(func=cmd_config, config_cmd="show")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = load_config()
    if getattr(args, "dev", False):
        cfg.dev_mode = True
        console.set_debug(True)

    # Global simulate mode (flag or config) forces synthetic data everywhere.
    if getattr(args, "simulate_global", False) or cfg.simulate_mode:
        cfg.simulate_mode = True
        if hasattr(args, "simulate"):
            args.simulate = True
        console.debug("global simulate mode active")

    if not getattr(args, "command", None):
        # No subcommand -> friendly interactive menu.
        console.banner(__version__)
        from .menu import run_menu
        return run_menu(cfg)

    try:
        return args.func(args, cfg)
    except RFHoundError as exc:
        console.error(str(exc))
        if cfg.dev_mode:
            raise
        return 2
    except KeyboardInterrupt:
        console.warn("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
