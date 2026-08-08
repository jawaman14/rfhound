from pathlib import Path

from rfhound.config import Config
from rfhound.modules import pdf, recon, report


def test_pdfdoc_valid_structure():
    doc = pdf.PdfDoc("Title")
    doc.heading("Section", 2)
    doc.paragraph("A paragraph with unicode → • ± that must transliterate.")
    doc.bullet("a bullet")
    doc.table(["A", "B"], [["1", "2"], ["3", "4"]])
    out = doc.render()
    assert out.startswith(b"%PDF-1.4")
    assert out.rstrip().endswith(b"%%EOF")
    assert b"xref" in out and b"/Type /Catalog" in out and b"/Type /Pages" in out
    # Content is pure ASCII (unicode transliterated) — no raw multibyte in stream.
    assert "→".encode() not in out and "•".encode() not in out


def test_pdf_escapes_parentheses():
    doc = pdf.PdfDoc()
    doc.paragraph("value (paren) and back\\slash")
    out = doc.render()
    assert br"\(" in out and br"\)" in out


def test_report_pdf_roundtrip(tmp_path):
    rep = recon.run_recon(Config(), simulate=True, progress=False)
    out = report.write_report(rep, tmp_path / "r.pdf", fmt="pdf")
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"%%EOF" in data
    assert len(data) > 500


def test_fmt_for_path():
    assert report.fmt_for_path(Path("x.pdf")) == "pdf"
    assert report.fmt_for_path(Path("x.PDF")) == "pdf"
    assert report.fmt_for_path(Path("x.html")) == "html"
    assert report.fmt_for_path(Path("x.md")) == "md"
    assert report.fmt_for_path(Path("x")) == "md"
