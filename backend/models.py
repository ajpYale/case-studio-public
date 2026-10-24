"""Data shapes for a generated case and the API around it.

The model writes a `CaseDraft`. Every number lives in one place: as a `Variable` (an input
the case gives the candidate) or a `Calculation` (an arithmetic expression over variables
and earlier calculations). Exhibit cells and answer text never hard-code a derived number;
they reference it, so the answer key can't drift from the exhibits.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard", "instant_offer"]
CaseFormat = Literal["interviewer_led", "candidate_led"]
Unit = Literal[
    "usd", "usd_k", "usd_m", "usd_b", "pct", "count", "count_k", "count_m",
    "years", "months", "days", "hours", "minutes", "multiple", "ratio", "per_unit_usd", "other",
]
SectionKind = Literal[
    "framework", "brainstorm", "market_sizing", "quant", "exhibit_read", "pivot", "synthesis",
]
ExhibitKind = Literal["table", "bar", "stacked_bar", "line", "pie", "text"]

UNIT_HELP = (
    "usd = dollars, usd_k / usd_m / usd_b = thousands / millions / billions of dollars "
    "(the value is in that unit, e.g. 12.5 with usd_m means $12.5M), pct = a FRACTION "
    "(0.25 means 25%), count / count_k / count_m = plain, thousands, millions of things, "
    "multiple = an 'x' multiple, ratio = a plain ratio, per_unit_usd = dollars per unit."
)


# ----------------------------------------------------------------------------- draft


class Variable(BaseModel):
    name: str = Field(description="snake_case identifier, unique across variables and calculations.")
    value: float
    unit: Unit = Field(description=UNIT_HELP)
    label: str = Field(description="Human label, e.g. 'Annual fixed cost of the new plant'.")
    revealed_in: str = Field(
        description="Where the candidate gets it: 'prompt', 'clarifying', an exhibit id like 'ex2', "
        "'interviewer' (shared when asked during a section), or 'assumption' (candidate should assume it)."
    )
    role: Literal["input", "distractor"] = Field(
        "input", description="'distractor' marks data that's deliberately irrelevant (harder cases)."
    )


class Calculation(BaseModel):
    id: str = Field(description="snake_case identifier, unique across variables and calculations.")
    label: str = Field(description="What it computes, e.g. 'Annual contribution margin'.")
    expression: str = Field(
        description="Python arithmetic over variable names and EARLIER calculation ids. Allowed: + - * / ** ( ), "
        "numbers, and min, max, abs, round, sqrt. Example: 'fixed_cost / (price - unit_cost)'. "
        "Percentages are fractions, so 'revenue * margin_pct'."
    )
    unit: Unit = Field(description=UNIT_HELP)
    expected_value: float = Field(description="The value you expect the expression to produce (used as a self-check).")
    decimals: int | None = Field(None, description="Decimals to display; null = sensible default.")


Cell = Union[float, str]


class ExhibitRow(BaseModel):
    label: str
    cells: list[Cell] = Field(
        description="One per non-label column. A number, plain text, or '=expression' to pull a variable or "
        "calculation (e.g. '=price_2024' or '=units * price'). Use '=' for any number that the solution uses."
    )


class Exhibit(BaseModel):
    id: str = Field(description="'ex1', 'ex2', ...")
    title: str
    subtitle: str | None = None
    kind: ExhibitKind = Field(
        description="table, or a chart drawn from the same rows: bar / stacked_bar / line use the first "
        "column as categories (rows) and each other column as a series; pie uses one value column."
    )
    columns: list[str] = Field(description="Header row INCLUDING the first (label) column.")
    rows: list[ExhibitRow]
    value_unit: Unit = Field(description="Default unit used to format numeric cells. " + UNIT_HELP)
    column_units: list[Unit] | None = Field(
        None, description="Per-column units when columns differ (one per NON-label column), e.g. "
        "['count', 'pct', 'usd_m']. Use this whenever a table mixes units, so 0.22 shows as 22%."
    )
    footnote: str | None = None
    text_body: str | None = Field(None, description="Only for kind='text': the handout copy.")


class ClarifyingQA(BaseModel):
    question: str
    answer: str = Field(description="May reference numbers with {name} placeholders.")


class FrameworkBucket(BaseModel):
    name: str
    points: list[str]


class Section(BaseModel):
    id: str = Field(description="'q1', 'q2', ...")
    title: str
    kind: SectionKind
    ask: str = Field(description="What the interviewer says to the candidate. No answers here.")
    exhibit_ids: list[str] = Field(default_factory=list, description="Exhibits handed out in this section.")
    info_to_share: list[str] = Field(
        default_factory=list,
        description="Facts the interviewer gives when the candidate asks. Use {name} placeholders for numbers.",
    )
    calculations: list[Calculation] = Field(default_factory=list)
    model_answer: str = Field(
        description="What a strong candidate says/derives. EVERY derived number must be a {calc_id} or {variable} "
        "placeholder, never typed out."
    )
    what_great_looks_like: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list, description="Nudges the interviewer can give if the candidate is stuck.")
    pushback: list[str] = Field(default_factory=list, description="Challenges the interviewer should put to the candidate.")


class Recommendation(BaseModel):
    answer: str = Field(description="Sample final recommendation; numbers as {placeholders}.")
    risks: list[str]
    next_steps: list[str]


class RubricLine(BaseModel):
    dimension: str
    strong: str
    weak: str


class CaseDraft(BaseModel):
    title: str
    client: str = Field(description="Fictional client name.")
    industry: str
    case_type: str
    difficulty: Difficulty
    format: CaseFormat
    duration_minutes: int
    concepts_tested: list[str]
    situation_summary: str = Field(description="One-line summary for the case library.")
    prompt: str = Field(description="The read-aloud case prompt; numbers as {placeholders}.")
    clarifying: list[ClarifyingQA]
    variables: list[Variable]
    framework: list[FrameworkBucket]
    framework_notes: str
    sections: list[Section]
    exhibits: list[Exhibit]
    recommendation: Recommendation
    rubric: list[RubricLine]
    interviewer_notes: str = Field(description="How to run this case well: pacing, where candidates stumble, the key insight.")


# ------------------------------------------------------------------------------ plan


class SectionPlan(BaseModel):
    kind: SectionKind
    intent: str = Field(description="What this section tests and what the candidate must find.")


class CasePlan(BaseModel):
    title: str
    client: str
    industry: str
    case_type: str
    situation: str
    core_question: str
    key_insight: str = Field(description="The non-obvious finding a strong candidate must reach.")
    twist: str | None = Field(None, description="Mid-case pivot, curveball, or counter-intuitive result (hard / instant offer).")
    storyline: list[SectionPlan]
    numbers_plan: str = Field(description="Which inputs drive the answer, rough magnitudes, and how the math chains.")
    exhibits_plan: list[str] = Field(description="One line per exhibit: what it shows and what it hides.")
    core_variables: list[Variable] = Field(description="The inputs that drive the answer, with final values and units.")
    core_calculations: list[Calculation] = Field(
        description="The 6-15 calculations that carry the answer, in order, over core_variables and earlier core "
        "calculations. This is the case's numeric spine; get the finance exactly right here."
    )


# ------------------------------------------------------------------------- reviews


class ReviewIssue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    where: str
    problem: str
    fix: str


class Review(BaseModel):
    issues: list[ReviewIssue]
    difficulty_fit: Literal["too_easy", "about_right", "too_hard"]
    summary: str


class SolverAnswer(BaseModel):
    id: str = Field(description="The id of the result, exactly as listed.")
    value: float | None = Field(description="Your result in the unit stated for that step (pct as a fraction: 0.25 "
                                "means 25%; usd_m in millions). null only if it can't be worked out at all.")
    working: str = Field(description="One line of arithmetic showing the inputs you used, e.g. '1,200 x $45 = $54,000'.")
    missing: str | None = Field(None, description="If a number you needed was never given, or the question can be read "
                                "two ways, say exactly what; otherwise null.")


class SolverOutput(BaseModel):
    answers: list[SolverAnswer]


# ----------------------------------------------------------------------------- API


class GenerateRequest(BaseModel):
    difficulty: Difficulty
    case_type: str | None = None
    industry: str | None = None
    format: CaseFormat | None = None
    notes: str | None = Field(None, max_length=600)
    # "luna" = the course model for every step; "strong" = Terra (Sol for Instant Offer).
    engine: Literal["luna", "strong"] = "luna"
    # Must be true for runs on an expensive model; the UI asks the user every run.
    confirm_cost: bool = False
