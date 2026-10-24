"""Find the exhibits in a casebook case, so the candidate can be shown just them.

Casebooks don't label exhibits consistently, and a page often mixes the exhibit with the
interviewer's notes or the answer. So: a vision model (Luna) looks at each page image and boxes
every candidate-facing exhibit, then code snaps each box to the PDF's own drawing objects, so the
crop hugs the real chart or table even when the model's box is a little off. Results are cached
per case, so each case is processed once (about 0.03 cents a page on Luna).
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Literal

import pypdfium2 as pdfium
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

import casebook
import generator

CACHE_DIR = casebook.BACKEND_DIR / "live" / "exhibits"
MAX_USD_PER_CASE = 0.10
PARALLEL_PAGES = 4
MARGIN = 0.04   # objects mostly inside the model's box grown by this much (share of the page) belong to the exhibit
LIMIT = 0.08    # ...and the crop never grows more than this beyond the model's box
PAD_PT = 6      # breathing room around the final crop, in PDF points
_RUNNING: dict[str, asyncio.Lock] = {}

INSTRUCTIONS = """You look at one page of a consulting case-interview casebook and find the exhibits an
interviewer hands to the candidate: charts, tables, and data handouts the candidate reads.

Box each one tightly, including its title, axis labels, legend and source note, as fractions of the
page (x0, y0 = top-left corner; x1, y1 = bottom-right; all between 0 and 1).

Never box: interviewer guidance or notes, solutions, answer math or model answers, frameworks,
the case prompt read aloud, page headers, footers, logos or page numbers. If an exhibit appears
next to the interviewer's notes, box only the exhibit. If a table or chart already shows the
answers to the case's questions, it is not a candidate exhibit: leave it out. Most pages have no
candidate exhibit; then return an empty list."""


class FoundExhibit(BaseModel):
    title: str = Field(description="The exhibit's title as printed, or a short description if it has none.")
    kind: Literal["chart", "table", "text_handout", "other"]
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)


class PageExhibits(BaseModel):
    exhibits: list[FoundExhibit] = Field(default_factory=list)


@lru_cache(maxsize=2)
def _agent(model: str) -> Agent:
    return Agent(generator._model(model), output_type=PageExhibits, retries=2, instructions=INSTRUCTIONS,
                 model_settings=generator._settings("exhibits"))


# ------------------------------------------------------------------ geometry

def _objects(path, page_no: int) -> tuple[float, float, list[tuple[float, float, float, float]]]:
    """Page size and the bounds (left, bottom, right, top, in points) of everything drawn on the page."""
    with casebook._PDFIUM:
        pdf = pdfium.PdfDocument(str(path))
        try:
            page = pdf[page_no - 1]
            w, h = page.get_size()
            boxes = []
            for obj in page.get_objects():
                try:
                    boxes.append(tuple(obj.get_pos()))
                except Exception:  # an object without bounds
                    continue
        finally:
            pdf.close()
    return w, h, boxes


def snap(found: FoundExhibit, w: float, h: float, objects: list[tuple]) -> list[float]:
    """Turn the model's box (fractions, top-left origin) into a crop in PDF points that hugs the drawn content."""
    fx0, fx1 = sorted((found.x0, found.x1))
    fy0, fy1 = sorted((found.y0, found.y1))
    # PDF points, origin bottom-left: left, bottom, right, top
    box = [fx0 * w, h - fy1 * h, fx1 * w, h - fy0 * h]

    def grown(f: float) -> list[float]:
        return [box[0] - f * w, box[1] - f * h, box[2] + f * w, box[3] + f * h]

    grow, limit = grown(MARGIN), grown(LIMIT)
    page_area = w * h
    inside = []
    for l, b, r, t in objects:
        area = max(0.0, r - l) * max(0.0, t - b)
        if area > 0.6 * page_area:
            continue  # slide backgrounds and full-page frames
        overlap = max(0.0, min(r, grow[2]) - max(l, grow[0])) * max(0.0, min(t, grow[3]) - max(b, grow[1]))
        if area == 0:  # a line or a point: keep it if it sits inside
            if grow[0] <= l and r <= grow[2] and grow[1] <= b and t <= grow[3]:
                inside.append((l, b, r, t))
        elif overlap >= 0.5 * area or (overlap > 0 and limit[0] <= l and r <= limit[2] and limit[1] <= b and t <= limit[3]):
            # mostly inside, or touching it and small enough to fit within the limit (a sideways axis title
            # or a source note at the edge): keep all of it
            inside.append((l, b, r, t))
    if inside:  # the union of what's drawn there, within the limit
        box = [max(limit[0], min(o[0] for o in inside)), max(limit[1], min(o[1] for o in inside)),
               min(limit[2], max(o[2] for o in inside)), min(limit[3], max(o[3] for o in inside))]
    return [max(0.0, box[0] - PAD_PT), max(0.0, box[1] - PAD_PT), min(w, box[2] + PAD_PT), min(h, box[3] + PAD_PT)]


