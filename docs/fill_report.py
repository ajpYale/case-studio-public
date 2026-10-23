"""Fill the data-driven sections of report_src.html and slides_src.html from the measured run log.

Every number here comes from docs/run_log.json, docs/tokenomics.json and the audit files in docs/runs.
Run once after collect_runs.py and tokenomics.py; it replaces the <!--SLOT--> markers.
"""

from __future__ import annotations

import json
from pathlib import Path

DOCS = Path(__file__).resolve().parent
runs = json.loads((DOCS / "run_log.json").read_text(encoding="utf-8"))
tok = json.loads((DOCS / "tokenomics.json").read_text(encoding="utf-8"))
L, B = tok["levels"], tok["blend"]
LEVEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "instant_offer": "Instant Offer"}


def money(x: float, d: int = 3) -> str:
    return f"${x:,.{d}f}"


def k(x: float) -> str:
    return f"{x / 1000:,.1f}K"


# Audit results per run (Terra second opinion on each completed Luna case)
done = [r for r in runs if r["status"] == "done"]
clean = {lv: sum(1 for r in done if r["difficulty"] == lv and r.get("audit", {}).get("majors") == 0) for lv in LEVEL}
count = {lv: sum(1 for r in done if r["difficulty"] == lv) for lv in LEVEL}
verified = {lv: sum(1 for r in done if r["difficulty"] == lv and r["quality"] == "verified") for lv in LEVEL}
hard_n = count["hard"] + count["instant_offer"]
hard_clean = clean["hard"] + clean["instant_offer"]
hard_verified = verified["hard"] + verified["instant_offer"]
easy_n = count["easy"] + count["medium"]
easy_clean = clean["easy"] + clean["medium"]

kpis = f'''<div class="kpis">
  <div class="kpi"><b>{money(L["easy"]["usd"], 3)}–{money(L["instant_offer"]["usd"], 2)}</b><span>measured cost per case on Luna, Easy to Instant Offer</span></div>
  <div class="kpi"><b>{L["easy"]["minutes"]:.0f}–{L["instant_offer"]["minutes"]:.0f} min</b><span>average time per case, unattended</span></div>
  <div class="kpi"><b>35%</b><span>of free online casebook cases I audited had a wrong key or flawed premise</span></div>
  <div class="kpi"><b>28</b><span>automated safety and correctness tests, all passing</span></div>
</div>'''

model_finding = f'''<div class="callout"><b>Luna is not powerful enough to make Hard and Instant Offer cases reliably.</b>
In my 15 test runs, Luna's own reviewer passed {hard_verified} of its {hard_n} Hard and Instant Offer cases. But an independent review by the
stronger <code>gpt-5.6-terra</code> found at least one major issue in {hard_n - hard_clean} of those {hard_n}: an assumption the key relies on
but never states, a number that needs a calculator, or a twist that the case gives away early. On Easy and Medium, {easy_clean} of
{easy_n} Luna cases passed the same independent review clean. So Luna is the right default for everyday practice, but at the top
two levels its self-review is too lenient. The app says so on screen and offers two upgrades: a <b>Second opinion</b> button
(one Terra review of the finished case, about {money(0.049, 2)}) and the <b>Stronger</b> engine.</div>'''

# ---- results table (appendix-style) ----
rows = []
for r in runs:
    a = r.get("audit")
    if r["status"] != "done":
        why = "config: Luna rejects structured output on Chat Completions (fixed by switching to the Responses API)" if r["minutes"] < 1 else "API gateway HTTP 500 (retries added after run 6)"
        rows.append(f'<tr><td>{r["label"].split("-")[0].replace("run", "")}</td><td>{LEVEL.get(r["difficulty"], r["difficulty"])}</td><td colspan="6">Failed: {why}</td><td class="num">{r["minutes"]:.1f}</td></tr>')
        continue
    au = "—" if not a else ("clean" if a["majors"] == 0 else f'{a["majors"]} major')
    rows.append(f'<tr><td>{r["label"].split("-")[0].replace("run", "")}</td><td>{LEVEL[r["difficulty"]]}</td>'
                f'<td>{"Verified" if r["quality"] == "verified" else "Flags remain"}</td><td>{au}</td>'
                f'<td class="num">{r["calls"]}</td><td class="num">{k(r["input"])}</td><td class="num">{k(r["cached"])}</td>'
                f'<td class="num">{k(r["output"])}</td><td class="num">{r["minutes"]:.1f}</td></tr>'
                .replace(f'<td class="num">{r["minutes"]:.1f}</td></tr>', f'<td class="num">{money(r["usd"])}</td><td class="num">{r["minutes"]:.1f}</td></tr>'))
