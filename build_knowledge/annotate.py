"""Step 1 of the knowledge build: read every case PDF and record what it's made of.

Run from the case_generator folder:

    .venv/Scripts/python build_knowledge/annotate.py

Reads `Project/Cases/*.pdf`, extracts the text, and asks the model to describe each
case's anatomy (type, difficulty drivers, structure, exhibits, math, key insight) in
its own words. Results go to build_knowledge/work/annotations.jsonl, one line per case.
Already-annotated cases are skipped, so the script can be re-run after a failure.

The case text itself stays in work/ and is never shipped with the app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pypdf import PdfReader

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
logging.getLogger("pypdf").setLevel(logging.ERROR)

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent
CASES_DIR = APP_ROOT.parent / "Cases"
WORK_DIR = HERE / "work"
TEXT_DIR = WORK_DIR / "text"
OUT_PATH = WORK_DIR / "annotations.jsonl"

load_dotenv(APP_ROOT / ".env")
load_dotenv(APP_ROOT.parent / ".env")
load_dotenv(APP_ROOT.parents[1] / ".env")

MODEL_NAME = os.environ.get("CASEGEN_BUILD_MODEL", "gpt-6-luna")
MAX_CHARS = 24_000
CONCURRENCY = 8

CaseType = Literal[
    "profitability", "market_entry", "market_sizing", "growth_strategy", "m_and_a",
    "private_equity_due_diligence", "pricing", "cost_reduction", "operations",
    "new_product_launch", "investment_decision", "competitive_response", "turnaround",
    "public_sector_or_nonprofit", "organization_or_people", "other",
]


class CaseAnnotation(BaseModel):
    case_type: CaseType
    secondary_types: list[CaseType] = Field(default_factory=list)
    industry: str = Field(description="Short industry label, e.g. 'airlines', 'consumer packaged goods', 'hospitals'.")
    format: Literal["interviewer_led", "candidate_led", "mixed"]
    printed_difficulty: str | None = Field(None, description="Difficulty exactly as labelled by the casebook, if any (e.g. 'Hard', 'Quant: Medium'); else null.")
    assessed_difficulty: int = Field(ge=1, le=5, description="1 = warm-up, 2 = easy, 3 = medium, 4 = hard, 5 = exceptionally demanding final-round case.")
    difficulty_drivers: list[str] = Field(description="What makes it as hard (or easy) as it is, in your own words. 2-5 short items.")
    num_questions: int = Field(description="Number of distinct questions/sections the interviewer asks after the prompt.")
    num_exhibits: int
    exhibit_kinds: list[str] = Field(description="e.g. table, bar chart, line chart, pie, waterfall, map, text handout.")
    quant_steps: int = Field(description="Approximate number of arithmetic steps in the full worked solution.")
    math_concepts: list[str] = Field(description="e.g. breakeven, payback, NPV/perpetuity, CAGR, weighted average, market sizing, margin analysis, capacity constraint, elasticity, cannibalization.")
    has_distractor_data: bool = Field(description="Does an exhibit or the prompt include information the candidate should notice is irrelevant?")
    has_pivot_or_curveball: bool = Field(description="Does the case change direction, add a new constraint mid-way, or contain a counter-intuitive twist?")
    question_sequence: list[str] = Field(description="Ordered section types, from: framework, clarifying, brainstorm, market_sizing, quant, exhibit_read, pivot, synthesis.")
    situation_archetype: str = Field(description="The client situation, abstracted and in your own words, with no company names: e.g. 'regional airline with falling margins weighs charging for in-flight food'.")
    analytical_engine: str = Field(description="One sentence on the core analysis the solution runs, abstracted.")
    key_insight_pattern: str = Field(description="One sentence on the 'aha' a strong candidate must find, abstracted.")
    what_makes_it_good: str = Field(description="One sentence on what makes this a realistic MBB-style case (or its main weakness).")
    interviewer_style: str = Field(description="How the guide supports the interviewer: hints, pushback, what-good-looks-like notes, rubric, etc. One sentence.")


INSTRUCTIONS = """You are an MBB case-interview coach cataloguing a library of practice cases.
You'll be given the extracted text of one case (prompt, interviewer guide, exhibits, solutions; charts
may be missing because they were images). Describe the case's anatomy so another coach could write NEW
cases with the same qualities. Rules:
- Write everything in your own words. Do NOT copy sentences from the case, and do NOT include company,
  person, or school names in the abstracted fields.
- Be precise about counts (questions, exhibits, quant steps); estimate if text is garbled.
- Judge difficulty against real MBB first- and final-round interviews."""


def extract_text(pdf: Path) -> str:
    reader = PdfReader(pdf)
    parts = []
    for i, page in enumerate(reader.pages, 1):
        parts.append(f"--- page {i} ---\n{page.extract_text() or ''}")
    return "\n".join(parts)


def build_agent() -> Agent[None, CaseAnnotation]:
    client = AsyncOpenAI(
        api_key="unused-openai-key",
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": os.environ["PORTKEY_API_KEY"]},
        timeout=180.0,
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    return Agent(model, output_type=CaseAnnotation, instructions=INSTRUCTIONS, retries=2)


async def main() -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT_PATH.exists():
        done = {json.loads(l)["source"] for l in OUT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()}
    pdfs = sorted(p for p in CASES_DIR.glob("*.pdf") if p.stem not in done)
    print(f"{len(done)} already annotated, {len(pdfs)} to go", flush=True)

    agent = build_agent()
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    failures: list[str] = []

    async def one(pdf: Path) -> None:
        text_path = TEXT_DIR / f"{pdf.stem}.txt"
        if not text_path.exists():
            text_path.write_text(extract_text(pdf), encoding="utf-8")
        text = text_path.read_text(encoding="utf-8")[:MAX_CHARS]
        source_book, _, case_name = pdf.stem.partition(" ")
        async with sem:
            try:
                result = await agent.run(f"Case: {case_name}\n\n{text}")
            except Exception as exc:  # keep going; re-run picks up failures
                failures.append(f"{pdf.stem}: {exc}")
                return
        row = {"source": pdf.stem, "casebook": source_book, **result.output.model_dump()}
        async with lock:
            with OUT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n = sum(1 for _ in OUT_PATH.open(encoding="utf-8"))
            if n % 25 == 0:
                print(f"  {n} annotated", flush=True)

    await asyncio.gather(*(one(p) for p in pdfs))
    total = sum(1 for _ in OUT_PATH.open(encoding="utf-8")) if OUT_PATH.exists() else 0
    print(f"done: {total} annotations, {len(failures)} failures", flush=True)
    for f in failures:
        print("  FAILED", f, flush=True)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
