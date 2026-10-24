"""Convert a casebook case (a PDF) into a full McKennel case: interviewer guide, handouts, worked math,
quality check, live mode and practice with Handsome Dan, just like a generated case.

Steps: read the PDF's text, find its exhibits (exhibits.py), have Luna convert everything into the
case format faithfully (exhibits re-entered as the app's own tables and charts, with the original
crops kept beside them), check every number with up to two fix rounds, then one independent review
for the Quality tab. Converted cases live in the local library only (git-ignored), like the casebooks.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import pypdfium2 as pdfium
from pydantic_ai import Agent, BinaryContent

import casebook
import exhibits
import generator
import verify
from models import CaseDraft, Exhibit, GenerateRequest

MAX_USD_PER_IMPORT = 0.50
FIX_ROUNDS = 2
PAGE_CHARS = 6000      # per page of casebook text sent to the converter
TOTAL_CHARS = 60000


@lru_cache(maxsize=2)
def _agent(model: str) -> Agent:
    # The number rules are the writer's; the "make it original and round" rules are not (this is a conversion).
    number_rules = generator._prompt("writer.md").split("# Interview-ready math")[0]
    return Agent(generator._model(model), output_type=CaseDraft, retries=2,
                 instructions=generator._prompt("importer.md") + "\n\n" + number_rules,
                 model_settings=generator._settings("importer"))


def assets_dir():
    return generator.GENERATED_DIR / "assets"


def converted_from(cid: str) -> str | None:
    """The library case already converted from this casebook case, if any."""
    for f in sorted(generator.GENERATED_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (d.get("source") or {}).get("casebook_id") == cid:
            return d["id"]
    return None


def converted_map() -> dict[str, str]:
    out = {}
    for f in generator.GENERATED_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        src = d.get("source") or {}
        if src.get("casebook_id"):
            out[src["casebook_id"]] = d["id"]
    return out


def _page_texts(cid: str) -> list[str]:
    path = casebook.path_of(cid)
    with casebook._PDFIUM:
        pdf = pdfium.PdfDocument(str(path))
        try:
            texts = [pdf[i].get_textpage().get_text_range().replace("\r", "").strip()[:PAGE_CHARS] for i in range(len(pdf))]
        finally:
            pdf.close()
    out, used = [], 0
    for i, t in enumerate(texts, 1):
        t = t[: max(0, TOTAL_CHARS - used)]
        used += len(t)
        out.append(f"--- Page {i} ---\n{t}")
    return out


async def convert(cid: str, progress, meter: generator.Meter | None = None) -> str:
    """Convert one casebook case; returns the new library case id."""
    meta = casebook.meta(cid)
    difficulty = meta.get("level") or "medium"
    req = GenerateRequest(difficulty=difficulty)
    meter = meter or generator.Meter(generator.LUNA_MODEL, MAX_USD_PER_IMPORT)
    agent = _agent(meter.model)
    level = generator._level_text(difficulty)

    await progress("Finding the exhibits")
    found = exhibits.cached(cid) or await exhibits.find(cid, meter=meter)  # its cost shows on the job card
    crops = [exhibits.crop_png(cid, e["n"], "full") for e in found["exhibits"]]

    await progress("Reading the casebook case")
    pages = _page_texts(cid)
    listing = "\n".join(f"Image {e['n']}: \"{e['title']}\" ({e['kind']}, page {e['page']})" for e in found["exhibits"])
    msg = [
        f"{level}\n\nConvert this casebook case: \"{meta['title']}\" ({meta['school']} casebook {meta['year']}). "
        f"Difficulty: {generator.LEVEL_LABEL[difficulty]} (final).\n\n"
        + (f"Its exhibits, as the images that follow, in order (your ex1..ex{len(crops)}):\n{listing}\n\n" if crops
           else "This case has no exhibits: return an empty exhibits list unless its text includes a written handout.\n\n")
        + "The casebook case, page by page:\n\n" + "\n\n".join(pages),
        *(BinaryContent(data=png, media_type="image/png") for png in crops),
    ]
    await progress("Converting it into a full case")
    draft = await generator._ask(meter, "importer", "Convert the casebook case", msg, agent=agent)
    draft.difficulty = difficulty

    await progress("Checking every number")
    history: list[dict] = []
    fixes = 0
    best = None  # (number of serious issues, draft): a fix round that makes things worse is thrown away
    for round_no in range(FIX_ROUNDS + 1):
        vals, issues = verify.check(draft, design=False)  # the casebook's case as it is: no size or style rules
        serious = [i for i in issues if i.severity in ("blocker", "major")]
        if best is None or len(serious) < best[0]:
            best = (len(serious), draft)
        if not serious or round_no == FIX_ROUNDS:
            break
        history.append({"step": "number check", "issues": [i.as_dict() for i in serious]})
        await progress(f"Fixing {len(serious)} consistency issue{'s' if len(serious) != 1 else ''} in the math")
        draft = await generator._fix(draft, [f"[{i.severity}] {i.where}: {i.problem}" for i in issues], req, level, meter,
                                     f"Fix {len(serious)} number-check issue{'s' if len(serious) != 1 else ''}", agent=agent)
        draft.difficulty = difficulty
        fixes += 1
    draft = best[1]
    pairs = await _place_unclaimed_exhibits(draft, found["exhibits"], crops, meter)
    vals, issues = verify.check(draft, design=False)

    await progress("Independent review")
    rendered = verify.render(draft, vals)
    review = await generator._ask(meter, "reviewer", "Independent review",
                                  f"{level}\n\nThis case was converted from a club casebook. Audit it:\n\n"
                                  f"{generator._review_text(rendered)}")
    remaining = [i.as_dict() for i in issues]
    status = "verified"
    if any(i["severity"] in ("blocker", "major") for i in remaining):
        status = "needs_attention"
    elif any(i.severity in ("blocker", "major") for i in review.issues):
        status = "review_flags"

    await progress("Saving it to BAIN")
    case_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    images = {}
    assets_dir().mkdir(parents=True, exist_ok=True)
    for eid, k in pairs.items():  # each casebook crop goes with its exhibit
        name = f"{case_id}-{eid}.png"
        (assets_dir() / name).write_bytes(crops[k - 1])
        images[eid] = name
    record = {
        "id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": req.model_dump(),
        "source": {"kind": "casebook", "casebook_id": cid, "title": meta["title"], "school": meta["school"],
                   "year": meta["year"]},
        "images": images,
        "draft": draft.model_dump(),
        "rendered": rendered,
        "quality": {"status": status, "checks": remaining, "reviews": [review.model_dump()], "fix_rounds": fixes,
                    "history": history, "model": meter.model, "engine": "luna", "converted": True},
        "usage": meter.summary(),
    }
    (generator.GENERATED_DIR / f"{case_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    return case_id


_TRANSCRIBE = ("Transcribe this consulting-case exhibit as plain text: its title, then its data as short lines or "
               "'label: value' pairs, with every number exactly as printed. No commentary.")


@lru_cache(maxsize=2)
def _transcriber(model: str) -> Agent:
    return Agent(generator._model(model), output_type=str, retries=2, instructions=_TRANSCRIBE,
                 model_settings=generator._settings("transcribe"))


async def _place_unclaimed_exhibits(draft: CaseDraft, found: list[dict], crops: list[bytes], meter) -> dict[str, int]:
    """Pair each casebook exhibit with the case's exhibits. Any the converter merged or dropped is added as its
    own exhibit (its image, plus a text transcription for the interviewer and reviewer agents), handed out in
    the same part as its nearest neighbour, so every casebook exhibit reaches the candidate."""
    pairs = match_images(draft, found)
    claimed = set(pairs.values())
    hands = {eid: sec for sec in draft.sections for eid in sec.exhibit_ids}
    for f in found:
        if f["n"] in claimed:
            continue
        body = await generator._ask(meter, "importer", f"Transcribe exhibit {f['n']}", [
            f"Exhibit title: {f['title']}", BinaryContent(data=crops[f["n"] - 1], media_type="image/png")],
            agent=_transcriber(meter.model))
        used = {e.id for e in draft.exhibits}
        eid = next(f"ex{k}" for k in range(1, 100) if f"ex{k}" not in used)
        draft.exhibits.append(Exhibit(id=eid, title=f["title"], kind="text", columns=["Item"], rows=[],
                                      value_unit="other", text_body=str(body).strip()[:3000]))
        near = sorted(((abs(n - f["n"]), e) for e, n in pairs.items() if e in hands), key=lambda t: t[0])
        section = hands[near[0][1]] if near else next((s for s in reversed(draft.sections) if s.exhibit_ids),
                                                      draft.sections[min(1, len(draft.sections) - 1)])
        section.exhibit_ids.append(eid)
        pairs[eid] = f["n"]
    # Number the exhibits in the casebook's order (Exhibit 3 stays Exhibit 3); any without an image go last.
    draft.exhibits.sort(key=lambda e: pairs.get(e.id, 10_000))
    return pairs


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in {"exhibit", "the", "and", "of", "by", "in"}}


def match_images(draft: CaseDraft, found: list[dict]) -> dict[str, int]:
    """Pair each found exhibit (crop n) with the case exhibit whose title matches it best, falling back on
    order. A crop is only used once, and an exhibit that matches nothing gets no image."""
    pairs: dict[str, int] = {}
    free = list(range(len(draft.exhibits)))
    aligned = len(draft.exhibits) == len(found)  # same count: the converter kept them all, so order is meaningful
    for k, f in enumerate(found, 1):
        want = _words(f["title"])
        scored = sorted(((len(want & _words(draft.exhibits[i].title)) / max(1, len(want)), -abs(i - (k - 1)), i)
                         for i in free), reverse=True)
        if not scored:
            break
        score, _, i = scored[0]
        if score < 0.34:
            if not (aligned and (k - 1) in free):
                continue  # no exhibit is this one: it gets its own (see _place_unclaimed_exhibits)
            i = k - 1    # titles reworded, but the counts line up: go by position
        pairs[draft.exhibits[i].id] = f["n"]
        free.remove(i)
    return pairs


def image_path(case: dict, eid: str):
    name = (case.get("images") or {}).get(eid)
    if not name:
        raise KeyError(eid)
    path = assets_dir() / name
    if not path.exists():
        raise KeyError(eid)
    return path
