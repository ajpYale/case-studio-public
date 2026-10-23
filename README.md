# McKennel & Co.

**A Yale SOM–styled generator of full, interviewer-ready MBB consulting practice cases — with an
answer key that is checked by code before you ever see it.**

The app has three rooms, in Yale blue with Handsome Dan as the mascot:

- **Run room.** Pick a difficulty (Easy · Puppy, Medium · Bulldog, Hard · Top Dog, Instant Offer · Handsome Dan) and how
  many cases (1–6, or one of each level). A team of AI agents plans, writes, checks and reviews each
  complete case: read-aloud prompt, clarifying answers, framework, exhibits (tables and charts),
  worked math, model answers, hints, pushback, a recommendation and a scoring rubric. Cases run in
  parallel, and each one's live card shows the agent at work, tokens, cache rate and dollars spent.
- **Library.** Every case, with its verification and second-opinion status. Open a case for the
  interviewer guide, candidate handouts, quality check and PDF.
- **Practice with Handsome Dan.** "Give me a case" and Handsome Dan, an AI interviewer agent, runs a library case with
  you: he reads the prompt, answers clarifying questions from the case, hands over exhibits when you
  reach them, pushes back, and a Scorer agent grades you on the case's rubric. The browser never
  receives the answer key, and a code guard stops Handsome Dan from stating results you haven't calculated.
  About half a cent per interview on Luna. Pick **Stronger** before starting to have Terra play Handsome Dan and score
  you: it follows the interviewing rules more closely, for about 15¢ an interview. You can also dictate your replies
  and have Handsome Dan read the prompt or everything aloud in a regal or calm voice.

Handsome Dan's eyes follow your pointer and a small Handsome Dan trots along the bottom of the screen
(hover him and click **Leash** to hide him). Visitors who don't go to Yale should not click the button in
the footer.

**Public copy.** This repository leaves out the knowledge pack distilled from MBA casebooks, so the app
runs on the hand-written starter pack (see below). Everything else is the same as the course submission. Report and slides: `docs/report.html` and `docs/slides.html`
(open by double-clicking).

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

**Optional — run the tests** (36 safety tests plus 2 page checks, no model calls, about 2 seconds):
```
.venv\Scripts\python -m pytest -v        (Windows)
.venv/bin/python -m pytest -v            (Mac / Linux)
```

---

## Models: Luna by default, stronger models as an option

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
printed by headless Microsoft Edge or Google Chrome; if neither is installed the case is still saved
and the app says the PDF couldn't be made. Set `CASEGEN_BROWSER` to a browser path if needed.

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
2. **An independent reviewer agent** audits the case against the quality rules and the requested
   difficulty, including whether every step can be done by hand, and its findings are fixed and
   re-checked. A final review gives the verdict: *Verified*, *Reviewer flags remain* or
   *Needs attention*.
3. **Optional second opinion** from the stronger model (see above).

## Layout

```
case_generator/
├── backend/
│   ├── main.py            FastAPI app, parallel job queue, live job board, spending guards
│   ├── generator.py       agents and the plan → write → check → review pipeline; token/cost meter
│   ├── verify.py          safe formula evaluator, consistency checks, rendering
│   ├── interviewer.py     practice mode: Interviewer (Handsome Dan) and Scorer agents, leak guard
│   ├── safety.py          screening of user notes (prompt injection)
│   ├── export.py          PDF export (headless Edge/Chrome)
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