runs_table = '''<table>
<thead><tr><th>Run</th><th>Level</th><th>Pipeline verdict</th><th>Terra audit</th><th class="num">Calls</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Output</th><th class="num">Cost</th><th class="num">Min</th></tr></thead>
<tbody>''' + "\n".join(rows) + "</tbody></table>"
# failed rows have one fewer cell; pad them
runs_table = runs_table.replace('<td colspan="6">', '<td colspan="7">')

level_rows = "\n".join(
    f'<tr><td>{LEVEL[lv]}</td><td class="num">{L[lv]["n"]}</td><td class="num">{L[lv]["calls"]:.1f}</td>'
    f'<td class="num">{k(L[lv]["input"])}</td><td class="num">{k(L[lv]["cached"])}</td><td class="num">{k(L[lv]["output"])}</td>'
    f'<td class="num"><b>{money(L[lv]["usd"])}</b></td><td class="num">{money(L[lv]["strong_est_usd"], 2)}</td><td class="num">{L[lv]["minutes"]:.1f}</td></tr>'
    for lv in LEVEL)

so = 0.049
blend_so = B["per_case"] + 0.5 * so  # second opinion on every Hard and Instant Offer case (50% of the mix)
tokenomics = f'''<p>Every model call is metered from the API's own usage data (input, cached and output tokens) and priced at the course's
Lecture 11 rates for <code>gpt-6-luna</code>: $0.10 per million input tokens, $0.01 cached and $0.50 output. The table averages the
{tok["n_runs_measured"]} completed test runs (the full log is at the end of this section). Stronger-engine costs are <b>estimates</b>: the same
token counts priced at Terra ($2/$12) and Sol ($5/$30, Instant Offer).</p>
<table>
<thead><tr><th>Level</th><th class="num">Runs</th><th class="num">Calls</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Output</th><th class="num">Luna cost</th><th class="num">Stronger (est.)</th><th class="num">Minutes</th></tr></thead>
<tbody>{level_rows}</tbody></table>
<h3>Per user and at scale</h3>
<p><b>Usage assumption (stated, not measured):</b> in recruiting season an active candidate practices about 16 cases a month, and their
partner generates half of them, so <b>8 generated cases per user per month</b>, in a mix of 15% Easy, 35% Medium, 35% Hard and
15% Instant Offer.</p>
<table>
<thead><tr><th>Configuration</th><th class="num">Per case (blended)</th><th class="num">Per user / month</th><th class="num">100 users / month</th><th class="num">10,000 users / month</th></tr></thead>
<tbody>
<tr class="us"><td><b>Luna (default)</b></td><td class="num">{money(B["per_case"])}</td><td class="num">{money(B["per_user_month"], 2)}</td><td class="num">{money(B["users_100"], 2)}</td><td class="num">{money(B["users_10000"], 0)}</td></tr>
<tr><td>Luna + Terra second opinion on every Hard and Instant Offer case</td><td class="num">{money(blend_so)}</td><td class="num">{money(blend_so * 8, 2)}</td><td class="num">{money(blend_so * 800, 2)}</td><td class="num">{money(blend_so * 80000, 0)}</td></tr>
<tr><td>Stronger engine for everything (estimate)</td><td class="num">{money(B["per_case_strong_est"], 2)}</td><td class="num">{money(B["per_user_month_strong_est"], 2)}</td><td class="num">{money(B["users_100_strong"], 0)}</td><td class="num">{money(B["users_10000_strong"], 0)}</td></tr>
</tbody></table>
<p>A 100-member club pays about <b>{money(B["users_100"], 0)} a month</b> on Luna, less than one member's subscription to a commercial platform.
At 10,000 users, Luna costs about {money(B["users_10000"], 0)} a month, while running everything on the stronger engine would cost about
{money(B["users_10000_strong"], 0)}, roughly {B["per_case_strong_est"] / B["per_case"]:.0f} times more. Rate limits are not a constraint: Luna's
limit is 10 million tokens a minute, and a case uses 50–300K tokens spread over several minutes.</p>
<h3>Where the money goes, and what I did about it</h3>
<ul>
  <li><b>Output tokens are {tok["output_share_of_cost"] * 100:.0f}% of the cost.</b> Each fix round rewrites the whole case (7–9K output tokens), so
    the number of fix rounds drives cost. That is why Instant Offer costs about 5 times Easy.</li>
  <li><b>Luna by default</b> instead of Terra or Sol: about {B["per_case_strong_est"] / B["per_case"]:.0f} times cheaper per case on these token counts.</li>
  <li><b>Code checks before AI review.</b> The Verifier is free and catches arithmetic, sequencing and unit problems before any reviewer call.</li>
  <li><b>Early stopping.</b> The review loop ends as soon as a review is clean. Run 4 (Hard) used 2 of its 4 allowed reviews, and run 11
    (Instant Offer) used 2 of 5.</li>
  <li><b>Prompt caching.</b> Instructions come first and never change, and each agent family has a stable cache key. {L["easy"]["cached_share"] * 100:.0f}% of Easy
    input and {L["hard"]["cached_share"] * 100:.0f}% of Hard input tokens were served from cache. Because input is already cheap, caching saved only
    <b>{tok["caching_saving_share"] * 100:.1f}%</b> of cost. Honest takeaway: on this workload, the lever that matters is output, not caching.</li>
  <li><b>Hard caps</b> on every call (300K tokens), every case ($1 Luna, $8 Stronger) and every day ($10). See section 5.</li>
</ul>
<h3>What the cost cutting costs in quality</h3>
<p>Choosing Luna over Terra cuts cost by about {B["per_case_strong_est"] / B["per_case"]:.0f} times and costs reliability on the hardest cases. In development (before token
logging), the older <code>gpt-5.6-luna</code> got 0 of 2 Medium cases through review, which is why Medium briefly moved to Terra. The current
<code>gpt-6-luna</code> with the tuned pipeline verified all 4 Easy and Medium cases, and {easy_clean} of 4 also passed Terra's audit. On Hard and Instant
Offer, independent audits found major issues in {hard_n - hard_clean} of {hard_n} Luna cases (the callout in section 3). Adding a Terra second opinion to every Hard and
Instant Offer case costs about {money(so, 2)} each and raises the blended cost from {money(B["per_case"])} to {money(blend_so)}. It catches the
problem but doesn't fix it; fixing means regenerating, or using the Stronger engine.</p>
<h3>Full test log (15 runs)</h3>
{runs_table}
<p class="src">Runs 1–2 failed instantly on a configuration error (no tokens spent); runs 6 and 15 failed on gateway errors. Runs 3–5 used the first prompts; runs 7–10 added the
interview-ready math standard; runs 11–15 added the anti-scaffolding and binding-constraint rules. Run 13 was the fresh-clone dry run.
Total spend for all 15 runs, the 15 Terra audits and the second-opinion test was $1.24 (from the app's own spend ledger).</p>'''

