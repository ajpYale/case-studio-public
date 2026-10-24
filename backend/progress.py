"""Practice progress over time: every scored interview with Handsome Dan, grouped into four skills, with
trends and a suggested next case.

Each case's rubric names its own dimensions, so scores are mapped onto four standard skills by
keyword. "Clear my progress" moves the scored interviews into an archive folder instead of deleting
them, and "Undo" puts the most recent clear back. Interviews still in progress are never touched.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import generator
import interviewer

WIPES_DIR = generator.BACKEND_DIR / "progress_wipes"  # git-ignored, like the interviews themselves
SKILLS = [
    ("Structuring", r"struct|framework|approach|organi|scop"),
    ("Quant", r"quant|math|numer|calcul|accura|analy|estimat"),
    ("Business judgment", r"judg|insight|business|commercial|creativ|brainstorm|hypoth|strateg"),
    ("Communication", r"commun|synth|recommend|present|clar|polish|storyl"),
]
# The kinds of case that exercise each skill most, for the "practice next" suggestion.
PRACTICE_FOR = {
    "Structuring": ["market_entry", "growth_strategy", "new_product_launch"],
    "Quant": ["profitability", "market_sizing", "investment_decision"],
    "Business judgment": ["m_and_a", "competitive_response", "growth_strategy"],
    "Communication": ["growth_strategy", "profitability", "market_entry"],
}
LEVELS = ["easy", "medium", "hard", "instant_offer"]
# A case's own case_type is free text ("Profitability diagnosis"); map it onto the app's case types.
CASE_TYPES = [
    ("m_and_a", r"m&a|merger|acqui"), ("private_equity_due_diligence", r"private equity|due diligence|pe"),
    ("market_entry", r"entry|enter"), ("market_sizing", r"sizing|market size"), ("new_product_launch", r"launch|new product"),
    ("turnaround", r"turnaround"), ("competitive_response", r"compet"), ("pricing", r"pric"),
    ("cost_reduction", r"cost"), ("growth_strategy", r"growth"), ("investment_decision", r"invest|capital|capex"),
    ("operations", r"operat|supply|capacity"), ("public_sector_or_nonprofit", r"public|nonprofit|government"),
    ("profitability", r"profit"),
]


def case_type_key(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower().replace("_", " ")
    return next((key for key, pattern in CASE_TYPES if re.search(pattern, t)), "other")


def skill_of(dimension: str) -> str:
    return next((name for name, pattern in SKILLS if re.search(pattern, dimension, re.I)), "Other")


def _sessions_dir() -> Path:
    return interviewer.SESSIONS_DIR


def history() -> list[dict]:
    """Every scored interview, oldest first."""
    out = []
    for f in _sessions_dir().glob("*.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        card = s.get("scorecard")
        if not card:
            continue
        case = generator.load_case(s["case_id"]) or {}
        draft = case.get("draft") or {}
        skills: dict[str, list[int]] = {}
        for d in card.get("dimensions", []):
            skills.setdefault(skill_of(d["dimension"]), []).append(d["score"])
        out.append({"id": s["id"], "at": s.get("created"), "case_id": s["case_id"],
                    "title": draft.get("title", "(a deleted case)"), "difficulty": draft.get("difficulty"),
                    "case_type": case_type_key(draft.get("case_type")), "overall": card["overall"], "verdict": card["verdict"],
                    "skills": {k: round(sum(v) / len(v), 2) for k, v in skills.items()}})
    return sorted(out, key=lambda e: e["at"] or "")


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def summary() -> dict:
    h = history()
    out = {"count": len(h), "interviews": h[-30:], "skills": [], "by_type": [], "suggestion": None,
           "undo": last_wipe()}
    if not h:
        return out
    out["overall_avg"] = _avg([e["overall"] for e in h])
    recent, earlier = h[-3:], h[:-3]
    out["overall_recent"] = _avg([e["overall"] for e in recent])
    out["overall_earlier"] = _avg([e["overall"] for e in earlier])
    for name, _ in SKILLS:
        scores = [e["skills"][name] for e in h if name in e["skills"]]
        if not scores:
            continue
        out["skills"].append({"skill": name, "avg": _avg(scores), "recent": _avg(scores[-3:]),
                              "earlier": _avg(scores[:-3]), "n": len(scores)})
    by_type: dict[str, list[int]] = {}
    for e in h:
        if e["case_type"]:
            by_type.setdefault(e["case_type"], []).append(e["overall"])
    out["by_type"] = sorted(({"case_type": t, "n": len(v), "avg": _avg(v)} for t, v in by_type.items()),
                            key=lambda r: -r["n"])
    out["suggestion"] = _suggest(h, out["skills"])
    return out


def _suggest(h: list[dict], skills: list[dict]) -> dict | None:
    """Next case: aimed at the weakest recent skill, at a level that matches recent results."""
    if not skills:
        return None
    weakest = min(skills, key=lambda s: (s["recent"], s["avg"]))
    levels = [e["difficulty"] for e in h[-5:] if e["difficulty"] in LEVELS]
    level = max(set(levels), key=levels.count) if levels else "medium"
    recent = _avg([e["overall"] for e in h[-3:]]) or 3
    if recent >= 4 and level != LEVELS[-1]:
        level, why_level = LEVELS[LEVELS.index(level) + 1], "you've been scoring well, so step up a level"
    elif recent <= 2 and level != LEVELS[0]:
        level, why_level = LEVELS[LEVELS.index(level) - 1], "a level down to rebuild the basics"
    else:
        why_level = "the level you've been practicing"
    done = {e["case_type"] for e in h}
    options = PRACTICE_FOR.get(weakest["skill"], ["profitability"])
    case_type = next((t for t in options if t not in done), options[0])
    return {"skill": weakest["skill"], "skill_avg": weakest["recent"], "difficulty": level, "case_type": case_type,
            "why": f"{weakest['skill']} is your lowest recent score ({weakest['recent']:.1f} of 5); {why_level}."}


# ------------------------------------------------------------------ clearing progress, and undoing it

def last_wipe() -> dict | None:
    wipes = sorted(p for p in WIPES_DIR.glob("*") if p.is_dir()) if WIPES_DIR.is_dir() else []
    if not wipes:
        return None
    meta = wipes[-1] / "wipe.json"
    info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    return {"id": wipes[-1].name, "at": info.get("at"), "count": len(list(wipes[-1].glob("*.json"))) - meta.exists()}


def wipe() -> dict:
    """Move every scored interview out of the progress history (into an archive folder)."""
    scored = []
    for f in _sessions_dir().glob("*.json"):
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("scorecard"):
                scored.append(f)
        except (OSError, json.JSONDecodeError):
            continue
    if not scored:
        raise ValueError("There's no progress to clear.")
    # Folder names sort in time order (microseconds included), so "the last clear" is always the newest one.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    newest = last_wipe()
    if newest and newest["id"] >= stamp:  # same microsecond, or a clock step back: still sort after it
        stamp = newest["id"] + "-1"
    target = WIPES_DIR / stamp
    target.mkdir(parents=True)
    for f in scored:
        shutil.move(str(f), target / f.name)
        interviewer.SESSIONS.pop(f.stem, None)
    (target / "wipe.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    return {"cleared": len(scored), "undo": last_wipe()}


def undo_wipe() -> dict:
    """Put the most recently cleared interviews back."""
    info = last_wipe()
    if not info:
        raise ValueError("There's no cleared progress to bring back.")
    source = WIPES_DIR / info["id"]
    _sessions_dir().mkdir(exist_ok=True)
    restored = 0
    for f in source.glob("*.json"):
        if f.name == "wipe.json":
            continue
        if not (_sessions_dir() / f.name).exists():
            shutil.move(str(f), _sessions_dir() / f.name)
            restored += 1
    shutil.rmtree(source, ignore_errors=True)
    return {"restored": restored, "undo": last_wipe()}
