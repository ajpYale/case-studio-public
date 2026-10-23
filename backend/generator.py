"""The case-writing pipeline: plan -> draft -> check & fix -> review & fix -> save.

Runs entirely from the bundled knowledge pack (knowledge/knowledge_pack.json, or the hand-written
knowledge/starter_pack.json when the full pack isn't present) and the prompts folder; it never reads
the original casebooks.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

import safety
import verify
from models import CaseDraft, CasePlan, GenerateRequest, Review

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

BACKEND_DIR = Path(__file__).resolve().parent
APP_ROOT = BACKEND_DIR.parent
PROMPTS = BACKEND_DIR / "prompts"
KNOWLEDGE_PATH = BACKEND_DIR / "knowledge" / "knowledge_pack.json"
STARTER_PATH = BACKEND_DIR / "knowledge" / "starter_pack.json"
GENERATED_DIR = BACKEND_DIR / "generated"

# Keys: first the repo's own .env, then the folder above it (where the teaching staff keep theirs),
# then the course folder two levels up (the author's own layout). Earlier files win.
load_dotenv(APP_ROOT / ".env")
load_dotenv(APP_ROOT.parent / ".env")
load_dotenv(APP_ROOT.parents[1] / ".env")

# Two engines. "luna" runs every step on the course model and is the default. "strong" is the
# optional upgrade: Terra for Easy-Hard and Sol for Instant Offer, which hold long chains of
# linked finance together far more reliably. Each can be overridden with an environment variable.
LUNA_MODEL = os.environ.get("CASEGEN_MODEL", "gpt-6-luna")
STRONG_MODEL = os.environ.get("CASEGEN_MODEL_STRONG", "gpt-5.6-terra")
STRONG_INSTANT_MODEL = os.environ.get("CASEGEN_MODEL_INSTANT", "gpt-5.6-sol")
ENGINE_LABEL = {"luna": "Luna (course model)", "strong": "Stronger models"}
# Sol is expensive: every run on it must be confirmed by the user (see main.create_case).
EXPENSIVE_MODELS = {"gpt-5.6-sol"}
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


def model_for(difficulty: str, engine: str = "luna") -> str:
    if engine == "strong":
        return STRONG_INSTANT_MODEL if difficulty == "instant_offer" else STRONG_MODEL
    return LUNA_MODEL


def needs_cost_confirmation(difficulty: str, engine: str = "luna") -> bool:
    return model_for(difficulty, engine) in EXPENSIVE_MODELS


# ------------------------------------------------------------------ tokens and money

# USD per 1M tokens. gpt-6-luna: course Lecture 11 (OpenAI standard pricing). GPT-5.6 family:
# course Lecture 1 (input/output); their cached rate isn't published there, so it's assumed to be
# a tenth of input, as with gpt-6-luna.
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50},
    "gpt-5.6-luna": {"input": 0.20, "cached": 0.02, "cache_write": 0.25, "output": 1.20},
    "gpt-5.6-terra": {"input": 2.00, "cached": 0.20, "cache_write": 2.50, "output": 12.00},
    "gpt-5.6-sol": {"input": 5.00, "cached": 0.50, "cache_write": 6.25, "output": 30.00},
}
# Kill-switches. A case stops when it would spend more than this; the server refuses new cases once
# today's spend reaches the daily cap. Both are in USD and can be changed in .env.
MAX_USD_PER_CASE = {"luna": float(os.environ.get("CASEGEN_MAX_USD_PER_CASE_LUNA", "1.00")),
                    "strong": float(os.environ.get("CASEGEN_MAX_USD_PER_CASE_STRONG", "8.00"))}
DAILY_USD_BUDGET = float(os.environ.get("CASEGEN_DAILY_USD_BUDGET", "10.00"))
MAX_TOKENS_PER_CALL = int(os.environ.get("CASEGEN_MAX_TOKENS_PER_CALL", "300000"))
LEDGER_PATH = BACKEND_DIR / "usage_ledger.json"
SECOND_OPINION_MAX_USD = 0.50  # one stronger-model review of a finished case
TRANSIENT_RETRIES = 2  # extra attempts after a gateway 5xx (the OpenAI client already retries twice)


class BudgetExceeded(RuntimeError):
    pass


def cost_usd(model: str, input_tokens: int, cached: int, output: int, cache_write: int = 0) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    uncached = max(input_tokens - cached - cache_write, 0)  # input_tokens includes cached and cache writes
    return (uncached * p["input"] + cached * p["cached"] + cache_write * p["cache_write"] + output * p["output"]) / 1e6


def _ledger() -> dict:
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def spent_today() -> float:
    return _ledger().get(datetime.now().strftime("%Y-%m-%d"), {}).get("usd", 0.0)


def _ledger_add(usd: float, tokens: int) -> None:
    led = _ledger()
    day = led.setdefault(datetime.now().strftime("%Y-%m-%d"), {"usd": 0.0, "tokens": 0, "calls": 0})
    day["usd"] = round(day["usd"] + usd, 6)
    day["tokens"] += tokens
    day["calls"] += 1
    LEDGER_PATH.write_text(json.dumps(led, indent=1), encoding="utf-8")


@dataclass
class Meter:
    """Token and dollar log for one case: one entry per model call, in order."""
    model: str
    budget_usd: float
    steps: list[dict] = field(default_factory=list)
    current: dict | None = None  # the call in flight, for live progress displays

    @property
    def usd(self) -> float:
        return sum(s["usd"] for s in self.steps)

    def summary(self) -> dict:
        tot = {k: sum(s[k] for s in self.steps) for k in ("input", "cached", "output", "requests", "seconds")}
        return {"model": self.model, **tot, "usd": round(self.usd, 6), "calls": len(self.steps), "steps": self.steps,
                "current": self.current}


async def _ask(meter: Meter, role: str, step: str, msg: str, agent: Agent | None = None):
    """Run one agent call under the per-call token cap and the per-case and daily dollar budgets.

    `agent` defaults to the case-writing agent for `role`; the practice interviewer passes its own."""
    if meter.usd >= meter.budget_usd:
        raise BudgetExceeded(f"stopped before '{step}': this case reached its ${meter.budget_usd:.2f} budget")
    if spent_today() >= DAILY_USD_BUDGET:
        raise BudgetExceeded(f"stopped before '{step}': today's ${DAILY_USD_BUDGET:.2f} budget is used up")
    t0 = time.monotonic()
    ag = agent or agents(meter.model)[role]
    meter.current = {"step": step, "role": role, "started": time.time()}
    try:
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                result = await ag.run(
                    msg, usage_limits=UsageLimits(request_limit=4, total_tokens_limit=MAX_TOKENS_PER_CALL))
                break
            except UsageLimitExceeded as exc:
                raise BudgetExceeded(f"'{step}' hit the per-call limit ({exc})") from exc
            except ModelHTTPError as exc:
                # Gateway hiccups (HTTP 5xx) are worth a patient retry; anything else is a real error.
                if exc.status_code < 500 or attempt == TRANSIENT_RETRIES:
                    raise
                meter.current["retry"] = attempt + 1
                await asyncio.sleep(20 * (attempt + 1))
    finally:
        meter.current = None
    u = result.usage() if callable(result.usage) else result.usage
    usd = cost_usd(meter.model, u.input_tokens, u.cache_read_tokens, u.output_tokens, u.cache_write_tokens)
    meter.steps.append({"step": step, "role": role, "input": u.input_tokens, "cached": u.cache_read_tokens,
                        "output": u.output_tokens, "requests": u.requests,
                        "seconds": round(time.monotonic() - t0, 1), "usd": round(usd, 6)})
    _ledger_add(usd, u.input_tokens + u.output_tokens)
    return result.output

MAX_CHECK_ROUNDS = 3   # deterministic check -> fix loops per pass
# Model reviews per case; the last one is a verdict only, never followed by a fix.
# Instant Offer gets one extra round: on Sol each fix landed, but each review dug one layer deeper.
MAX_REVIEWS = {"easy": 3, "medium": 4, "hard": 4, "instant_offer": 5}


def max_reviews_for(req: GenerateRequest) -> int:
    return MAX_REVIEWS[req.difficulty]
MAX_PLAN_FIXES = 2
ARCHETYPES_SHOWN = 6

LEVEL_LABEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "instant_offer": "Instant Offer"}
CASE_TYPE_LABEL = {
    "profitability": "Profitability", "market_entry": "Market entry", "market_sizing": "Market sizing",
    "growth_strategy": "Growth strategy", "m_and_a": "M&A", "private_equity_due_diligence": "PE due diligence",
    "pricing": "Pricing", "cost_reduction": "Cost reduction", "operations": "Operations",
    "new_product_launch": "New product launch", "investment_decision": "Investment decision",
    "competitive_response": "Competitive response", "turnaround": "Turnaround",
    "public_sector_or_nonprofit": "Public sector / nonprofit",
}

Progress = Callable[[str], Awaitable[None]]


# ----------------------------------------------------------------- knowledge pack

@lru_cache(maxsize=1)
def knowledge() -> dict:
    # The full pack is distilled from copyrighted casebooks and isn't in the public repo; the starter
    # pack has generic calibration and no archetypes.
    path = KNOWLEDGE_PATH if KNOWLEDGE_PATH.exists() else STARTER_PATH
    if not path.exists():
        raise RuntimeError(f"No knowledge pack at {KNOWLEDGE_PATH} or {STARTER_PATH}.")
    return json.loads(path.read_text(encoding="utf-8"))


def options() -> dict:
    kp = knowledge()
    return {
        "difficulties": [{"value": k, "label": v} for k, v in LEVEL_LABEL.items()],
        "case_types": [{"value": k, "label": v} for k, v in CASE_TYPE_LABEL.items()],
        "industries": kp["industries"],
        "formats": [{"value": "interviewer_led", "label": "Interviewer-led"},
                    {"value": "candidate_led", "label": "Candidate-led"}],
        "built_from": kp.get("built_from", {"cases": 0, "casebooks": 0, "starter": True}),
        "engines": [{"value": e, "label": ENGINE_LABEL[e], "models": {k: model_for(k, e) for k in LEVEL_LABEL},
                     "confirm_levels": [k for k in LEVEL_LABEL if needs_cost_confirmation(k, e)]}
                    for e in ("luna", "strong")],
        "prices": PRICES,
    }


def pick_archetypes(req: GenerateRequest, rng: random.Random) -> list[dict]:
    pool = knowledge().get("archetypes", [])
    if not pool:
        return []

    def at_level(a: dict) -> bool:
        # The toughest hard cases (pivot + distractors + heavy math) also count as instant-offer grade.
        return a["level"] == req.difficulty or (req.difficulty == "instant_offer" and a.get("instant_offer_grade"))

    level_pool = [a for a in pool if at_level(a)] or pool

    def matches(a: dict) -> bool:
        ok = True
        if req.case_type:
            ok &= req.case_type == a["case_type"] or req.case_type in a.get("secondary_types", [])
        if req.industry:
            ok &= a.get("industry_group") == req.industry
        return ok

    preferred = [a for a in pool if matches(a)] if (req.case_type or req.industry) else []
    same_level = [a for a in preferred if at_level(a)]
    chosen: list[dict] = []
    for bucket in (same_level, preferred, level_pool):
        bucket = list(bucket)
        rng.shuffle(bucket)
        for a in bucket:
            if a not in chosen:
                chosen.append(a)
            if len(chosen) >= ARCHETYPES_SHOWN:
                return chosen
    return chosen


def _archetype_text(archetypes: list[dict]) -> str:
    lines = []
    for i, a in enumerate(archetypes, 1):
        lines.append(
            f"{i}. [{a['level']}, {a['case_type']}, {a['industry_group']}] Situation: {a['situation_archetype']} "
            f"| Engine: {a['analytical_engine']} | Insight: {a['key_insight_pattern']} "
            f"| Math: {', '.join(a['math_concepts'][:5])} | Exhibits: {a['num_exhibits']} "
            f"| Distractors: {'yes' if a['has_distractor_data'] else 'no'} | Pivot: {'yes' if a['has_pivot_or_curveball'] else 'no'}"
        )
    return "\n".join(lines)


def _level_text(difficulty: str) -> str:
    spec = (PROMPTS / "difficulty.md").read_text(encoding="utf-8")
    block = spec.split(f"## {difficulty}\n", 1)[1].split("\n## ", 1)[0]
    cal = knowledge().get("levels", {}).get(difficulty, {})
    stats = cal.get("stats", {})
    notes = cal.get("calibration_notes", "")
    stat_line = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in stats.items()) if stats else ""
    out = f"Difficulty: {LEVEL_LABEL[difficulty]}\n{block.strip()}\nShape: {verify.shape_for(difficulty)}."
    if stat_line:
        out += f"\nIn the reference library, cases at this level have: {stat_line}."
    if notes:
        out += f"\nCalibration notes from the reference library:\n{notes}"
    return out


def _recent_titles(n: int = 15) -> list[str]:
    files = sorted(GENERATED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    titles = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            titles.append(f"{d['draft']['title']} ({d['draft']['industry']}, {d['draft']['case_type']})")
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return titles


# -------------------------------------------------------------------------- agents

@lru_cache(maxsize=4)
def _model(name: str) -> OpenAIResponsesModel:
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to case_generator/.env or the course .env.")
    client = AsyncOpenAI(
        api_key="unused-openai-key",
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
        timeout=420.0,
    )
    # The Responses API: gpt-6-luna on Portkey only accepts structured output (function tools) there.
    return OpenAIResponsesModel(name, provider=OpenAIProvider(openai_client=client))


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _settings(prompt_family: str) -> OpenAIResponsesModelSettings:
    # Planner and writer share one long, unchanging instruction block (and the reviewer has its own),
    # so a shared cache key per family lets repeat calls reuse those tokens at the cached price.
    return OpenAIResponsesModelSettings(max_tokens=32000, openai_prompt_cache_key=f"case-studio-{prompt_family}")


@lru_cache(maxsize=4)
def agents(model_name: str = LUNA_MODEL) -> dict[str, Agent]:
    writer_instr = _prompt("writer.md") + "\n\n" + _prompt("quality_rules.md") + "\n\n# House style from the reference library\n" + knowledge().get("style_guide", "")
    return {
        "planner": Agent(_model(model_name), output_type=CasePlan, instructions=writer_instr, retries=2, model_settings=_settings("writer")),
        "writer": Agent(_model(model_name), output_type=CaseDraft, instructions=writer_instr, retries=2, model_settings=_settings("writer")),
        "reviewer": Agent(
            _model(model_name), output_type=Review, retries=2, model_settings=_settings("reviewer"),
            instructions=_prompt("reviewer.md") + "\n\n" + _prompt("quality_rules.md"),
        ),
    }


# -------------------------------------------------------------------- the pipeline

_REVISION_SUFFIX = re.compile(r"\s*(?:[—–-]\s*|\()\s*(?:corrected|revised|fixed|updated|v\d+)\b.*$", re.I)


def _clean_title(title: str) -> str:
    """Drop editing artifacts like '— Corrected' that a fix round can leave in a title."""
    return _REVISION_SUFFIX.sub("", title).strip() or title


def _request_text(req: GenerateRequest) -> str:
    parts = [f"Difficulty: {LEVEL_LABEL[req.difficulty]}"]
    if req.case_type:
        parts.append(f"Case type: {CASE_TYPE_LABEL.get(req.case_type, req.case_type)}")
    if req.industry:
        parts.append(f"Industry: {req.industry}")
    if req.format:
        parts.append(f"Format: {req.format.replace('_', '-')}")
    if req.notes:
        parts.append(safety.fence_notes(req.notes))
    return "\n".join(parts)


def _review_text(rendered: dict) -> str:
    """The case as an interviewer would read it, with every number filled in."""
    r = rendered
    out = [f"# {r['title']} — {r['client']} ({r['industry']}, {r['case_type']}, {r['difficulty']}, {r['format']})",
           f"## Prompt\n{r['prompt']}", "## Clarifying"]
    out += [f"- Q: {q['question']}\n  A: {q['answer']}" for q in r["clarifying"]]
    out.append("## Answer-key inputs (INTERNAL — the candidate never sees this list; each item's 'revealed in' "
               "says where the candidate gets it, and the prompt/exhibits/share facts below are what they actually see. "
               "Values here are exact.)")
    out += [f"- {v['name']} = {v['display']} ({v['label']}; revealed in {v['revealed_in']}; {v['role']})" for v in r["variables"]]
    out.append("## Framework\n" + "\n".join(f"- {b['name']}: {'; '.join(b['points'])}" for b in r["framework"]))
    for e in r["exhibits"]:
        out.append(f"## Exhibit {e['id']}: {e['title']} ({e['kind']}, column units {', '.join(e.get('units') or [e['value_unit']])})")
        if e.get("subtitle"):
            out.append(f"Subtitle: {e['subtitle']}")
        if e["kind"] == "text":
            out.append(e.get("text_body") or "")
        else:
            out.append(" | ".join(e["columns"]))
            out += [" | ".join([row["label"], *cells]) for row, cells in zip(e["rows"], e["display"])]
        if e.get("footnote"):
            out.append(f"Note: {e['footnote']}")
    for s in r["sections"]:
        out.append(f"## {s['id']} {s['title']} [{s['kind']}] exhibits: {', '.join(s['exhibit_ids']) or 'none'}")
        out.append(f"Ask: {s['ask']}")
        out += [f"Share: {t}" for t in s["info_to_share"]]
        out += [f"Calc {c['id']}: {c['label']} = {c['expression']} = {c['display']}"
            + (f" (exact {c['value']:.6g}; later steps use the exact value)" if isinstance(c.get("value"), float) else "")
            for c in s["calculations"]]
        out.append(f"Model answer: {s['model_answer']}")
        for label, key in (("What great looks like", "what_great_looks_like"), ("Common mistakes", "common_mistakes"),
                           ("Hints", "hints"), ("Pushback", "pushback")):
            if s[key]:
                out.append(f"{label}: " + " | ".join(s[key]))
    if r.get("rubric"):
        out.append("## Rubric\n" + "\n".join(f"- {l['dimension']}: strong = {l['strong']} | weak = {l['weak']}" for l in r["rubric"]))
    out.append(f"## Interviewer notes\n{r.get('interviewer_notes', '')}")
    rec = r["recommendation"]
    out.append(f"## Recommendation\n{rec['answer']}\nRisks: {'; '.join(rec['risks'])}\nNext steps: {'; '.join(rec['next_steps'])}")
    return "\n".join(out)


async def _fix(draft: CaseDraft, problems: list[str], req: GenerateRequest, level: str, meter: Meter,
               step: str) -> CaseDraft:
    msg = (
        f"{level}\n\nHere is a case draft as JSON:\n{draft.model_dump_json()}\n\n"
        "It has these problems:\n" + "\n".join(f"- {p}" for p in problems) +
        "\n\nHow to fix: for an arithmetic or consistency finding, find the calculation it names, look at the "
        "variables it uses, and decide which number is right — then change that variable or expression and every "
        "sentence, exhibit cell and conclusion that states the other number. For a missing-input finding, add the "
        "input to the prompt, a clarifying answer, a 'share' fact or an exhibit handed out in time. Problems marked "
        "STILL UNRESOLVED survived an earlier fix attempt: change the underlying numbers or structure, not just the "
        "wording."
        "\n\nReturn the complete corrected case. Make surgical fixes: correct each problem at its root and update "
        "every number, sentence and conclusion that depends on it (if a formula is right but the expectation was "
        "wrong, fix the expectation AND the text built on it). Do not add new analyses, sections or exhibits, and "
        "don't expand the case; simplify instead if a part is hard to make consistent. Keep everything that's "
        "already fine, the same title and client, and the same difficulty. The case must read as a finished "
        "original: never mention corrections, fixes, revisions or earlier versions anywhere in its text."
    )
    out = await _ask(meter, "writer", step, msg)
    out.difficulty = req.difficulty
    out.title, out.client = draft.title, draft.client
    return out


async def _check_and_fix(draft: CaseDraft, req: GenerateRequest, level: str, progress: Progress,
                         history: list[dict], meter: Meter) -> tuple[CaseDraft, verify.Values, list[verify.Issue], int]:
    fixes = 0
    for _ in range(MAX_CHECK_ROUNDS):
        vals, issues = verify.check(draft)
        serious = [i for i in issues if i.severity in ("blocker", "major")]
        if not serious:
            return draft, vals, issues, fixes
        history.append({"step": "number check", "issues": [i.as_dict() for i in serious]})
        await progress(f"Fixing {len(serious)} consistency issue{'s' if len(serious) != 1 else ''} in the math")
        draft = await _fix(draft, [f"[{i.severity}] {i.where}: {i.problem}" for i in issues], req, level, meter,
                           f"Fix {len(serious)} number-check issue{'s' if len(serious) != 1 else ''}")
        fixes += 1
    vals, issues = verify.check(draft)
    return draft, vals, issues, fixes


def new_meter(req: GenerateRequest) -> Meter:
    return Meter(model_for(req.difficulty, req.engine), MAX_USD_PER_CASE[req.engine])


async def generate(req: GenerateRequest, progress: Progress, meter: Meter | None = None) -> str:
    meter = meter or new_meter(req)
    rng = random.Random()
    level = _level_text(req.difficulty)
    archetypes = pick_archetypes(req, rng)
    recent = _recent_titles()

    await progress("Planning the storyline")
    plan_msg = (
        f"{level}\n\n{_request_text(req)}\n\n"
        + ("Patterns from real casebook cases (inspiration only — write something new; borrow the kind of "
           f"analytical engine and insight, not the scenario):\n{_archetype_text(archetypes)}\n\n" if archetypes else "")
        + (f"Recently generated cases to avoid repeating:\n" + "\n".join(f"- {t}" for t in recent) + "\n\n" if recent else "")
        + "Plan an original case that fits the request and difficulty exactly. Choose numbers that make the "
        "key insight emerge from the math."
    )
    plan = await _ask(meter, "planner", "Plan the storyline", plan_msg)
    for _ in range(MAX_PLAN_FIXES):
        plan_issues = verify.check_plan(plan.core_variables, plan.core_calculations)
        if not plan_issues:
            break
        await progress("Correcting the plan's core math")
        plan = await _ask(
            meter, "planner", "Correct the plan's core math",
            f"{plan_msg}\n\nYour previous plan:\n{plan.model_dump_json()}\n\nIts numeric spine has problems:\n"
            + "\n".join(f"- {i.where}: {i.problem}" for i in plan_issues)
            + "\nReturn the corrected plan (same story and title; fix the math and anything that depends on it).")
    plan.title = _clean_title(plan.title)

    await progress("Writing the full case")
    write_msg = (
        f"{level}\n\n{_request_text(req)}\n\nThe approved plan:\n{plan.model_dump_json(indent=1)}\n\n"
        "Write the complete case following the plan. Reuse the plan's core variables and core calculations "
        "exactly (same names, values and expressions) as the case's numeric spine, placed in the right sections; "
        "add only the supporting calculations the sections need, within the shape limits. Follow the number rules "
        "exactly: variables, calculations with expected values, '=' formulas in exhibit cells, and {placeholders} "
        "in all text."
    )
    draft = await _ask(meter, "writer", "Write the full case", write_msg)
    draft.difficulty = req.difficulty
    draft.title = _clean_title(draft.title)

    history: list[dict] = []
    await progress("Checking every number")
    draft, vals, issues, fixes = await _check_and_fix(draft, req, level, progress, history, meter)

    reviews: list[dict] = []
    max_reviews = max_reviews_for(req)
    review_names = ["Independent review", "Second review", "Third review", "Fourth review", "Fifth review",
                    "Sixth review"]
    for n in range(max_reviews):
        name = "Final review" if n == max_reviews - 1 else review_names[min(n, len(review_names) - 1)]
        await progress(name)
        rendered = verify.render(draft, vals)
        earlier = [f"- {i.get('where', '')}: {i.get('problem', '')[:220]}"
                   for h in history if "review" in h["step"].lower() for i in h["issues"]]
        review = await _ask(
            meter, "reviewer", name,
            f"{level}\n\n"
            + ("Earlier reviews raised these points, which the writer has since tried to fix. Confirm they're "
               "resolved; don't re-raise them if they are:\n" + "\n".join(earlier[-20:]) + "\n\n" if earlier else "")
            + f"Audit this case:\n\n{_review_text(rendered)}")
        reviews.append(review.model_dump())
        serious_text = []
        if review.difficulty_fit != "about_right":
            serious_text.append(f"Difficulty fit: the case is {review.difficulty_fit.replace('_', ' ')} for the requested level. Adjust it.")
        seen_where = {i.get("where", "")[:40].lower() for h in history if "review" in h["step"].lower() for i in h["issues"]}
        serious_text += [("STILL UNRESOLVED " if i.where[:40].lower() in seen_where else "")
                         + f"[{i.severity}] {i.where}: {i.problem} Fix: {i.fix}"
                         for i in review.issues if i.severity in ("blocker", "major")]
        if not serious_text or n == max_reviews - 1:
            break  # clean, or this was the final verdict
        history.append({"step": name, "issues": [i.model_dump() for i in review.issues if i.severity != "minor"]})
        await progress(f"Revising {len(serious_text)} reviewer finding{'s' if len(serious_text) != 1 else ''}")
        draft = await _fix(draft, serious_text, req, level, meter, f"Fix {len(serious_text)} {name.lower()} finding"
                           + ("s" if len(serious_text) != 1 else ""))
        fixes += 1
        draft, vals, issues, more = await _check_and_fix(draft, req, level, progress, history, meter)
        fixes += more

    await progress("Formatting")
    rendered = verify.render(draft, vals)
    remaining = [i.as_dict() for i in issues]
    last_review = reviews[-1] if reviews else None
    status = "verified"
    if any(i["severity"] in ("blocker", "major") for i in remaining):
        status = "needs_attention"
    elif last_review and any(i["severity"] in ("blocker", "major") for i in last_review["issues"]):
        status = "review_flags"

    case_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    record = {
        "id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": req.model_dump(),
        "plan": plan.model_dump(),
        "draft": draft.model_dump(),
        "rendered": rendered,
        "quality": {"status": status, "checks": remaining, "reviews": reviews, "fix_rounds": fixes,
                    "history": history, "model": meter.model, "engine": req.engine},
        "usage": meter.summary(),
    }
    GENERATED_DIR.mkdir(exist_ok=True)
    (GENERATED_DIR / f"{case_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return case_id


async def second_opinion(case_id: str) -> dict:
    """One independent review of a finished case by the stronger model — a few cents, no rewrite.

    Lets a Luna-written case get a Terra-level check without paying to regenerate it."""
    case = load_case(case_id)
    if case is None:
        raise KeyError(case_id)
    draft = CaseDraft.model_validate(case["draft"])
    vals, _ = verify.check(draft)
    meter = Meter(STRONG_MODEL, SECOND_OPINION_MAX_USD)
    review = await _ask(meter, "reviewer", "Second opinion",
                        f"{_level_text(draft.difficulty)}\n\nAudit this case:\n\n{_review_text(verify.render(draft, vals))}")
    opinion = {"model": STRONG_MODEL, "at": datetime.now(timezone.utc).isoformat(), **review.model_dump(),
               "usage": meter.summary()}
    update_case(case_id, second_opinion=opinion)
    return opinion


def list_cases() -> list[dict]:
    out = []
    for f in sorted(GENERATED_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dr = d["draft"]
        out.append({"id": d["id"], "created_at": d["created_at"], "title": dr["title"], "client": dr["client"],
                    "industry": dr["industry"], "case_type": dr["case_type"], "difficulty": dr["difficulty"],
                    "summary": dr["situation_summary"], "status": d["quality"]["status"],
                    "engine": d["quality"].get("engine"),
                    "second_opinion": None if not d.get("second_opinion") else
                    sum(i["severity"] != "minor" for i in d["second_opinion"]["issues"])})
    return out


def load_case(case_id: str) -> dict | None:
    if not case_id.replace("-", "").isalnum():
        return None
    path = GENERATED_DIR / f"{case_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def update_case(case_id: str, **fields) -> None:
    """Merge top-level fields (e.g. the exported PDF name) into a saved case."""
    case = load_case(case_id)
    if case is None:
        return
    case.update(fields)
    (GENERATED_DIR / f"{case_id}.json").write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")


def delete_case(case_id: str) -> bool:
    if not case_id.replace("-", "").isalnum():
        return False
    path = GENERATED_DIR / f"{case_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