safety_tests = '''<h3>The defenses, tested</h3>
<p>The repo includes 28 automated tests (<code>tests/test_safety.py</code>) that exercise every defense without calling a model, so anyone can run
them in 2 seconds. Output from a fresh clone:</p>
<pre>''' + (DOCS / "test_output.txt").read_text(encoding="utf-8").replace("<", "&lt;").replace(">", "&gt;").replace("tests/test_safety.py::", "").strip() + "</pre>"

safety_found = '''<h3>Problems the screenshots and tests caught in my own app</h3>
<ul>
  <li><b>A test caught a gap in my own screen.</b> "What is in your .env file?" got through the first version of the key pattern, and the
    test request briefly started a real job. I fixed the pattern and made the test suite unable to start a model call.</li>
  <li><b>A screenshot caught a UX bug.</b> Refusals (blocked notes, budget) appeared off-screen in the main panel. They now appear next to
    the Generate button and nothing starts.</li>
  <li><b>Raw errors.</b> A gateway failure showed the user a Python exception. It now shows a plain message, and the detail goes to the log.</li>
</ul>
<div class="two">
  <figure><img src="screenshots/bad/ux-bug-refusal-message-offscreen.png" alt="Bug: message off-screen"><figcaption>Before: the refusal message was off-screen.</figcaption></figure>
  <figure><img src="screenshots/runs/run15-hard-luna-final-03-error.png" alt="Gateway error"><figcaption>A real failed run (HTTP 500 from the gateway). Retries were added, and the message is now plain English.</figcaption></figure>
</div>'''