# ------------------------------------------------------------------ finding them

def _cache_path(cid: str):
    return CACHE_DIR / f"{cid}.json"


def cached(cid: str) -> dict | None:
    casebook.path_of(cid)  # validates the id
    p = _cache_path(cid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


async def find(cid: str, refresh: bool = False, meter: generator.Meter | None = None) -> dict:
    """Find (or return the saved) exhibits for one casebook case. Pass a conversion's meter so this spend shows
    on its job card and counts against its budget."""
    path = casebook.path_of(cid)
    lock = _RUNNING.setdefault(cid, asyncio.Lock())
    async with lock:  # two clicks on the same case don't pay twice
        if not refresh and (hit := cached(cid)):
            return hit
        pages = casebook.meta(cid)["pages"]
        meter = meter or generator.Meter(generator.LUNA_MODEL, MAX_USD_PER_CASE)
        start = len(meter.steps)
        agent = _agent(generator.LUNA_MODEL)
        slots = asyncio.Semaphore(PARALLEL_PAGES)

        async def one(p: int) -> list[dict]:
            async with slots:
                png = await asyncio.to_thread(casebook.page_png, cid, p, "full")
                out = await generator._ask(meter, "exhibits", f"Find exhibits on page {p}", [
                    f"Page {p} of {pages} of a casebook case.", BinaryContent(data=png, media_type="image/png")],
                    agent=agent)
            if not out.exhibits:
                return []
            w, h, objects = await asyncio.to_thread(_objects, path, p)
            return [{"page": p, "title": e.title.strip()[:120], "kind": e.kind, "crop": snap(e, w, h, objects),
                     "found": [e.x0, e.y0, e.x1, e.y1]}  # the model's own box, kept so crops can be re-snapped for free
                    for e in out.exhibits if abs((e.x1 - e.x0) * (e.y1 - e.y0)) >= 0.01]  # ignore specks

        found = await asyncio.gather(*(one(p) for p in range(1, pages + 1)))
        items = [{"n": k, **e} for k, e in enumerate((e for page in found for e in page), 1)]
        own = meter.steps[start:]
        result = {"case_id": cid, "model": meter.model, "pages": pages, "exhibits": items,
                  "usage": {"calls": len(own), "usd": round(sum(x["usd"] for x in own), 6),
                            "input": sum(x["input"] for x in own), "output": sum(x["output"] for x in own)}}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(cid).write_text(json.dumps(result, indent=1), encoding="utf-8")
        for old in CACHE_DIR.glob(f"{cid}-x*.png"):  # crops from an earlier run are stale now
            old.unlink(missing_ok=True)
        return result


def exhibit(cid: str, n: int) -> dict:
    data = cached(cid)
    hit = next((e for e in (data or {}).get("exhibits", []) if e["n"] == n), None)
    if hit is None:
        raise KeyError(n)
    return hit


def crop_png(cid: str, n: int, size: str = "full") -> bytes:
    """One exhibit as a PNG, cropped from its page (cached like page images)."""
    if size not in casebook.SCALES:
        raise KeyError(size)
    e = exhibit(cid, n)
    out = CACHE_DIR / f"{cid}-x{n}-{size}.png"
    if out.exists():
        return out.read_bytes()
    path = casebook.path_of(cid)
    with casebook._PDFIUM:
        if out.exists():
            return out.read_bytes()
        pdf = pdfium.PdfDocument(str(path))
        try:
            page = pdf[e["page"] - 1]
            w, h = page.get_size()
            l, b, r, t = e["crop"]
            # A crop is a fraction of a page, so render it sharper than whole pages: about 2.2x for the candidate's
            # screen, about 1x for the interviewer's thumbnail.
            scale = {"full": 2.24, "thumb": 1.0}[size]
            bitmap = page.render(scale=scale, crop=(l, b, w - r, h - t), rev_byteorder=True)
            data = casebook._png(bitmap.width, bitmap.height, bytes(bitmap.buffer), bitmap.stride, bitmap.n_channels)
        finally:
            pdf.close()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(out)
    return data
