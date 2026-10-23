"""Collect the test-run log for the report: every run's outcome and measured tokens and cost.

Reads the run summaries written by the UI driver (docs/runs/*.json) and the saved cases they
point to, and writes docs/run_log.json. Run from anywhere: python docs/collect_runs.py
"""

from __future__ import annotations

import json
from pathlib import Path

DOCS = Path(__file__).resolve().parent
GENERATED = DOCS.parent / "backend" / "generated"
FLAGGED = DOCS.parents[1] / "Flagged Cases"


def load_case(case_id: str) -> dict | None:
    for folder in (GENERATED, FLAGGED):
        f = folder / f"{case_id}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def main() -> None:
    runs = []
    for f in sorted((DOCS / "runs").glob("run*.json")):
        try:
            raw = f.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252")  # early runs printed in the Windows code page
            r = json.loads(text)
        except json.JSONDecodeError:
            continue
        row = {k: r.get(k) for k in ("label", "difficulty", "engine", "status", "minutes", "error", "case_id", "title",
                                     "quality", "fix_rounds", "calls", "input", "cached", "output", "usd", "note",
                                     "prompt_version")}
        case = load_case(r["case_id"]) if r.get("case_id") else None
        if case and case.get("usage"):
            u = case["usage"]
            row["steps"] = [{k: s[k] for k in ("step", "role", "input", "cached", "output", "seconds", "usd")} for s in u["steps"]]
        audit = DOCS / "runs" / f"cross_audit_{r.get('case_id')}.json"
        if audit.exists():
            a = json.loads(audit.read_text(encoding="utf-8"))
            sev = [i["severity"] for i in a["issues"]]
            row["audit"] = {"model": a["audit_model"], "blockers": sev.count("blocker"), "majors": sev.count("major"),
                            "minors": sev.count("minor"), "usd": a["usage"]["usd"],
                            "major_issues": [i["problem"] for i in a["issues"] if i["severity"] != "minor"]}
        runs.append(row)
    out = DOCS / "run_log.json"
    out.write_text(json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in runs:
        print(f"{r['label']:<24} {r['status']:<6} {str(r.get('quality')):<14} fixes={r.get('fix_rounds')} "
              f"calls={r.get('calls')} usd={r.get('usd')} min={r.get('minutes')} audit={r.get('audit', {}).get('majors')}")


if __name__ == "__main__":
    main()