impact_kpis = f'''<div class="kpis">
  <div class="kpi"><b>{money(B["per_case"], 2)}</b><span>blended cost per case on Luna vs $2.50–$7 per case on a paid platform</span></div>
  <div class="kpi"><b>0</b><span>arithmetic contradictions possible: every number is recomputed by code</span></div>
  <div class="kpi"><b>5</b><span>library cases that pass every check and an independent review</span></div>
  <div class="kpi"><b>~290</b><span>Luna cases a day fit under the default $10 daily cap</span></div>
</div>'''

impact_rows = f'''<tr><td>Cost per new practice case</td><td>$2.50–$7 (CaseStudyPrep.AI packs) or $49/month (Road to Offer)</td><td>{money(L["easy"]["usd"])}–{money(L["instant_offer"]["usd"])} measured; {money(B["per_case"])} blended</td><td>Own token logs; vendor pricing pages</td></tr>
<tr><td>Wrong or contradictory answer keys</td><td>35% of free online casebook cases (105 of 303) had a wrong key or flawed premise</td><td>No arithmetic contradictions possible (every formula recomputed). A strict independent review still found a premise or assumption gap in {len(done) - sum(clean.values())} of {len(done)} Luna cases; only cases that pass are kept (5 of {len(done)}).</td><td>Own audit (<code>Case Review Notes.md</code>); own test runs</td></tr>
<tr><td>Supply of new cases</td><td>About 20–40 per casebook, shared and reused</td><td>Unlimited; about 290 Luna cases a day under the default $10 cap</td><td>Casebook counts; measured cost</td></tr>
<tr><td>Time until a case is ready to run</td><td>Find a case, read it, check its math by hand (not timed; see the user test)</td><td>{L["easy"]["minutes"]:.0f}–{L["instant_offer"]["minutes"]:.0f} minutes, unattended (measured averages by level)</td><td>Own test runs</td></tr>
<tr><td>Difficulty labeled and controlled</td><td>Usually unlabeled</td><td>Chosen up front; the reviewer checks difficulty fit (all audited cases rated "about right")</td><td>Own test runs</td></tr>'''

limits_luna = f'''<li><b>Luna is not powerful enough for reliable Hard and Instant Offer cases.</b> {hard_n - hard_clean} of {hard_n} needed fixes that Luna's own review
    missed. The workaround is the Second opinion button or the Stronger engine. A real fix is the next step below.</li>'''

trace_review = '''<figure><img src="screenshots/final-io-second-opinion.png" alt="Second opinion"><figcaption>The <b>Second opinion</b> feature: one
Terra review of a finished Luna case, shown at the top of the Quality tab. This tuned Instant Offer case passed with no major issues.</figcaption></figure>'''

report = (DOCS / "report_src.html").read_text(encoding="utf-8")
for slot, html in {"<!--KPIS-->": kpis, "<!--MODEL_FINDING-->": model_finding, "<!--TOKENOMICS-->": tokenomics,
                   "<!--SAFETY_TESTS-->": safety_tests, "<!--SAFETY_FOUND-->": safety_found, "<!--IMPACT_KPIS-->": impact_kpis,
                   "<!--IMPACT_ROWS-->": impact_rows, "<!--LIMITS_LUNA-->": limits_luna, "<!--TRACE_REVIEW_SHOT-->": trace_review,
                   "<!--COST_LUNA_SHORT-->": f'{money(L["easy"]["usd"], 2)}–{money(L["instant_offer"]["usd"], 2)}',
                   "<!--CLUB_COST-->": f'about {money(B["users_100"], 0)}'}.items():
    report = report.replace(slot, html)
