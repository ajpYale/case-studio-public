"""The solver check: can a strong candidate reach the answer key from what the candidate is given?

A solver agent gets only the candidate's side of the case (prompt, clarifying answers, facts the
interviewer shares, assumptions the interviewer confirms, exhibits) and the list of results to
calculate, never the key. Code then compares its answers with the key. A miss usually means the
key relies on a fact the candidate never gets, or a question that can be read two ways, which is
the kind of premise gap the model reviewers kept missing.

Everything here is plain code; the model call itself happens in generator.generate.
"""

from __future__ import annotations

import verify
from models import CaseDraft, SolverOutput

UNIT_TEXT = {
    "usd": "dollars", "usd_k": "thousands of dollars", "usd_m": "millions of dollars",
    "usd_b": "billions of dollars", "pct": "a fraction (0.25 means 25%)", "count": "a plain count",
    "count_k": "thousands", "count_m": "millions", "years": "years", "months": "months", "days": "days",
    "hours": "hours", "minutes": "minutes", "multiple": "an 'x' multiple", "ratio": "a plain ratio",
    "per_unit_usd": "dollars per unit", "other": "the natural unit for the step",
}
TOLERANCE = 0.025  # interview math is done by hand; 2.5% covers sensible rounding


def _exhibit_text(e: dict, number: int) -> list[str]:
    out = [f"Exhibit {number}: {e['title']}" + (f" ({e['subtitle']})" if e.get("subtitle") else "")]
    if e["kind"] == "text":
        out.append(e.get("text_body") or "")
    else:
        out.append(" | ".join(e["columns"]))
        out += [" | ".join([row["label"], *cells]) for row, cells in zip(e["rows"], e["display"])]
    if e.get("footnote"):
        out.append(f"Note: {e['footnote']}")
    return out


def candidate_text(draft: CaseDraft, vals: verify.Values) -> str:
    """The case exactly as the candidate experiences it, with no model answers, worked math or hints."""
    r = verify.render(draft, vals)
    number = {e["id"]: i + 1 for i, e in enumerate(r["exhibits"])}
    by_id = {e["id"]: e for e in r["exhibits"]}
    out = [f"# Case prompt (read aloud by the interviewer)\n{r['prompt']}"]
    if r["clarifying"]:
        out.append("# Answers the interviewer gives to clarifying questions")
        out += [f"- Q: {q['question']}\n  A: {q['answer']}" for q in r["clarifying"]]
    assumptions = [v for v in r["variables"] if v["revealed_in"] == "assumption"]
    if assumptions:
        out.append("# Assumptions the interviewer confirms if you propose them")
        out += [f"- {v['label']}: {v['display']}" for v in assumptions]
    handed: set[str] = set()
    for k, (sec, shown) in enumerate(zip(draft.sections, r["sections"]), 1):
        out.append(f"\n# Part {k}\nInterviewer: {shown['ask']}")
        if shown["info_to_share"]:
            out.append("Facts the interviewer shares if you ask:")
            out += [f"- {t}" for t in shown["info_to_share"]]
        for eid in sec.exhibit_ids:
            if eid in by_id and eid not in handed:
                handed.add(eid)
                out += ["Handed to you:", *_exhibit_text(by_id[eid], number[eid])]
        if sec.calculations:
            out.append("Results to calculate in this part:")
            out += [f"- {c.id}: {c.label} (give it in {UNIT_TEXT.get(c.unit, c.unit)})" for c in sec.calculations]
    return "\n".join(out)


def solve_prompt(draft: CaseDraft, vals: verify.Values) -> str:
    return (candidate_text(draft, vals)
            + "\n\nWork the case as the candidate. Give one answer for every result listed above, in order.")


def _close(got: float, want: float, unit: str) -> bool:
    """Generous on presentation (25 vs 0.25 for a percentage, $1.2M given as 1,200,000, a loss given as a
    positive number): those aren't gaps in the case. Strict on the value itself."""
    tries = [got, got / 100] if unit == "pct" else [got]
    if unit in ("usd", "usd_k", "usd_m", "usd_b", "count", "count_k", "count_m", "per_unit_usd"):
        tries += [got * f for f in (1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9)]
    for t in tries:
        if abs(want) < 1e-9:
            if abs(t) <= 1e-6:
                return True
        elif abs(abs(t) - abs(want)) <= TOLERANCE * abs(want):
            return True
    return False


def compare(out: SolverOutput, draft: CaseDraft, vals: verify.Values) -> dict:
    """Score the solver's answers against the key, one row per calculation."""
    answers = {a.id: a for a in out.answers}
    rows = []
    for sec in draft.sections:
        for c in sec.calculations:
            if c.id not in vals.env:
                continue
            a = answers.get(c.id)
            ok = bool(a and a.value is not None and _close(a.value, vals.env[c.id], c.unit))
            rows.append({
                "section": sec.id, "id": c.id, "label": c.label, "expected": vals.text(c.id),
                "solver": verify.fmt(a.value, c.unit) if a and a.value is not None else None,
                "ok": ok, "working": (a.working if a else "")[:400],
                "missing": (a.missing or None) if a else "no answer given",
            })
    return {"solved": sum(r["ok"] for r in rows), "total": len(rows), "results": rows}


def gaps(result: dict) -> list[dict]:
    """Misses worth acting on. A miss where the solver says nothing was missing is often its own
    slip, but it still goes to the writer, who is told to leave a complete, clear step alone."""
    return [r for r in result["results"] if not r["ok"]]


def problems(misses: list[dict]) -> list[str]:
    """The solver's misses, phrased for the writer's fix step."""
    out = []
    for r in misses:
        said = f"It said: {r['missing']}." if r["missing"] else "It didn't report anything missing."
        got = r["solver"] or "no answer"
        out.append(
            f"[major] {r['section']} calculation {r['id']} ({r['label']}): a solver given only what the candidate "
            f"sees got {got}, but the key says {r['expected']}. {said} Its working: {r['working'] or 'none'}. "
            "If the key relies on a number, fact or assumption the candidate is never given, give it to them (the "
            "prompt, a clarifying answer, a 'share if asked' fact, an exhibit handed out by then, or a variable marked "
            "'assumption'). If the question can be read two ways, make it precise. If the step is already complete and "
            "clear and the solver simply made an arithmetic slip, leave it unchanged.")
    return out


def flagged(result: dict | None) -> int:
    """Final misses where the solver reported missing or ambiguous information: real flags on the case."""
    if not result:
        return 0
    return sum(1 for r in result["results"] if not r["ok"] and r["missing"])
