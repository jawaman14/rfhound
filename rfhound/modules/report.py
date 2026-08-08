"""Generate Markdown / HTML reports from a recon session."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from .recon import ReconReport


def to_markdown(report: ReconReport, *, title: str = "RFHound recon report") -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"# {title}",
        "",
        f"- Generated: {now}",
        f"- RFHound version: {__version__}",
        f"- Mode: {'SIMULATED (no hardware)' if report.simulated else 'live capture'}",
        f"- Bands surveyed: {len(report.findings)}",
        f"- Active bands: {len(report.active_findings)}",
        "",
        "> Receive-only reconnaissance. Verify authorization before any transmit.",
        "",
        "## Active findings",
        "",
    ]
    if not report.active_findings:
        lines.append("_No active signals detected._")
    else:
        lines.append("| Band | Category | Peaks | Strongest | Suggested decoder |")
        lines.append("|------|----------|-------|-----------|-------------------|")
        for f in report.active_findings:
            top = max(f.peaks, key=lambda p: p.power_db)
            lines.append(
                f"| {f.band.name} | {f.band.category} | {len(f.peaks)} | "
                f"{top.freq_mhz:.3f} MHz @ {top.power_db} dB | "
                f"{f.band.decoder or '-'} |"
            )
    lines += ["", "## Detailed peaks", ""]
    for f in report.findings:
        lines.append(f"### {f.band.name}  ({f.band.low_hz/1e6:.3f}-{f.band.high_hz/1e6:.3f} MHz)")
        lines.append("")
        lines.append(f"{f.band.description}")
        lines.append("")
        lines.append(f"- Noise floor: {f.noise_floor_db} dB")
        if f.peaks:
            for p in sorted(f.peaks, key=lambda p: p.power_db, reverse=True):
                b = p.band
                extra = f" — {b.description}" if b else ""
                lines.append(f"- **{p.freq_mhz:.4f} MHz** @ {p.power_db} dB{extra}")
        else:
            lines.append("- (quiet)")
        lines.append("")
    return "\n".join(lines)


def to_html(report: ReconReport, *, title: str = "RFHound recon report") -> str:
    md_rows = []
    for f in report.active_findings:
        top = max(f.peaks, key=lambda p: p.power_db)
        md_rows.append(
            f"<tr><td>{html.escape(f.band.name)}</td>"
            f"<td>{html.escape(f.band.category)}</td>"
            f"<td>{len(f.peaks)}</td>"
            f"<td>{top.freq_mhz:.3f} MHz @ {top.power_db} dB</td>"
            f"<td>{html.escape(f.band.decoder or '-')}</td></tr>"
        )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mode = "SIMULATED (no hardware)" if report.simulated else "live capture"
    rows_html = "\n".join(md_rows) or "<tr><td colspan=5>No active signals detected.</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 900px;
         color: #e6e6e6; background: #14161a; }}
  h1 {{ color: #4fd1c5; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #333; padding: .5rem .75rem; text-align: left; }}
  th {{ background: #1e2228; color: #4fd1c5; }}
  .meta {{ color: #9aa; font-size: .9rem; }}
  .warn {{ background:#2a2410; border-left:4px solid #d4a017; padding:.75rem 1rem; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="meta">Generated {now} · RFHound v{__version__} · Mode: {mode} ·
  {len(report.active_findings)}/{len(report.findings)} bands active</p>
<div class="warn">Receive-only reconnaissance. Confirm you are authorized before transmitting.</div>
<table>
<thead><tr><th>Band</th><th>Category</th><th>Peaks</th><th>Strongest</th><th>Decoder</th></tr></thead>
<tbody>
{rows_html}
</tbody></table>
</body></html>
"""


def to_pdf(report: ReconReport, *, title: str = "RFHound recon report") -> bytes:
    """Render the recon report to a PDF (dependency-free, base-14 fonts)."""
    from .pdf import PdfDoc
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mode = "SIMULATED (no hardware)" if report.simulated else "live capture"
    doc = PdfDoc(title)
    doc.paragraph(f"Generated {now}  ·  RFHound v{__version__}  ·  Mode: {mode}  ·  "
                  f"{len(report.active_findings)}/{len(report.findings)} bands active")
    doc.paragraph("Receive-only reconnaissance. Confirm you are authorized before "
                  "transmitting.")

    doc.heading("Active findings", 2)
    if not report.active_findings:
        doc.paragraph("No active signals detected.")
    else:
        rows = []
        for f in report.active_findings:
            top = max(f.peaks, key=lambda p: p.power_db)
            rows.append([f.band.name, f.band.category, len(f.peaks),
                         f"{top.freq_mhz:.3f}MHz@{top.power_db}dB", f.band.decoder or "-"])
        doc.table(["Band", "Category", "Peaks", "Strongest", "Decoder"], rows)

    doc.heading("Detailed peaks", 2)
    for f in report.findings:
        doc.heading(f"{f.band.name}  ({f.band.low_hz/1e6:.3f}-{f.band.high_hz/1e6:.3f} MHz)", 3)
        doc.paragraph(f.band.description)
        doc.paragraph(f"Noise floor: {f.noise_floor_db} dB")
        if f.peaks:
            for p in sorted(f.peaks, key=lambda p: p.power_db, reverse=True):
                extra = f" - {p.band.description}" if p.band else ""
                doc.bullet(f"{p.freq_mhz:.4f} MHz @ {p.power_db} dB{extra}")
        else:
            doc.bullet("(quiet)")
    return doc.render()


def fmt_for_path(path: Path) -> str:
    """Pick the report format from a file suffix (.pdf / .html / .md)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".html", ".htm"):
        return "html"
    return "md"


def write_report(report: ReconReport, out_path: Path, *, fmt: str = "md") -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf":
        out_path.write_bytes(to_pdf(report))
    elif fmt == "html":
        out_path.write_text(to_html(report))
    else:
        out_path.write_text(to_markdown(report))
    return out_path