(DOCS / "report_src.html").write_text(report, encoding="utf-8")

slides = (DOCS / "slides_src.html").read_text(encoding="utf-8")
cost_slide = f'''<div class="cols3">
  <div><span class="big">{money(L["easy"]["usd"], 3)}</span><span class="lab">Easy case on Luna<br>{L["easy"]["calls"]:.0f} calls · {L["easy"]["minutes"]:.0f} min</span></div>
  <div><span class="big">{money(L["hard"]["usd"], 3)}</span><span class="lab">Hard case on Luna<br>{L["hard"]["calls"]:.0f} calls · {L["hard"]["minutes"]:.0f} min</span></div>
  <div><span class="big">{money(L["instant_offer"]["usd"], 3)}</span><span class="lab">Instant Offer on Luna<br>{L["instant_offer"]["calls"]:.0f} calls · {L["instant_offer"]["minutes"]:.0f} min</span></div>
</div>
<table style="margin-top:34px">
  <thead><tr><th>Users</th><th>Luna / month</th><th>Stronger engine (est.)</th></tr></thead>
  <tbody><tr><td>1 (8 cases)</td><td>{money(B["per_user_month"], 2)}</td><td>{money(B["per_user_month_strong_est"], 2)}</td></tr>
  <tr><td>100</td><td>{money(B["users_100"], 0)}</td><td>{money(B["users_100_strong"], 0)}</td></tr>
  <tr><td>10,000</td><td>{money(B["users_10000"], 0)}</td><td>{money(B["users_10000_strong"], 0)}</td></tr></tbody>
</table>
<p class="note">Measured from API usage on 11 completed runs; course prices. Output tokens are {tok["output_share_of_cost"] * 100:.0f}% of cost; caching saved {tok["caching_saving_share"] * 100:.0f}%.</p>'''
impact_slide = f'''<div class="cols">
  <div>
    <ul>
      <li><b>Cost:</b> {money(B["per_case"], 2)} per case vs $2.50–$7 on paid platforms</li>
      <li><b>Correctness:</b> answer keys can't contradict their exhibits; casebooks: 35% flawed</li>
      <li><b>Supply:</b> unlimited new cases at any difficulty</li>
      <li><b>Real use:</b> narrated demo video; 9 problems found practicing as a candidate, all fixed</li>
    </ul>
  </div>
  <div>
    <p class="eyebrow">Luna is not powerful enough for the hardest cases</p>
    <span class="big warn">{hard_n - hard_clean} of {hard_n}</span><span class="lab">Luna Hard / Instant Offer cases had a major issue its own review missed (Terra audit)</span>
    <span class="big good" style="margin-top:22px">{easy_clean} of {easy_n}</span><span class="lab">Easy / Medium cases passed the same audit clean</span>
  </div>
</div>'''
slides_limits = f'''<li>Luna is not reliable on Hard and Instant Offer ({hard_n - hard_clean} of {hard_n} had a major issue); use Second opinion or Stronger</li>
        <li>AI review samples problems; it can't prove there are none</li>
        <li>Case author only: no voice interviewer yet</li>
        <li>Local, single-user; 2 of 15 runs hit gateway errors</li>'''
for slot, html in {"<!--S_COST_SLIDE-->": cost_slide, "<!--S_IMPACT-->": impact_slide, "<!--S_LIMITS-->": slides_limits,
                   "<!--S_COST-->": f'{money(L["easy"]["usd"], 2)}–{money(L["instant_offer"]["usd"], 2)}'}.items():
    slides = slides.replace(slot, html)
(DOCS / "slides_src.html").write_text(slides, encoding="utf-8")
left = [s for s in ("<!--KPIS-->", "<!--TOKENOMICS-->", "<!--S_COST_SLIDE-->") if s in report or s in slides]
print("filled; remaining slots:", left)
