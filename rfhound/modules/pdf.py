"""Minimal, dependency-free PDF writer for RFHound reports.

Emits a valid PDF using the built-in PDF base-14 fonts (Helvetica /
Helvetica-Bold for prose, Courier for aligned tables) — no font embedding and
no third-party library, so it keeps RFHound's light-core promise (no reportlab /
weasyprint). Good enough for a clean text report with headings, paragraphs,
bullets and simple tables; it is not a general-purpose typesetter.
"""

from __future__ import annotations

PAGE_W, PAGE_H = 612, 792     # US Letter, points
MARGIN = 54
LEADING = 1.35

# Transliterate the handful of non-ASCII glyphs our reports use, so the content
# stream stays pure ASCII (simple, portable, no font-encoding tables needed).
_SUBS = {
    "•": "*", "→": "->", "–": "-", "—": "-", "…": "...", "±": "+/-", "×": "x",
    "µ": "u", "μ": "u", "σ": "sigma", "≥": ">=", "≤": "<=", "·": "-", "▬": "-",
    "’": "'", "‘": "'", "“": '"', "”": '"', "✓": "OK", "✗": "X", "°": "deg",
}


def _ascii(s: str) -> str:
    for k, v in _SUBS.items():
        s = s.replace(k, v)
    return s.encode("ascii", "ignore").decode("ascii")


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class PdfDoc:
    """Build a simple flowing document, then `render()` to PDF bytes."""

    def __init__(self, title: str = ""):
        self.lines: list = []      # (text, font, size, indent, gap_before)
        if title:
            self.heading(title, 1)

    def _add(self, text, font, size, indent=0, gap=0.0):
        self.lines.append((_ascii(text), font, size, indent, gap))

    def _wrap(self, text, size, indent):
        usable = PAGE_W - 2 * MARGIN - indent
        max_chars = max(8, int(usable / (size * 0.52)))   # Helvetica ~0.52*size wide
        out, cur = [], ""
        for w in _ascii(text).split():
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    out.append(cur)
                while len(w) > max_chars:
                    out.append(w[:max_chars])
                    w = w[max_chars:]
                cur = w
        if cur:
            out.append(cur)
        return out or [""]

    def heading(self, text, level=1):
        size = {1: 18, 2: 14, 3: 11}.get(level, 11)
        for i, ln in enumerate(self._wrap(text, size, 0)):
            self._add(ln, "F2", size, 0, gap=(12 if level == 1 else 9) if i == 0 else 0)

    def paragraph(self, text, indent=0):
        for i, ln in enumerate(self._wrap(text, 11, indent)):
            self._add(ln, "F1", 11, indent, gap=6 if i == 0 else 0)

    def bullet(self, text):
        for i, ln in enumerate(self._wrap(text, 11, 16)):
            self._add(("*  " if i == 0 else "   ") + ln, "F1", 11, 10, gap=3 if i == 0 else 0)

    def spacer(self, pts=6):
        self._add("", "F1", pts, 0, gap=pts)

    def table(self, headers, rows):
        cols = len(headers)
        srows = [[str(c) for c in r] for r in rows]
        widths = [len(str(h)) for h in headers]
        for r in srows:
            for j in range(cols):
                widths[j] = max(widths[j], len(r[j]) if j < len(r) else 0)
        widths = [min(w, 30) for w in widths]   # cap column width

        def fmt(cells):
            return "  ".join(
                (str(cells[j]) if j < len(cells) else "")[:widths[j]].ljust(widths[j])
                for j in range(cols))

        self._add(fmt(headers), "F3", 9, 0, gap=6)      # Courier => columns align
        self._add("-" * min(95, sum(widths) + 2 * (cols - 1)), "F3", 9, 0)
        for r in srows:
            self._add(fmt(r)[:95], "F3", 9, 0)

    # ---- layout + serialise ------------------------------------------------ #
    def _paginate(self):
        pages, cur, y = [], [], PAGE_H - MARGIN
        for (text, font, size, indent, gap) in self.lines:
            y -= gap
            lh = size * LEADING
            if y - lh < MARGIN:
                pages.append(cur)
                cur, y = [], PAGE_H - MARGIN
            y -= lh
            cur.append((MARGIN + indent, y, text, font, size))
        if cur:
            pages.append(cur)
        return pages or [[]]

    def render(self) -> bytes:
        pages = self._paginate()
        objs: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
            5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        }
        n = 6
        page_nums = []
        for page in pages:
            content_num, page_num = n, n + 1
            n += 2
            stream = ""
            for (x, y, text, font, size) in page:
                if not text:
                    continue
                stream += (f"BT /{font} {size:.0f} Tf {x:.1f} {y:.1f} Td "
                           f"({_esc(text)}) Tj ET\n")
            sb = stream.encode("latin-1", "replace")
            objs[content_num] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(sb), sb)
            objs[page_num] = (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
                b"/Contents %d 0 R >>" % (PAGE_W, PAGE_H, content_num))
            page_nums.append(page_num)
        kids = b" ".join(b"%d 0 R" % p for p in page_nums)
        objs[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_nums))

        out = b"%PDF-1.4\n"
        offsets: dict[int, int] = {}
        max_num = max(objs)
        for num in range(1, max_num + 1):
            offsets[num] = len(out)
            out += b"%d 0 obj\n" % num + objs[num] + b"\nendobj\n"
        xref_pos = len(out)
        out += b"xref\n0 %d\n" % (max_num + 1)
        out += b"0000000000 65535 f \n"
        for num in range(1, max_num + 1):
            out += b"%010d 00000 n \n" % offsets[num]
        out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
                % (max_num + 1, xref_pos))
        return out
