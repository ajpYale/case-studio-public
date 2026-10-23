"""Deterministic checks and rendering for a CaseDraft.

`check(draft)` evaluates every calculation and exhibit formula, then reports anything
that can't be computed, disagrees with what the model expected, or contradicts itself
(totals that don't add up, pie slices that don't make 100%, dangling placeholders,
derived numbers typed into answer text). `render(draft)` turns the draft into display
strings with every {placeholder} filled from the computed values.

Expressions are parsed with `ast` and evaluated against a whitelist — no eval().
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from models import CaseDraft, Difficulty, Exhibit

# ---------------------------------------------------------------- safe arithmetic

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt, "ceil": math.ceil, "floor": math.floor}


class ExprError(ValueError):
    pass


def evaluate(expr: str, env: dict[str, float]) -> float:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"can't parse '{expr}'") from exc

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ExprError(f"unknown name '{node.id}'")
            return env[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ExprError("exponent too large")
            try:
                return float(_BINOPS[type(node.op)](left, right))
            except ZeroDivisionError as exc:
                raise ExprError("division by zero") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            args = [walk(a) for a in node.args]
            try:
                return float(_FUNCS[node.func.id](*args))
            except (TypeError, ValueError) as exc:
                raise ExprError(f"bad call to {node.func.id}") from exc
        raise ExprError(f"'{ast.unparse(node)}' isn't allowed (arithmetic, names and min/max/abs/round/sqrt only)")

    value = walk(tree)
    if math.isnan(value) or math.isinf(value):
        raise ExprError("result is not a finite number")
    return value


# ------------------------------------------------------------------- formatting

def _round_half_up(x: float, decimals: int) -> Decimal:
    # Round half up from x with float noise removed: 4.4415 -> 4.442, and 4.8 / 1.28 (= 3.7499999999999996
    # in binary) -> 3.75 -> 3.8, the way a person computing by hand would round it.
    return Decimal(f"{x:.12g}").quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def _trim(x: float, decimals: int) -> str:
    s = f"{_round_half_up(x, max(decimals, 0)):,.{max(decimals, 0)}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def exact_decimals(x: float, cap: int = 4) -> int:
    """Fewest decimals that show x exactly (up to cap) — inputs are never shown rounded."""
    for d in range(cap + 1):
        if abs(round(x, d) - x) < 1e-9 * max(1.0, abs(x)):
            return d
    return cap


def _auto_decimals(x: float) -> int:
    # Whole numbers show whole; otherwise keep enough precision that a total like $141.2M
    # never displays as $141M next to components that sum to 141.2 (trailing zeros are trimmed).
    a = abs(x)
    if a == 0 or abs(a - round(a)) < 1e-9:
        return 0
    if a >= 10_000:
        return 0
    if a >= 10:
        return 1
    return 2


def fmt(value: float, unit: str, decimals: int | None = None) -> str:
    d = _auto_decimals(value) if decimals is None else decimals
    neg = value < 0
    v = abs(value)
    if unit == "pct":
        dd = decimals if decimals is not None else (0 if abs(v * 100 - round(v * 100)) < 1e-9 else 1)
        out = f"{_trim(v * 100, dd)}%"
    elif unit in ("usd", "per_unit_usd") and decimals is not None and decimals > 0:
        out = f"${_round_half_up(v, decimals):,.{max(decimals, 2)}f}"  # cents stay as cents: $41.75, $149.50
    elif unit in ("usd", "per_unit_usd"):
        if decimals is not None:
            out = f"${_trim(v, decimals)}"
        elif abs(v - round(v)) < 1e-9 or v >= 10_000:
            out = f"${v:,.0f}"
        else:
            out = f"${v:,.2f}"  # cents stay as cents: $149.50, not $149.5
    elif unit == "usd_k":
        out = f"${_trim(v, d)}K"
    elif unit == "usd_m":
        out = f"${_trim(v, d)}M"
    elif unit == "usd_b":
        out = f"${_trim(v, d)}B"
    elif unit == "count_k":
        out = f"{_trim(v, d)}K"
    elif unit == "count_m":
        out = f"{_trim(v, d)}M"
    elif unit == "multiple":
        out = f"{_trim(v, 1 if decimals is None else max(decimals, 1))}x"
    elif unit in ("years", "months", "days", "hours", "minutes"):
        word = unit if not math.isclose(v, 1) else unit[:-1]
        out = f"{_trim(v, d)} {word}"
    else:
        out = _trim(v, d)
    return f"-{out}" if neg else out


# ------------------------------------------------------------------------ checks

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
# Numbers typed into answer text that look derived: money, percents, or 3+ digit figures.
LOOSE_NUMBER = re.compile(r"(?<![\w{])(\$\s?\d[\d,]*(?:\.\d+)?\s?[KMB]?|\d[\d,]*(?:\.\d+)?\s?%|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)(?![\w}])")
YEARISH = re.compile(r"^(19|20)\d\d$")

# Minimum shape per difficulty (sections, exhibits, calculations).
# Calibrated to the reference library: harder cases differ mostly in math depth, distractors
# and pivots, not in exhibit count (library medians: 1-2 exhibits; 7 / 8 / 10 / 15 quant steps).
SHAPE = {
    "easy": (3, 1, 3),
    "medium": (4, 1, 5),
    "hard": (5, 2, 8),
    "instant_offer": (6, 3, 12),
}
# Upper bounds (sections, exhibits, calculations): a sprawling case is harder to run and to get right.
SHAPE_MAX = {
    "easy": (5, 2, 8),
    "medium": (6, 3, 12),
    "hard": (7, 4, 16),
    "instant_offer": (8, 5, 24),
}


@dataclass
class Values:
    env: dict[str, float] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    decimals: dict[str, int | None] = field(default_factory=dict)

    def text(self, name: str) -> str:
        return fmt(self.env[name], self.units[name], self.decimals.get(name))


@dataclass
class Issue:
    severity: str  # blocker | major | minor
    where: str
    problem: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "where": self.where, "problem": self.problem}


def compute(draft: CaseDraft) -> tuple[Values, list[Issue]]:
    vals, issues = Values(), []
    seen: set[str] = set()
    for v in draft.variables:
        if not v.name.isidentifier():
            issues.append(Issue("blocker", f"variable {v.name}", "name isn't a valid identifier"))
            continue
        if v.name in seen:
            issues.append(Issue("blocker", f"variable {v.name}", "duplicate name"))
        seen.add(v.name)
        vals.env[v.name], vals.units[v.name] = float(v.value), v.unit
        # Inputs display exactly as given (no rounding): $41.75 stays $41.75, 2.845 stays 2.845.
        vals.decimals[v.name] = exact_decimals(v.value * 100 if v.unit == "pct" else v.value)
        if v.unit == "pct" and abs(v.value) > 1.5:
            issues.append(Issue("major", f"variable {v.name}", f"pct values are fractions; {v.value} would be {v.value * 100:.0f}%"))
    for s in draft.sections:
        for c in s.calculations:
            where = f"{s.id} calculation {c.id}"
            if not c.id.isidentifier() or c.id in seen:
                issues.append(Issue("blocker", where, "id is invalid or already used"))
                continue
            seen.add(c.id)
            try:
                value = evaluate(c.expression, vals.env)
            except ExprError as exc:
                issues.append(Issue("blocker", where, f"{exc} in '{c.expression}'"))
                continue
            vals.env[c.id], vals.units[c.id], vals.decimals[c.id] = value, c.unit, c.decimals
            tol = max(abs(c.expected_value) * 0.01, 1e-6 if c.unit != "pct" else 5e-4)
            if abs(value - c.expected_value) > tol:
                issues.append(Issue(
                    "major", where,
                    f"'{c.expression}' = {value:,.4g}, but you expected {c.expected_value:,.4g}. "
                    "Either the formula or the expectation (and any text built on it) is wrong.",
                ))
    return vals, issues


def exhibit_values(ex: Exhibit, vals: Values) -> tuple[list[list[float | str | None]], list[Issue]]:
    issues, grid = [], []
    width = len(ex.columns) - 1
    for r in ex.rows:
        if len(r.cells) != width:
            issues.append(Issue("major", f"{ex.id} row '{r.label}'", f"has {len(r.cells)} cells for {width} value columns"))
        row: list[float | str | None] = []
        for cell in r.cells:
            if isinstance(cell, str) and cell.strip().startswith("="):
                try:
                    row.append(evaluate(cell.strip()[1:], vals.env))
                except ExprError as exc:
                    issues.append(Issue("blocker", f"{ex.id} row '{r.label}'", f"{exc} in '{cell}'"))
                    row.append(None)
            elif isinstance(cell, (int, float)):
                row.append(float(cell))
            else:
                row.append(cell)
        grid.append(row)
    return grid, issues


def column_unit(ex: Exhibit, j: int) -> str:
    """Unit of value column j (0-based, label column excluded)."""
    if ex.column_units and j < len(ex.column_units):
        return ex.column_units[j]
    return ex.value_unit


_RATE_HEADER = re.compile(r"%|percent|share|margin|growth|rate|utili[sz]ation|penetration|conversion|cagr", re.I)


def _display_unit(ex: Exhibit, j: int, grid: list[list]) -> str:
    """Display unit for column j; for cases written without column_units, show rate columns as %."""
    unit = column_unit(ex, j)
    if ex.column_units or unit == "pct" or j + 1 >= len(ex.columns) or not _RATE_HEADER.search(ex.columns[j + 1]):
        return unit
    nums = [r[j] for r in grid if j < len(r) and isinstance(r[j], float)]
    return "pct" if nums and all(abs(x) <= 1.5 for x in nums) else unit


def _cell_text(ex: Exhibit, row, j: int, value, units: list[str], vals: Values) -> str:
    if not isinstance(value, float):
        return "—" if value is None else str(value)
    raw = row.cells[j] if j < len(row.cells) else None
    if isinstance(raw, str) and raw.strip().startswith("="):
        name = raw.strip()[1:].strip()
        if name in vals.env:  # a cell that pulls one input or result shows it in that item's own unit
            return vals.text(name)
    unit = units[j] if j < len(units) else ex.value_unit
    if isinstance(raw, (int, float)):  # context data typed into the exhibit: show exactly as given
        return fmt(value, unit, exact_decimals(value * 100 if unit == "pct" else value))
    return fmt(value, unit)


def _total_checks(ex: Exhibit, grid: list[list]) -> list[Issue]:
    issues = []
    labels = [r.label.strip().lower() for r in ex.rows]
    for i, lab in enumerate(labels):
        if lab.startswith(("total", "sum")) and i > 0:
            for col in range(len(ex.columns) - 1):
                if column_unit(ex, col) in ("pct", "ratio", "multiple", "per_unit_usd"):
                    continue
                parts = [g[col] for g in grid[:i] if col < len(g) and isinstance(g[col], float)]
                tot = grid[i][col] if col < len(grid[i]) else None
                if isinstance(tot, float) and len(parts) >= 2:
                    s = sum(parts)
                    if abs(s - tot) > max(abs(tot) * 0.005, 1e-6):
                        issues.append(Issue("major", f"{ex.id} '{ex.rows[i].label}' / '{ex.columns[col + 1]}'",
                                            f"total shows {tot:,.4g} but the rows above sum to {s:,.4g}"))
    if ex.kind == "pie" and column_unit(ex, 0) == "pct":
        vals = [g[0] for g in grid if g and isinstance(g[0], float)]
        if vals and abs(sum(vals) - 1) > 0.011:
            issues.append(Issue("major", ex.id, f"pie slices sum to {sum(vals) * 100:.1f}%, not 100%"))
    return issues


def _text_fields(draft: CaseDraft) -> list[tuple[str, str, bool]]:
    """(where, text, answer_like) for every field that may hold placeholders."""
    out = [("prompt", draft.prompt, False)]
    out += [(f"clarifying '{q.question[:40]}'", q.answer, False) for q in draft.clarifying]
    for s in draft.sections:
        out += [(f"{s.id} info", t, False) for t in s.info_to_share]
        out.append((f"{s.id} model answer", s.model_answer, True))
    out.append(("recommendation", draft.recommendation.answer, True))
    return out


# Keys whose strings are identifiers or formulas, never display text.
_NON_TEXT_KEYS = {"expression", "id", "name", "revealed_in", "kind", "value_unit", "column_units", "unit", "role",
                  "difficulty", "format", "exhibit_ids", "cells", "columns_raw"}


def _walk_text(obj, path: str = ""):
    """Yield (path, string) for every display-text string in a dumped draft."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in _NON_TEXT_KEYS:
                yield from _walk_text(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_text(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _fill_all(obj, vals: Values):
    if isinstance(obj, dict):
        return {k: (v if k in _NON_TEXT_KEYS else _fill_all(v, vals)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill_all(v, vals) for v in obj]
    if isinstance(obj, str):
        return fill(obj, vals)
    return obj


def check(draft: CaseDraft) -> tuple[Values, list[Issue]]:
    vals, issues = compute(draft)

    for path, text in _walk_text(draft.model_dump()):
        for name in PLACEHOLDER.findall(text):
            if name not in vals.env:
                issues.append(Issue("blocker", path, f"placeholder {{{name}}} doesn't match any variable or calculation"))

    ex_ids = {e.id for e in draft.exhibits}
    used_ex: set[str] = set()
    for s in draft.sections:
        for eid in s.exhibit_ids:
            if eid not in ex_ids:
                issues.append(Issue("blocker", s.id, f"refers to exhibit '{eid}' which doesn't exist"))
            used_ex.add(eid)
    for e in draft.exhibits:
        if e.id not in used_ex:
            issues.append(Issue("minor", e.id, "exhibit is never handed out in any section"))
        if e.kind != "text":
            grid, ex_issues = exhibit_values(e, vals)
            issues += ex_issues + _total_checks(e, grid)

    known = _known_numbers(draft, vals)
    for where, text, answer_like in _text_fields(draft):
        # A typed number is fine if it matches something in the case; one that matches nothing
        # is exactly how answer keys drift from their exhibits.
        stripped = PLACEHOLDER.sub("", text)
        stray = [m for m in LOOSE_NUMBER.findall(stripped)
                 if not YEARISH.match(m.replace(",", "")) and not _matches_known(m, known)]
        if stray:
            issues.append(Issue("major" if answer_like else "minor", where,
                                "typed-out numbers that match no variable, calculation or exhibit value: "
                                + ", ".join(sorted(set(stray))[:5]) + " — use {placeholders} so the text matches the math"))

    issues += _availability_issues(draft, vals)
    issues += _placement_issues(draft, vals)
    issues += _hand_math_issues(draft, vals)

    referenced = set()
    for s in draft.sections:
        for c in s.calculations:
            referenced |= {n.id for n in ast.walk(ast.parse(c.expression, mode="eval")) if isinstance(n, ast.Name)} if _parses(c.expression) else set()
    for e in draft.exhibits:
        for r in e.rows:
            for cell in r.cells:
                if isinstance(cell, str) and cell.strip().startswith("=") and _parses(cell.strip()[1:]):
                    referenced |= {n.id for n in ast.walk(ast.parse(cell.strip()[1:], mode="eval")) if isinstance(n, ast.Name)}
    for _, text in _walk_text(draft.model_dump()):
        referenced |= set(PLACEHOLDER.findall(text))
    for v in draft.variables:
        if v.role == "input" and v.name not in referenced:
            issues.append(Issue("minor", f"variable {v.name}", "defined but never used (mark it 'distractor' if intentional)"))

    n_sec, n_ex, n_calc = SHAPE[draft.difficulty]
    calcs = sum(len(s.calculations) for s in draft.sections)
    if len(draft.sections) < n_sec or len(draft.exhibits) < n_ex or calcs < n_calc:
        issues.append(Issue("major", "case shape",
                            f"{draft.difficulty} needs at least {n_sec} sections, {n_ex} exhibits and {n_calc} calculations; "
                            f"this has {len(draft.sections)}, {len(draft.exhibits)} and {calcs}"))
    if draft.difficulty == "instant_offer" and not any(
            re.search(r"exceptional|offer", f"{r.dimension} {r.strong}", re.I) for r in draft.rubric):
        issues.append(Issue("major", "rubric", "Instant Offer needs a rubric line that separates strong from exceptional "
                                               "(offer-on-the-spot) performance"))
    if draft.difficulty in ("hard", "instant_offer"):
        pushbacks = sum(len(s.pushback) for s in draft.sections)
        if pushbacks < 2:
            issues.append(Issue("major", "pushback", f"{draft.difficulty} needs at least two interviewer pushback "
                                                     f"challenges with what a strong candidate says; this has {pushbacks}"))
        quant = [s for s in draft.sections if s.calculations]
        if quant and sum(1 for s in quant if s.hints) < len(quant) / 2:
            issues.append(Issue("minor", "hints", "give hints for most quantitative sections"))
    if draft.difficulty != "easy" and draft.exhibits and all(e.kind in ("table", "text") for e in draft.exhibits):
        issues.append(Issue("minor", "exhibits", "no charts — turn a trend or comparison into a line or bar chart"))
    leaks = [p for p, t in _walk_text(draft.model_dump())
             if re.search(r"\b(corrected|revised|fixed) (exhibit|version|case|key|answer|figure|number)", t, re.I)]
    unreal = [p for p, t in _walk_text(draft.model_dump())
              if re.search(r"\b(fictional|fictitious|hypothetical|imaginary|made-up|illustrative)\b", t, re.I)]
    if unreal:
        issues.append(Issue("major", unreal[0], "the case calls itself fictional or hypothetical; present the client, "
                                                "market and data as real (the reader already knows they're invented)"))
    if leaks:
        issues.append(Issue("major", leaks[0], "text mentions corrections or earlier versions; the case must read as a finished original"))
    x_sec, x_ex, x_calc = SHAPE_MAX[draft.difficulty]
    if len(draft.sections) > x_sec or len(draft.exhibits) > x_ex or calcs > x_calc:
        issues.append(Issue("major", "case shape",
                            f"{draft.difficulty} should have at most {x_sec} sections, {x_ex} exhibits and {x_calc} calculations; "
                            f"this has {len(draft.sections)}, {len(draft.exhibits)} and {calcs}. Cut supporting arithmetic "
                            "(keep the numeric spine) rather than adding analyses"))
    return vals, issues


def check_plan(variables: list, calculations: list) -> list[Issue]:
    """Evaluate a plan's numeric spine the same way as a full case."""
    env: dict[str, float] = {}
    issues: list[Issue] = []
    for v in variables:
        env[v.name] = float(v.value)
        if v.unit == "pct" and abs(v.value) > 1.5:
            issues.append(Issue("major", f"core variable {v.name}", f"pct values are fractions; {v.value} would be {v.value * 100:.0f}%"))
    for c in calculations:
        try:
            value = evaluate(c.expression, env)
        except ExprError as exc:
            issues.append(Issue("blocker", f"core calculation {c.id}", f"{exc} in '{c.expression}'"))
            continue
        env[c.id] = value
        if abs(value - c.expected_value) > max(abs(c.expected_value) * 0.01, 1e-6):
            issues.append(Issue("major", f"core calculation {c.id}",
                                f"'{c.expression}' = {value:,.4g}, but you expected {c.expected_value:,.4g}"))
    return issues


_ANY_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?[KMB%]?")


def _names_in(expr: str) -> set[str]:
    if not _parses(expr):
        return set()
    return {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}


def _availability_issues(draft: CaseDraft, vals: Values) -> list[Issue]:
    """A calculation may only use inputs the candidate has been given by that point.

    An input counts as given if it's an explicit assumption, appears (as a placeholder or its value)
    in the prompt, a clarifying answer, or any section ask or 'share if asked' fact up to that section, or sits in an
    exhibit handed out up to that section.
    """
    issues: list[Issue] = []
    by_name = {v.name: v for v in draft.variables}
    texts = [draft.prompt] + [q.answer for q in draft.clarifying]
    handed: set[str] = set()
    ex_by_id = {e.id: e for e in draft.exhibits}
    ex_refs: dict[str, set[str]] = {}
    ex_vals: dict[str, list[float]] = {}
    for e in draft.exhibits:
        refs, nums = set(), []
        for r in e.rows:
            for cell in r.cells:
                if isinstance(cell, str) and cell.strip().startswith("="):
                    refs |= _names_in(cell.strip()[1:])
                elif isinstance(cell, (int, float)):
                    nums.append(float(cell))
        ex_refs[e.id], ex_vals[e.id] = refs, nums

    # Exhibits must not show results the candidate is asked to calculate in that section or later.
    calc_section = {c.id: k for k, s in enumerate(draft.sections) for c in s.calculations}
    first_handed: dict[str, int] = {}
    for k, s in enumerate(draft.sections):
        for eid in s.exhibit_ids:
            first_handed.setdefault(eid, k)
    for eid, k in first_handed.items():
        spoilers = sorted(n for n in ex_refs.get(eid, set()) if calc_section.get(n, -1) >= k)
        if spoilers:
            issues.append(Issue(
                "major", f"{eid}",
                f"shows {', '.join(spoilers[:4])}, which the candidate is supposed to calculate in "
                f"{draft.sections[k].id} or later — show the inputs instead of the answer",
            ))

    for s in draft.sections:
        texts += [s.ask, *s.info_to_share]  # the ask is read aloud, so its numbers are given too
        handed |= set(s.exhibit_ids)
        raw = "\n".join(texts)
        filled_tokens = _ANY_NUMBER.findall(fill(raw, vals))
        for c in s.calculations:
            for name in _names_in(c.expression):
                v = by_name.get(name)
                if v is None or v.revealed_in == "assumption":
                    continue
                if f"{{{name}}}" in raw:
                    continue
                if any(name in ex_refs.get(eid, set()) or any(abs(x - v.value) < 1e-9 for x in ex_vals.get(eid, []))
                       for eid in handed if eid in ex_by_id):
                    continue
                if any(_matches_known(t, ([abs(v.value) * _SCALE.get(v.unit, 1.0), abs(v.value)],
                                          [abs(v.value) * 100] if v.unit == "pct" else []))
                       for t in filled_tokens if t.strip("$ ,")):
                    continue
                issues.append(Issue(
                    "major", f"{s.id} calculation {c.id}",
                    f"uses {name} ({v.label}, revealed in '{v.revealed_in}') before the candidate is given it. Put it in "
                    f"the prompt, a clarifying answer, this or an earlier section's 'share if asked', or an exhibit "
                    f"handed out by this section — or mark it 'assumption' if the candidate should assume it",
                ))
    return issues


def _hand_math_issues(draft: CaseDraft, vals: Values) -> list[Issue]:
    """Interview math is done by hand: no powers above a cube (annuity and discount factors must be
    given as inputs), and no single-row 'exhibits' that are really a list of assumptions."""
    issues: list[Issue] = []
    for s in draft.sections:
        for c in s.calculations:
            if not _parses(c.expression):
                continue
            for node in ast.walk(ast.parse(c.expression, mode="eval")):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                    try:
                        exp = evaluate(ast.unparse(node.right), vals.env)
                    except ExprError:
                        continue
                    if abs(exp) > 3 or exp != int(exp):
                        issues.append(Issue(
                            "major", f"{s.id} calculation {c.id}",
                            f"'{c.expression}' raises to the power {exp:g}, which a candidate can't do by hand. Give the "
                            "factor itself as an input (e.g. an annuity or discount factor stated in an exhibit or a "
                            "'share' line) and use it in the formula, or use a perpetuity with a round rate"))
                        break
    # Two sections that ask essentially the same thing pad the case without testing anything new.
    words = [set(re.findall(r"[a-z]{4,}", s.ask.lower())) for s in draft.sections]
    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            a, b = words[i], words[j]
            if a and b and len(a & b) / len(a | b) > 0.6:
                issues.append(Issue("major", f"{draft.sections[i].id} and {draft.sections[j].id}",
                                    "these two sections ask nearly the same thing; merge them or give the second a "
                                    "different job"))
    syntheses = [s.id for s in draft.sections if s.kind == "synthesis"]
    if len(syntheses) > 1:
        issues.append(Issue("major", ", ".join(syntheses), "more than one synthesis section; keep a single final "
                                                          "recommendation and give the others a different job"))
    for e in draft.exhibits:
        if e.kind == "table" and len(e.rows) == 1 and len(e.columns) >= 4:
            issues.append(Issue("minor", e.id, "a single-row table of assumptions isn't much of an exhibit; list one "
                                               "assumption per row, merge it into another exhibit, or use 'share' lines"))
    return issues


def _placement_issues(draft: CaseDraft, vals: Values) -> list[Issue]:
    """Every input and distractor must be something the candidate actually sees: in an exhibit, the
    prompt, a clarifying answer or an interviewer 'share' line. Otherwise the guide grades the
    candidate on data they were never given. ('assumption' variables are exempt.)"""
    issues: list[Issue] = []
    texts = [draft.prompt] + [q.answer for q in draft.clarifying]
    texts += [t for s in draft.sections for t in [s.ask, *s.info_to_share]]
    cell_refs: set[str] = set()
    cell_nums: list[float] = []
    for e in draft.exhibits:
        texts += [e.title, e.subtitle or "", e.footnote or "", e.text_body or "", *e.columns]
        for r in e.rows:
            texts.append(r.label)
            for cell in r.cells:
                if isinstance(cell, str) and cell.strip().startswith("="):
                    cell_refs |= _names_in(cell.strip()[1:])
                elif isinstance(cell, (int, float)):
                    cell_nums.append(float(cell))
                elif isinstance(cell, str):
                    texts.append(cell)
    raw = "\n".join(texts)
    for v in draft.variables:
        if v.revealed_in.strip() == "assumption":
            continue
        if (v.name in cell_refs or f"{{{v.name}}}" in raw or any(abs(x - v.value) < 1e-9 for x in cell_nums)
                or _states_value(raw, v, vals)):
            continue
        issues.append(Issue(
            "major", f"variable {v.name}",
            f"{v.label} ({v.role}, revealed in '{v.revealed_in}') never appears anywhere the candidate sees it. "
            f"Add it where it belongs ('={v.name}' in an exhibit cell, or {{{v.name}}} in the prompt, a clarifying "
            "answer or a 'share' line), or remove it and every mention of it in hints, common mistakes and grading notes",
        ))
    return issues


def _states_value(text: str, v, vals: Values) -> bool:
    """True if the text writes out v's value: same figure to within half a percent (a stray "4"
    doesn't count as 4.2 years). Percentages must carry a % sign."""
    targets = [abs(v.value) * 100] if v.unit == "pct" else [abs(v.value) * _SCALE.get(v.unit, 1.0), abs(v.value)]
    for token in _ANY_NUMBER.findall(fill(text, vals)):
        t = token.replace("$", "").replace(",", "").strip()
        is_pct = t.endswith("%")
        if is_pct != (v.unit == "pct"):
            continue
        t = t.rstrip("%").strip()
        scale = 1.0
        if t and t[-1] in _SUFFIX:
            scale, t = _SUFFIX[t[-1]], t[:-1].strip()
        try:
            num = float(t) * scale
        except ValueError:
            continue
        if any(abs(num - c) <= max(0.005 * c, 1e-9) for c in targets):
            return True
    return False


_SCALE = {"usd_k": 1e3, "usd_m": 1e6, "usd_b": 1e9, "count_k": 1e3, "count_m": 1e6}
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9}


def _known_numbers(draft: CaseDraft, vals: Values) -> tuple[list[float], list[float]]:
    """(absolute values in base units, percent values) for everything the case defines."""
    plain, pct = [], []

    def add(v: float, unit: str) -> None:
        if unit == "pct":
            pct.append(abs(v) * 100)
        plain.append(abs(v) * _SCALE.get(unit, 1.0))
        plain.append(abs(v))  # the same figure quoted in its own unit ("12.5" of usd_m)

    for name, v in vals.env.items():
        add(v, vals.units[name])
    for e in draft.exhibits:
        if e.kind == "text":
            continue
        grid, _ = exhibit_values(e, vals)
        for row in grid:
            for j, cell in enumerate(row):
                if isinstance(cell, float):
                    add(cell, column_unit(e, j))
    return plain, pct


def _matches_known(token: str, known: tuple[list[float], list[float]]) -> bool:
    plain, pct = known
    t = token.replace("$", "").replace(",", "").strip()
    is_pct = t.endswith("%")
    t = t.rstrip("%").strip()
    scale = 1.0
    if t and t[-1] in _SUFFIX:
        scale, t = _SUFFIX[t[-1]], t[:-1].strip()
    try:
        num = float(t) * scale
    except ValueError:
        return True  # not a number we can judge
    decimals = len(t.split(".")[1]) if "." in t else 0
    rounding = 0.5 * 10 ** (-decimals) * scale  # "$4M" stands for anything that rounds to it
    pool = pct if is_pct else plain
    return any(abs(num - c) <= max(0.01 * c, rounding) for c in pool)


def _parses(expr: str) -> bool:
    try:
        ast.parse(expr, mode="eval")
        return True
    except SyntaxError:
        return False


# ----------------------------------------------------------------------- render

_DOUBLED = [
    (re.compile(r"\$\s?(-?\$)"), r"\1"),                                   # "$" + "$4.2M"
    (re.compile(r"-\$\$"), "-$"),
    (re.compile(r"%\s?%"), "%"),                                          # "25%" + "%"
    (re.compile(r"(\d)([KMB])\s?\2\b"), r"\1\2"),                         # "$4.2M" + "M"
    (re.compile(r"(\d)([KMB])\s(?:thousand|million|billion)\b", re.I), r"\1\2"),
    (re.compile(r"(\d)x\s?x\b"), r"\1x"),                                 # "3.2x" + "x"
    (re.compile(r"\b(year|month|day|hour|minute)(s?)\s+\1s?\b"), r"\1\2"),  # "12 months" + "months"
]


def fill(text: str, vals: Values) -> str:
    out = PLACEHOLDER.sub(lambda m: vals.text(m.group(1)) if m.group(1) in vals.env else m.group(0), text)
    # Placeholders render with their own symbol and unit; drop any the writer added around them.
    for pattern, repl in _DOUBLED:
        out = pattern.sub(repl, out)
    return out


def render(draft: CaseDraft, vals: Values) -> dict:
    """A display-ready dict: all placeholders filled, exhibit cells formatted, chart values numeric."""
    d = _fill_all(draft.model_dump(), vals)
    for s in d["sections"]:
        for c in s["calculations"]:
            c["value"] = vals.env.get(c["id"])
            c["display"] = vals.text(c["id"]) if c["id"] in vals.env else "n/a"
            c["expression_display"] = _pretty_expr(c["expression"], draft)
    for e_out, e in zip(d["exhibits"], draft.exhibits):
        if e.kind == "text":
            e_out["text_body"] = fill(e.text_body or "", vals)
            continue
        grid, _ = exhibit_values(e, vals)
        e_out["grid"] = grid
        units = [_display_unit(e, j, grid) for j in range(len(e.columns) - 1)]
        e_out["display"] = [[_cell_text(e, r, j, c, units, vals) for j, c in enumerate(row)]
                            for r, row in zip(e.rows, grid)]
        e_out["units"] = units
    for v in d["variables"]:
        v["display"] = vals.text(v["name"]) if v["name"] in vals.env else fmt(v["value"], v["unit"])
    return d


def _pretty_expr(expr: str, draft: CaseDraft) -> str:
    labels = {v.name: v.label for v in draft.variables}
    for s in draft.sections:
        for c in s.calculations:
            labels[c.id] = c.label
    # One pass over identifiers so a label's own words are never re-substituted.
    out = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: f"[{labels[m.group(0)]}]" if m.group(0) in labels else m.group(0), expr)
    return out.replace("**", "^").replace("*", "×").replace("/", "÷")


SHAPE_TEXT = {
    k: (f"{v[0]}-{SHAPE_MAX[k][0]} sections, {v[1]}-{SHAPE_MAX[k][1]} exhibits and "
        f"{v[2]}-{SHAPE_MAX[k][2]} calculations in total") for k, v in SHAPE.items()
}


def shape_for(difficulty: Difficulty) -> str:
    return SHAPE_TEXT[difficulty]
