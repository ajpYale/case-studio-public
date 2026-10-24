# McKennel & Co.

> [!IMPORTANT]
> **Work in progress: please do not grade this branch.** This is the `post-submission` branch, where I am
> continuing to build the app after the course. The graded MGT 409 submission is the
> [`main` branch](https://github.com/ajpYale/case-studio/tree/main), which is unchanged since the deadline. Everything here is
> new work added afterwards and may change at any time.

**A Yale SOM–styled generator of full, interviewer-ready MBB consulting practice cases — with an
answer key that is checked by code before you ever see it.**

The app has three rooms, in Yale blue with Handsome Dan as the mascot:

- **Bulldog Case Generator (BCG).** Pick a difficulty (Easy · Puppy, Medium · Bulldog, Hard · Top Dog, Instant Offer · Handsome Dan) and how
  many cases (1–6, or one of each level). A team of AI agents plans, writes, checks and reviews each
  complete case: read-aloud prompt, clarifying answers, framework, exhibits (tables and charts),
  worked math, model answers, hints, pushback, a recommendation and a scoring rubric. Cases run in
  parallel, and each one's live card shows the agent at work, tokens, cache rate and dollars spent.
  Cases survive a server restart: an unfinished Luna case starts over by itself, and any case can be retried.
  Dismiss a card with ×, or **Clear finished** to empty the board (the cases stay in BAIN).
- **Bulldog Archive of INterviews (BAIN).** One tab, two sub-tabs. **Generated cases**: every case
  written here, with its verification, solver and second-opinion status and any open problem reports;
  open one for the interviewer guide, candidate handouts, quality check and PDF, or **Give this case
  live** to run it with a partner (see below). **Casebook cases**: the real casebook cases the app
  learned from, which you can convert into full cases like ours and give live (see "Casebook cases"
  below). Converted cases are listed there, not under Generated cases.
- **Practice with Handsome Dan.** "Give me a case" and Handsome Dan, an AI interviewer agent, runs a library case with
  you: he reads the prompt, answers clarifying questions from the case, hands over exhibits when you
  reach them, pushes back, and a Scorer agent grades you on the case's rubric. The browser never
  receives the answer key, and a code guard stops Handsome Dan from stating results you haven't calculated.
  About half a cent per interview on Luna. Pick **Stronger** before starting to have Terra play Handsome Dan and score
  you: it follows the interviewing rules more closely, for about 15¢ an interview. You can also dictate your replies
  and have Handsome Dan read the prompt or everything aloud in a regal or calm voice. A clock in the header tracks
  your time on each part against the case's length, and the scorecard shows your pacing.
- **Your progress.** The Practice tab tracks every scored interview: your average and trend, four skills
  (structuring, quant, business judgment, communication) across interviews, the case types you've practiced,
  and a suggested next case aimed at your weakest recent skill (**Practice this** starts it). **Clear my
  progress** asks first, then moves the scored interviews into `backend/progress_wipes/` instead of
  deleting them; **Undo last clear** puts them back (several clears undo one at a time, newest first).
- **Flag a problem.** From a case, a practice interview or a scorecard, report a wrong number, a missing fact or an
  unclear question. Reports show in the case's Quality tab, and open ones are given to the reviewer agent when
  new cases are written, so the same kind of problem gets caught next time.

Handsome Dan's eyes follow your pointer and a small Handsome Dan trots along the bottom of the screen
(hover him and click **Leash** to hide him). Visitors who don't go to Yale should not click the button in
the footer.

**Public copy.** This repository leaves out the knowledge pack distilled from MBA casebooks, so the app
runs on the hand-written starter pack (see below). It includes no casebooks or casebook cases either: the
Casebook cases tab works with a folder of case PDFs you already have. Everything else is the same as the
private repository. Report and slides: `docs/report.html` and `docs/slides.html`
(open by double-clicking).
Demo video at 2× speed (1:26, narrated): `docs/demo_2x.mp4`.

---

## Run it (about 5 minutes)

You need **Python 3.11 or newer** and a `PORTKEY_API_KEY`.

**1. Put the key where the app can find it.** The app reads `.env` from this repo folder first and
then from the folder **above** it, so the teaching staff's shared `.env` works as is:

```
some-folder/
├── .env                 <- PORTKEY_API_KEY=...   (either here)
└── case_generator/      <- this repo
    ├── .env             <- ...or here (copy .env.example)
    └── ...
```

**2. Install** (from inside the repo folder):

Windows (PowerShell or cmd):
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Mac / Linux:
```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**3. Start the app:**

Windows:
```
.venv\Scripts\python -m uvicorn main:app --app-dir backend --port 8409
```

Mac / Linux:
```
.venv/bin/python -m uvicorn main:app --app-dir backend --port 8409
```

**4. Open http://localhost:8409.** The library already holds five finished sample cases (one per
level, each checked by a stronger model). To make a new one, pick **Easy** and **Luna**, then
**Generate case** (about 3 minutes and about 1¢).

**Optional — run the tests** (67 tests, no model calls, a few seconds):
```
.venv\Scripts\python -m pytest -v        (Windows)
.venv/bin/python -m pytest -v            (Mac / Linux)
```

---

## Models: Luna by default, stronger models as an option

Professor Zaman approved offering stronger models alongside Luna as long as the app runs on Luna. Luna is
the default for every agent; Terra and Sol are used only when you opt in.

| Engine | Models | Measured cost per case | Time |
|---|---|---|---|
| **Luna** (default) | `gpt-6-luna` for every step | Easy $0.013 · Medium $0.029 · Hard $0.040 · Instant Offer $0.059 | 3–16 min |
| **Stronger** | `gpt-5.6-terra` (Easy–Hard), `gpt-5.6-sol` (Instant Offer) | about $0.30–$3.30 (estimate) | similar |

**Luna is not powerful enough to make Hard and Instant Offer cases reliably.** In testing, Luna's
own reviewer passed 6 of its 7 Hard and Instant Offer cases, but an independent review by
`gpt-5.6-terra` still found a major issue in 5 of the 7. Easy and Medium hold up (3 of 4 clean).
So for the top two levels, use one of the two upgrades:

- **Second opinion (Terra, ~5¢)**: a button on every finished case that runs one independent
  stronger-model review and shows its findings in the Quality tab. Nothing is rewritten.
- **Stronger engine**: writes the whole case on Terra/Sol. Sol is expensive, so every Sol run asks
  for confirmation first, and the server refuses a Sol run that wasn't confirmed.

## Spending limits

- **Per case:** a case stops if it would spend more than $1.00 on Luna or $8.00 on the Stronger engine.
- **Per day:** new cases are refused once the day's spend reaches $10.00.
- **Per call:** no single model call may use more than 300,000 tokens.
- **Queue:** 3 cases generate in parallel (`CASEGEN_PARALLEL`, up to 6) and at most 3 more wait.
- **Practice:** each interview stops at $0.50 or 60 messages.

All four are in `.env.example` and can be changed. Every case's Quality tab lists each model call
with its input, cached and output tokens and its cost.

## PDFs

Every new case is also saved as a PDF in a `Generated Cases` folder (inside the repo, or next to it
if one exists there): the interviewer guide, then each candidate handout on its own page. The PDF is
printed by headless Microsoft Edge or Google Chrome. Set `CASEGEN_BROWSER` to a browser path if needed.

Without Edge or Chrome on the server (or with `CASEGEN_PDF=off`, e.g. when hosting), nothing breaks:
cases are still saved, and **Print / Save as PDF** in the case view opens the same document in your own
browser's print dialog, where you can save it as a PDF.

## Live partner mode

Practice with a person instead of Handsome Dan. Open a case and click **Give this case live**. You
keep the full interviewer guide; your candidate scans the QR code (or opens the link) and sees only
what you hand over: the prompt when you show it, and each exhibit when you release it. Never the
guide, the answers or the case title. No model calls.

- **Second screen on the same computer:** works as is; open the link in another window.
- **Candidate's phone on the same Wi-Fi:** start the server so other devices can reach it, then the QR
  code points at your computer's network address:
  ```
  .venv\Scripts\python -m uvicorn main:app --app-dir backend --port 8409 --host 0.0.0.0
  ```
  Windows may ask whether to allow Python on private networks; allow it. Other devices can then open
  **only** a live case's candidate view: everything that spends money or shows an answer key answers
  them with "403 Forbidden", whatever they try.

## Casebook cases

The **Casebook cases** sub-tab of BAIN lists the real casebook cases the knowledge pack was built from (search by
name, school or industry; filter by level, casebook, case type, and whether it's converted yet).
**Raw PDF** opens the casebook's own pages.

**Convert** turns a casebook case into one of our own. First Luna looks at every page and finds the
exhibits (charts, tables, data handouts), leaving out interviewer notes and answers, and code crops
each one tight to the chart or table drawn in the PDF. Then Luna converts the case faithfully (the
casebook's story, numbers, questions, exhibits and answers) into an interviewer guide with worked
math, handouts, hints, pushback, a recommendation and a rubric; the number checks run with up to two
fix rounds (a fix that makes things worse is thrown away), and one independent review notes what's
shaky in the casebook case itself. About 1-2 cents and two minutes per case, shown live on the BCG
board; the job card's cost includes the exhibit finder. The converted case is marked "From casebook"
and runs exactly like a generated one; its card then offers **Open full case**, **Give Case** (the
full guide with the candidate's screen ready to share) and **Raw PDF**, and the case itself has
practice with Handsome Dan, PDF and flags. Each exhibit keeps
the casebook's original image (the default, since it's exact) with a **Show redrawn** toggle for the
app's own chart or table; the redrawn data is also what lets Handsome Dan and the reviewer read the
exhibits.

**Convert all shown** converts every case the current search and filters show (cases already converted
are skipped). A confirmation first shows the count, the expected cost and time, and what's left of
today's budget; nothing starts until you confirm. Three convert at a time while you keep using the
app, and a progress bar above the list shows how far it's got, with **Stop** (cases already converting
finish). The batch stops by itself before it would pass the day's $10 budget, and it picks up where
it left off after a server restart. Converting all 450 cases costs about $4.50–$11 on Luna.

The casebooks are copyrighted, so they are never part of this repo, and this public copy comes with none:
point the app at a folder of case PDFs you already have. It reads them from that folder and serves them
only to this computer. Click **Change folder** above the list to
point it at any folder of case PDFs (subfolders count, and a subfolder's name is used as the
casebook's name); the choice is saved in `backend/settings.json` (git-ignored), and **Use the
default** goes back. The default is `CASEGEN_CASES_DIR` if set, else `../Cases` next to the repo.

## How it learned from real casebooks

The full app uses `backend/knowledge/knowledge_pack.json` (not included in this public copy), distilled once from **449 audited practice cases in 32
MBA consulting casebooks**: difficulty calibration, an archetype library (each case's situation,
analytical engine, key insight and math, re-described in fresh words with no casebook text or client
names) and a house-style guide. `backend/prompts/quality_rules.md` adds the failure patterns found
while auditing those casebooks — about a third of the free online cases had a wrong answer key.

**The app never reads the casebooks**, and they are not in this repo (the clubs hold the
copyright). `build_knowledge/` holds the one-time scripts that built the pack; they need the case
PDFs in `../Cases/` and are only needed to rebuild it.

If `knowledge_pack.json` is absent (as in the public copy of this repo), the app falls back to
`backend/knowledge/starter_pack.json`: hand-written difficulty notes and style guide, no
archetypes and nothing derived from any casebook. Cases still go through every check and review.

## How it keeps the answer key right

Every number in a case is defined once, as an input or as a formula over inputs. Exhibit cells and
answer text pull from those formulas, so the key can't contradict its own exhibits. Then:

1. **Code checks** (`backend/verify.py`) recompute every formula with a safe arithmetic parser and
   flag wrong expected values, exhibit totals that don't add up, typed numbers that match nothing in
   the case, inputs used before the candidate is given them, inputs the candidate never sees,
   exhibits that give away the answer, math a candidate can't do by hand (powers above a cube),
   and duplicated sections. Problems go back to the writer (up to three rounds).
2. **A solver agent** works the case from the candidate's side only: the prompt, clarifying answers,
   shared facts and exhibits, never the key. Code compares each of its results with the key. A miss
   usually means a fact the candidate needs is missing or a question can be read two ways, the kind of
   premise gap model reviewers tend to miss, so misses go back to the writer before review, and the
   final result shows in the Quality tab ("Solver 7/8") and on the Library card.
3. **An independent reviewer agent** audits the case against the quality rules and the requested
   difficulty, including whether every step can be done by hand, and its findings are fixed and
   re-checked. A final review gives the verdict: *Verified*, *Reviewer flags remain* or
   *Needs attention*.
4. **Optional second opinion** from the stronger model (see above).

## Layout

```
case_generator/
├── backend/
│   ├── main.py            FastAPI app, parallel job queue, live job board, spending guards
│   ├── generator.py       agents and the plan → write → check → review pipeline; token/cost meter
│   ├── verify.py          safe formula evaluator, consistency checks, rendering
│   ├── solver.py          the solver check: candidate-only materials, answers vs the key
│   ├── interviewer.py     practice mode: Interviewer (Handsome Dan) and Scorer agents, leak guard, pacing
│   ├── live.py            live partner mode: the candidate's screen, QR code
│   ├── casebook.py        casebook cases: a local folder of PDFs, pages rendered as images
│   ├── exhibits.py        finds the exhibits in a casebook case (Luna vision + crop snapping)
│   ├── importer.py        converts a casebook case into a full case
│   ├── progress.py        practice progress over time, suggested next case, clear and undo
│   ├── safety.py          screening of user notes (prompt injection)
│   ├── export.py          PDF export (headless Edge/Chrome; browser print as the fallback)
│   ├── models.py          case schema
│   ├── prompts/           writer, reviewer, interviewer, scorer, difficulty levels, quality rules
│   ├── knowledge/         knowledge_pack.json (the distilled library), starter_pack.json (fallback)
│   ├── sample_cases/      example cases copied into an empty library on first start
│   ├── practice/          saved practice interviews (git-ignored)
│   └── static/            the web app: app.js (rooms), case_view.js, charts.js, dan.css, dan.svg
├── tests/                 safety and correctness tests (no model calls)
├── docs/                  report.html, slides.html, screenshots
└── build_knowledge/       one-time scripts that read the casebooks
```
