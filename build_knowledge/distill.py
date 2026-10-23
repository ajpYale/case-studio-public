"""Step 2 of the knowledge build: condense the annotations into the app's knowledge pack.

Run from the case_generator folder after annotate.py:

    .venv/Scripts/python build_knowledge/distill.py

Writes backend/knowledge/knowledge_pack.json, which is all the app needs at run time:
- per-difficulty statistics and calibration notes,
- an archetype library (abstracted situation / analytical engine / insight per case — no
  casebook text, no client names),
- the industry groups and a house-style guide.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent
ANNOTATIONS = HERE / "work" / "annotations.jsonl"
OUT = APP_ROOT / "backend" / "knowledge" / "knowledge_pack.json"

load_dotenv(APP_ROOT / ".env")
load_dotenv(APP_ROOT.parent / ".env")
load_dotenv(APP_ROOT.parents[1] / ".env")
MODEL_NAME = os.environ.get("CASEGEN_BUILD_MODEL", "gpt-6-luna")

INDUSTRY_GROUPS = [
    "Airlines & travel", "Automotive & transportation", "Banking & financial services", "Insurance",
    "Consumer goods", "Retail & e-commerce", "Restaurants & food service", "Healthcare providers",
    "Pharma, biotech & medical devices", "Technology & software", "Telecom & media",
    "Energy, utilities & natural resources", "Industrial & manufacturing", "Hospitality, leisure & sports",
    "Education", "Public sector & nonprofit", "Private equity & investing", "Agriculture & food production",
    "Real estate & construction", "Logistics & supply chain",
]
LEVEL_OF = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "instant_offer"}


class IndustryMap(BaseModel):
    mapping: dict[str, str]


class Notes(BaseModel):
    notes: str


def model() -> OpenAIResponsesModel:
    client = AsyncOpenAI(
        api_key="unused-openai-key",
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": os.environ["PORTKEY_API_KEY"]},
        timeout=300.0,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def q(values: list[float]) -> str:
    if not values:
        return "n/a"
    values = sorted(values)
    med = statistics.median(values)
    lo, hi = values[len(values) // 4], values[(3 * len(values)) // 4]
    return f"{med:g} (typical {lo:g}-{hi:g})"


def level_stats(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "cases": n,
        "questions": q([r["num_questions"] for r in rows]),
        "exhibits": q([r["num_exhibits"] for r in rows]),
        "quant_steps": q([r["quant_steps"] for r in rows]),
        "share_with_distractor_data": f"{round(100 * sum(r['has_distractor_data'] for r in rows) / max(n, 1))}%",
        "share_with_pivot": f"{round(100 * sum(r['has_pivot_or_curveball'] for r in rows) / max(n, 1))}%",
        "share_candidate_led": f"{round(100 * sum(r['format'] != 'interviewer_led' for r in rows) / max(n, 1))}%",
        "common_math": ", ".join(m for m, _ in Counter(c.lower() for r in rows for c in r["math_concepts"]).most_common(8)),
    }


async def main() -> None:
    rows = [json.loads(l) for l in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} annotations")
    m = model()
    rng = random.Random(409)

    # 1. Industry groups.
    industries = sorted({r["industry"] for r in rows})
    mapper = Agent(m, output_type=IndustryMap, instructions=(
        "Map each industry label to exactly one of these groups (use the group text verbatim): "
        + "; ".join(INDUSTRY_GROUPS)))
    mapping = (await mapper.run("Labels:\n" + "\n".join(industries))).output.mapping
    for r in rows:
        g = mapping.get(r["industry"])
        r["industry_group"] = g if g in INDUSTRY_GROUPS else "Industrial & manufacturing"

    # 2. Levels. The hardest hard cases (pivot + distractors + heavy math) also inform instant offer.
    p75_steps = sorted(r["quant_steps"] for r in rows)[(3 * len(rows)) // 4]
    for r in rows:
        r["level"] = LEVEL_OF[r["assessed_difficulty"]]
        r["instant_offer_grade"] = r["level"] == "instant_offer" or (
            r["level"] == "hard" and r["has_pivot_or_curveball"] and r["has_distractor_data"] and r["quant_steps"] >= p75_steps)

    by_level = {lv: [r for r in rows if r["level"] == lv] for lv in ("easy", "medium", "hard")}
    by_level["instant_offer"] = [r for r in rows if r["instant_offer_grade"]]

    # 3. Calibration notes per level, written from that level's difficulty drivers.
    calibrator = Agent(m, output_type=Notes, instructions=(
        "You coach MBB case writers. From descriptions of what made real practice cases easy or hard, write "
        "6-10 crisp bullet points that describe what cases at this level are like and how to build one. "
        "Your own words; no case or company names."))

    async def calibrate(level: str) -> str:
        sample = rng.sample(by_level[level], min(40, len(by_level[level])))
        drivers = "\n".join(f"- {'; '.join(r['difficulty_drivers'])}" for r in sample)
        extra = (" This is the 'instant offer' tier: the hardest cases in the library. Describe what makes them "
                 "brutal and what would make a case harder still while staying fair.") if level == "instant_offer" else ""
        return (await calibrator.run(f"Level: {level}.{extra}\nDifficulty drivers:\n{drivers}")).output.notes

    # 4. House style, from what made cases good and how their guides support the interviewer.
    stylist = Agent(m, output_type=Notes, instructions=(
        "You edit a consulting-club casebook. From notes on what made real cases realistic and how their "
        "interviewer guides were written, write a house-style guide of 10-14 bullets for writing new cases "
        "(prompt, clarifying info, exhibits, interviewer guidance, recommendation). Your own words; no names."))
    style_sample = rng.sample(rows, min(80, len(rows)))
    style_input = "\n".join(f"- Good: {r['what_makes_it_good']} | Guide: {r['interviewer_style']}" for r in style_sample)

    notes = await asyncio.gather(*(calibrate(lv) for lv in by_level), stylist.run(style_input))
    level_notes = dict(zip(by_level, notes[:4]))
    style_guide = notes[4].output.notes

    keep = ["level", "instant_offer_grade", "case_type", "secondary_types", "industry_group", "format",
            "situation_archetype", "analytical_engine", "key_insight_pattern", "math_concepts", "num_exhibits",
            "exhibit_kinds", "quant_steps", "has_distractor_data", "has_pivot_or_curveball", "question_sequence"]
    pack = {
        "version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "built_from": {"cases": len(rows), "casebooks": len({r["casebook"] for r in rows})},
        "levels": {lv: {"stats": level_stats(by_level[lv]), "calibration_notes": level_notes[lv]} for lv in by_level},
        "case_types": dict(Counter(r["case_type"] for r in rows).most_common()),
        "industries": [g for g, _ in Counter(r["industry_group"] for r in rows).most_common()],
        "style_guide": style_guide,
        "archetypes": [{k: r[k] for k in keep} for r in rows],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    for lv, d in pack["levels"].items():
        print(lv, d["stats"])


if __name__ == "__main__":
    asyncio.run(main())
