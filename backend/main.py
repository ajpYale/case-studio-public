"""McKennel & Co. API and web app.

Run from inside the backend/ folder:

    ..\\.venv\\Scripts\\uvicorn main:app --port 8409

then open http://localhost:8409.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import export
import generator
import interviewer
import safety
import verify
from models import CaseDraft, GenerateRequest

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLES_DIR = Path(__file__).resolve().parent / "sample_cases"


def _seed_library() -> None:
    """A fresh clone starts with a few finished example cases, so the app has something to show
    before anyone spends tokens. Only runs when the library is empty."""
    generator.GENERATED_DIR.mkdir(exist_ok=True)
    if SAMPLES_DIR.is_dir() and not any(generator.GENERATED_DIR.glob("*.json")):
        for f in SAMPLES_DIR.glob("*.json"):
            shutil.copy2(f, generator.GENERATED_DIR / f.name)


_seed_library()
app = FastAPI(title="McKennel & Co.")


@app.middleware("http")
async def no_stale_assets(request, call_next):
    # Always revalidate the page and its assets so an updated app never runs stale JS/CSS.
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@dataclass
class Job:
    id: str
    request: GenerateRequest
    base_url: str = "http://localhost:8409/"
    status: str = "queued"          # queued | running | done | error
    stages: list[dict] = field(default_factory=list)
    case_id: str | None = None
    error: str | None = None
    meter: generator.Meter | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None

    def view(self) -> dict:
        """Everything the run board shows, including live tokens and dollars while the job runs."""
        u = self.meter.summary() if self.meter else None
        cur = (u or {}).get("current")
        now = self.finished or time.time()
        out = {"id": self.id, "status": self.status, "stages": self.stages, "case_id": self.case_id, "error": self.error,
               "difficulty": self.request.difficulty if self.request else None,
               "engine": self.request.engine if self.request else None,
               "model": self.meter.model if self.meter else None,
               "elapsed": round(now - (self.started or now), 1), "waited": round((self.started or now) - self.created, 1),
               "calls": u["calls"] if u else 0, "input": u["input"] if u else 0, "cached": u["cached"] if u else 0,
               "output": u["output"] if u else 0, "usd": u["usd"] if u else 0.0,
               "budget_usd": self.meter.budget_usd if self.meter else None,
               "current": {"step": cur["step"], "role": cur["role"], "seconds": round(time.time() - cur["started"], 1),
                           "retry": cur.get("retry")} if cur else None}
        if self.case_id:
            case = generator.load_case(self.case_id)
            if case:
                out.update(title=case["draft"]["title"], quality=case["quality"]["status"],
                           fix_rounds=case["quality"]["fix_rounds"])
        return out


JOBS: dict[str, Job] = {}
# A few cases at once keeps cost and rate limits predictable; a few more may wait in line, and
# anything beyond that is refused so a script hammering the button can't queue up a bill.
PARALLEL = max(1, min(int(os.environ.get("CASEGEN_PARALLEL", "3")), 6))
GENERATION_SLOTS = asyncio.Semaphore(PARALLEL)
MAX_PENDING_JOBS = PARALLEL + 3


async def _run(job: Job) -> None:
    async def progress(stage: str) -> None:
        job.stages.append({"stage": stage, "at": datetime.now(timezone.utc).isoformat()})

    async with GENERATION_SLOTS:
        job.status, job.started = "running", time.time()
        try:
            job.case_id = await generator.generate(job.request, progress, job.meter)
            await progress("Saving the PDF to Generated Cases")
            await _save_pdf(job.case_id, job.base_url)
            job.status = "done"
        except generator.BudgetExceeded as exc:
            job.status, job.error = "error", f"Stopped to protect the budget: {exc}."
        except Exception as exc:  # surface any failure to the UI instead of a silent hang
            job.status, job.error = "error", _friendly(exc)
        finally:
            job.finished = time.time()


def _friendly(exc: Exception) -> str:
    """A plain-English failure message; the technical detail stays in the server log."""
    status = getattr(exc, "status_code", None)
    print(f"generation failed: {type(exc).__name__}: {exc}")
    if status and status >= 500:
        return ("The AI service had a temporary problem (HTTP %d) and still failed after several retries. "
                "Only the steps that finished were charged. Please try again in a minute." % status)
    if status == 429:
        return "The AI service is rate-limiting requests right now. Please try again in a minute."
    if status in (401, 403):
        return "The API key was rejected. Check PORTKEY_API_KEY in your .env file."
    return f"Generation failed: {type(exc).__name__}: {str(exc)[:300]}"


async def _save_pdf(case_id: str, base_url: str) -> str | None:
    """Export the case to Project/Generated Cases. A failed export never loses the case itself."""
    case = generator.load_case(case_id)
    if not case:
        return None
    try:
        name = await export.export_pdf(case_id, case["draft"]["difficulty"], case["draft"]["title"],
                                       base_url, existing=case.get("pdf"))
    except export.ExportError as exc:
        generator.update_case(case_id, pdf=None, pdf_error=str(exc))
        return None
    generator.update_case(case_id, pdf=name, pdf_error=None)
    return name


@app.get("/api/options")
def get_options() -> dict:
    return generator.options()


@app.post("/api/cases")
async def create_case(req: GenerateRequest, request: Request) -> dict:
    if generator.needs_cost_confirmation(req.difficulty, req.engine) and not req.confirm_cost:
        raise HTTPException(409, f"{generator.model_for(req.difficulty, req.engine)} is expensive; "
                                 "confirm the cost before generating this case.")
    if generator.spent_today() >= generator.DAILY_USD_BUDGET:
        raise HTTPException(429, f"Today's ${generator.DAILY_USD_BUDGET:.2f} model budget is used up. "
                                 "Try again tomorrow or raise CASEGEN_DAILY_USD_BUDGET.")
    if sum(j.status in ("queued", "running") for j in JOBS.values()) >= MAX_PENDING_JOBS:
        raise HTTPException(429, f"{MAX_PENDING_JOBS} cases are already being generated. Wait for one to finish.")
    if req.notes:
        problem = safety.screen_notes(req.notes)
        if problem:
            raise HTTPException(422, problem)
    job = Job(id=uuid.uuid4().hex[:10], request=req, base_url=str(request.base_url), meter=generator.new_meter(req))
    JOBS[job.id] = job
    asyncio.create_task(_run(job))
    return {"job_id": job.id}


@app.get("/api/jobs")
def list_jobs() -> dict:
    """The run board: every job since the server started, newest first, with live cost."""
    jobs = sorted(JOBS.values(), key=lambda j: j.created, reverse=True)
    return {"jobs": [j.view() for j in jobs], "parallel": PARALLEL, "max_pending": MAX_PENDING_JOBS,
            "spent_today_usd": round(generator.spent_today(), 4), "daily_budget_usd": generator.DAILY_USD_BUDGET}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    return job.view()


@app.get("/api/cases")
def list_cases() -> list[dict]:
    return generator.list_cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    case = generator.load_case(case_id)
    if not case:
        raise HTTPException(404, "No such case")
    # Re-render from the stored draft so formatting improvements apply to older cases too.
    draft = CaseDraft.model_validate(case["draft"])
    vals, _ = verify.check(draft)
    return {"id": case["id"], "created_at": case["created_at"], "request": case["request"],
            "case": verify.render(draft, vals), "quality": case["quality"], "usage": case.get("usage"), "second_opinion": case.get("second_opinion"),
            "pdf": case.get("pdf"), "pdf_folder": str(export.EXPORT_DIR)}


@app.get("/api/budget")
def get_budget() -> dict:
    return {"spent_today_usd": round(generator.spent_today(), 4), "daily_budget_usd": generator.DAILY_USD_BUDGET,
            "max_usd_per_case": generator.MAX_USD_PER_CASE}


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str) -> dict:
    case = generator.load_case(case_id)
    if not case or not generator.delete_case(case_id):
        raise HTTPException(404, "No such case")
    export.remove_pdf(case.get("pdf"))
    return {"deleted": case_id}


async def _practice_call(fn, *args) -> dict:
    """Run a practice action and turn its failures into clear HTTP errors."""
    if generator.spent_today() >= generator.DAILY_USD_BUDGET:
        raise HTTPException(429, f"Today's ${generator.DAILY_USD_BUDGET:.2f} model budget is used up.")
    try:
        result = fn(*args)
        return await result if asyncio.iscoroutine(result) else result
    except (KeyError, LookupError) as exc:
        raise HTTPException(404, str(exc).strip("'") if isinstance(exc, LookupError) and not isinstance(exc, KeyError)
                            else "No such case or session") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except generator.BudgetExceeded as exc:
        raise HTTPException(429, f"Stopped to protect the budget: {exc}.") from exc
    except Exception as exc:  # gateway errors and the like
        raise HTTPException(502, _friendly(exc)) from exc


@app.post("/api/practice")
async def practice_start(req: interviewer.PracticeRequest) -> dict:
    return await _practice_call(interviewer.start, req)


@app.get("/api/practice/{sid}")
def practice_get(sid: str) -> dict:
    s = interviewer.load(sid)
    if not s:
        raise HTTPException(404, "No such session")
    return interviewer.view(s)


@app.post("/api/practice/{sid}/message")
async def practice_message(sid: str, msg: interviewer.CandidateMessage) -> dict:
    return await _practice_call(interviewer.reply, sid, msg.text)


@app.post("/api/practice/{sid}/skip")
async def practice_skip(sid: str) -> dict:
    return await _practice_call(interviewer.skip, sid)


@app.post("/api/practice/{sid}/score")
async def practice_score(sid: str) -> dict:
    return await _practice_call(interviewer.score, sid)


@app.post("/api/cases/{case_id}/second-opinion")
async def second_opinion(case_id: str) -> dict:
    if not generator.load_case(case_id):
        raise HTTPException(404, "No such case")
    if generator.spent_today() >= generator.DAILY_USD_BUDGET:
        raise HTTPException(429, f"Today's ${generator.DAILY_USD_BUDGET:.2f} model budget is used up.")
    try:
        return await generator.second_opinion(case_id)
    except generator.BudgetExceeded as exc:
        raise HTTPException(429, str(exc)) from exc


@app.get("/api/cases/{case_id}/pdf/file")
async def pdf_file(case_id: str, request: Request) -> FileResponse:
    """The case's PDF as a download, so the browser can save it wherever the user chooses."""
    case = generator.load_case(case_id)
    if not case:
        raise HTTPException(404, "No such case")
    name = case.get("pdf")
    if not name or not (export.EXPORT_DIR / name).exists():
        name = await _save_pdf(case_id, str(request.base_url))
        if not name:
            raise HTTPException(500, generator.load_case(case_id).get("pdf_error") or "PDF export failed")
    return FileResponse(export.EXPORT_DIR / name, media_type="application/pdf", filename=name)


@app.post("/api/cases/{case_id}/pdf")
async def save_pdf(case_id: str, request: Request) -> dict:
    if not generator.load_case(case_id):
        raise HTTPException(404, "No such case")
    name = await _save_pdf(case_id, str(request.base_url))
    if not name:
        raise HTTPException(500, generator.load_case(case_id).get("pdf_error") or "PDF export failed")
    return {"pdf": name, "folder": str(export.EXPORT_DIR)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/bulldog-security")
def bulldog_security() -> FileResponse:
    """For visitors who don't go to Yale."""
    return FileResponse(STATIC_DIR / "trap.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
