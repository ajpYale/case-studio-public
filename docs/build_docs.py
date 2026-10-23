"""Build self-contained docs/report.html and docs/slides.html from the *_src.html sources.

Every <img src="screenshots/..."> is inlined as a base64 data URI, so the output opens by
double-clicking on any computer with every image visible. Run from anywhere:

    python docs/build_docs.py
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent
IMG = re.compile(r'(<img\b[^>]*?\bsrc=")(?!data:|https?:)([^"]+)(")')


def inline_images(html: str) -> str:
    def swap(m: re.Match) -> str:
        path = (DOCS / m.group(2)).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"missing image: {m.group(2)}")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"{m.group(1)}data:{mime};base64,{data}{m.group(3)}"
    return IMG.sub(swap, html)


HEADING = re.compile(r"<(h[23])\b[^>]*>.*?</\1>\s*", re.S)
BLOCK = re.compile(r"<(p|ul|ol|div|figure|pre|table)\b", re.S)


def _block_end(html: str, start: int, tag: str) -> int:
    """Index just past the element that opens at `start` (counts nested tags of the same name)."""
    depth, pos = 0, start
    opener, closer = re.compile(rf"<{tag}\b"), f"</{tag}>"
    while True:
        o = opener.search(html, pos)
        c = html.find(closer, pos)
        if c == -1:
            return -1
        if o and o.start() < c:
            depth, pos = depth + 1, o.end()
        else:
            depth, pos = depth - 1, c + len(closer)
            if depth == 0:
                return pos


def keep_headings_with_content(html: str) -> str:
    """Wrap every h2/h3 with the block that follows it so print never strands a heading at a page bottom."""
    out, pos = [], 0
    body = html.find("<body")
    for m in HEADING.finditer(html, body):
        if m.start() < pos:
            continue  # already glued to the heading before it
        after = m.end()
        while (sub := HEADING.match(html, after)):  # an h2 directly followed by an h3: keep both with the content
            after = sub.end()
        nxt = BLOCK.match(html, after)
        if not nxt:
            continue
        end = _block_end(html, nxt.start(), nxt.group(1))
        if end == -1 or end - nxt.start() > 6000:  # don't glue a heading to a huge table or figure
            continue
        out.append(html[pos:m.start()])
        out.append('<div class="keep-next">' + html[m.start():end] + "</div>")
        pos = end
    out.append(html[pos:])
    return "".join(out)


def build(name: str) -> None:
    src = DOCS / f"{name}_src.html"
    if not src.exists():
        print(f"skip {name}: no {src.name}")
        return
    out = DOCS / f"{name}.html"
    html = src.read_text(encoding="utf-8")
    if name == "report":
        html = keep_headings_with_content(html)
    out.write_text(inline_images(html), encoding="utf-8")
    print(f"wrote {out.name} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    build("report")
    build("slides")
