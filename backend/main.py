"""McKennel & Co. API and web app.

Run from inside the backend/ folder:

    ..\\.venv\\Scripts\\uvicorn main:app --port 8409

then open http://localhost:8409.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import casebook
import exhibits
import export
import generator
import importer
import interviewer
import live
import progress
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _restore_jobs()  # cases that were mid-generation when the server stopped
    await _restore_batch()  # and a batch conversion that was still feeding cases in
    yield


app = FastAPI(title="McKennel & Co.", lifespan=lifespan)

# Live partner mode lets a phone on the same network open the candidate view, which means starting
# the server with --host 0.0.0.0. Other devices then get only that read-only view: everything that
# spends money or shows the answer key stays limited to this computer.
LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_REMOTE_OK = re.compile(r"^/(?:live/[A-Za-z0-9_-]{12,32}|api/live/[A-Za-z0-9_-]{12,32}(?:/images/ex\d{1,3}\.png)?"
                        r"|static/[\w./-]+)$")


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    local = host in LOCAL_CLIENTS or host.startswith("::ffff:127.") or host.startswith("127.")
    if not local and not (request.method == "GET" and _REMOTE_OK.match(request.url.path)):
        return JSONResponse({"detail": "Only the candidate view of a live case is available from other devices."},
                            status_code=403)
    return await call_next(request)


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
    status: str = "queued"          # queued | running | done | error | interrupted
    stages: list[dict] = field(default_factory=list)
    case_id: str | None = None
    error: str | None = None
    meter: generator.Meter | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    retried_as: str | None = None   # the new job started by Retry
    import_ref: str | None = None   # a casebook case being converted, instead of a case being written
    import_title: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "request": self.request.model_dump(), "base_url": self.base_url, "status": self.status,
                "stages": self.stages, "case_id": self.case_id, "error": self.error, "created": self.created,
                "started": self.started, "finished": self.finished, "retried_as": self.retried_as,
                "import_ref": self.import_ref, "import_title": self.import_title,
                "model": self.meter.model if self.meter else None,
                "budget_usd": self.meter.budget_usd if self.meter else None,
                "steps": self.meter.steps if self.meter else []}

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        req = GenerateRequest.model_validate(d["request"])
        meter = generator.Meter(d.get("model") or generator.model_for(req.difficulty, req.engine),
                                d.get("budget_usd") or generator.MAX_USD_PER_CASE[req.engine])
        meter.steps = list(d.get("steps") or [])  # earlier spend still counts against the case's cap
        return cls(id=d["id"], request=req, base_url=d.get("base_url") or "http://localhost:8409/",
                   status=d.get("status", "queued"), stages=list(d.get("stages") or []), case_id=d.get("case_id"),
                   error=d.get("error"), meter=meter, created=d.get("created") or time.time(),
                   started=d.get("started"), finished=d.get("finished"), retried_as=d.get("retried_as"),
                   import_ref=d.get("import_ref"), import_title=d.get("import_title"))

    def view(self) -> dict:
        """Everything the run board shows, including live tokens and dollars while the job runs."""
        u = self.meter.summary() if self.meter else None
        cur = (u or {}).get("current")
        now = self.finished or time.time()
        out = {"id": self.id, "status": self.status, "stages": self.stages, "case_id": self.case_id, "error": self.error,
               "retried_as": self.retried_as, "import_title": self.import_title,
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
                           source=(case.get("source") or {}).get("kind"),
                           fix_rounds=case["quality"]["fix_rounds"])
            else:  # the case was deleted from BAIN after it finished
                out.update(title="(deleted from BAIN)", case_id=None)
        return out


JOBS: dict[str, Job] = {}
# A few cases at once keeps cost and rate limits predictable; a few more may wait in line, and
# anything beyond that is refused so a script hammering the button can't queue up a bill.
PARALLEL = max(1, min(int(os.environ.get("CASEGEN_PARALLEL", "3")), 6))
GENERATION_SLOTS = asyncio.Semaphore(PARALLEL)
MAX_PENDING_JOBS = PARALLEL + 3


JOBS_PATH = generator.BACKEND_DIR / "jobs.json"
KEEP_JOBS_SECONDS = 2 * 86400  # the board (and the file) keeps the last two days


def _persist() -> None:
    """Write the job board to disk so a restart can pick up where it left off."""
    cutoff = time.time() - KEEP_JOBS_SECONDS
    data = [j.to_dict() for j in JOBS.values() if j.created >= cutoff or j.status in ("queued", "running")]
    try:
        tmp = JOBS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JOBS_PATH)
    except OSError as exc:  # never let bookkeeping break a generation
        print(f"couldn't save the job board: {exc}")


async def _restore_jobs() -> None:
    """Reload the board after a restart. A case that was mid-generation starts over (its earlier spend
    still counts against its cap), except on an expensive model, which waits for the user to retry
    and confirm the cost again."""
    try:
        data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    cutoff = time.time() - KEEP_JOBS_SECONDS
    for d in data:
        try:
            job = Job.from_dict(d)
        except Exception as exc:  # a damaged entry shouldn't stop the rest
            print(f"skipped a saved job: {exc}")
            continue
        if job.id in JOBS or (job.created < cutoff and job.status not in ("queued", "running")):
            continue
        JOBS[job.id] = job
        if job.status not in ("queued", "running"):
            continue
        if generator.needs_cost_confirmation(job.request.difficulty, job.request.engine):
            job.status, job.finished = "interrupted", time.time()
            job.error = "Interrupted by a server restart. Press Retry to run it again; you'll be asked to confirm the cost first."
        elif generator.spent_today() >= generator.DAILY_USD_BUDGET:
            job.status, job.finished = "interrupted", time.time()
            job.error = "Interrupted by a server restart, and today's model budget is used up."
        else:
            job.status, job.started, job.finished = "queued", None, None
            job.stages.append({"stage": "Resumed after a server restart (starting over)",
                               "at": datetime.now(timezone.utc).isoformat()})
            asyncio.create_task(_run(job))
    _persist()


async def _run(job: Job) -> None:
    async def progress(stage: str) -> None:
        job.stages.append({"stage": stage, "at": datetime.now(timezone.utc).isoformat()})
        _persist()

    async with GENERATION_SLOTS:
        job.status, job.started = "running", time.time()
        _persist()
        try:
            if job.import_ref:
                job.case_id = await importer.convert(job.import_ref, progress, job.meter)
            else:
                job.case_id = await generator.generate(job.request, progress, job.meter)
            if export.available():
                await progress("Saving the PDF to Generated Cases")
                await _save_pdf(job.case_id, job.base_url)
            job.status = "done"
        except generator.BudgetExceeded as exc:
            job.status, job.error = "error", f"Stopped to protect the budget: {exc}."
        except Exception as exc:  # surface any failure to the UI instead of a silent hang
            job.status, job.error = "error", _friendly(exc)
        finally:
            job.finished = time.time()
            _persist()


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
    return {**generator.options(), "server_pdf": export.available()}


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
    _persist()
    asyncio.create_task(_run(job))
    return {"job_id": job.id}


class RetryRequest(BaseModel):
    confirm_cost: bool = False


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, body: RetryRequest, request: Request) -> dict:
    """Run a failed or interrupted case again with the same settings (as a new job, under every usual guard)."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    if job.status not in ("error", "interrupted") or job.retried_as:
        raise HTTPException(409, "Only a failed or interrupted case can be retried, once.")
    if job.import_ref:
        started = _start_conversion(job.import_ref, request)
    else:
        started = await create_case(job.request.model_copy(update={"confirm_cost": body.confirm_cost}), request)
    job.retried_as = started["job_id"]
    _persist()
    return started


@app.get("/api/jobs")
def list_jobs() -> dict:
    """The run board: every job since the server started, newest first, with live cost."""
    jobs = sorted(JOBS.values(), key=lambda j: j.created, reverse=True)
    return {"jobs": [j.view() for j in jobs], "parallel": PARALLEL, "max_pending": MAX_PENDING_JOBS,
            "spent_today_usd": round(generator.spent_today(), 4), "daily_budget_usd": generator.DAILY_USD_BUDGET}


@app.post("/api/jobs/clear")
def clear_jobs() -> dict:
    """Take every finished card off the board. Only the board entries go: the cases stay in the library."""
    gone = [k for k, j in JOBS.items() if j.status not in ("queued", "running")]
    for k in gone:
        del JOBS[k]
    _persist()
    return {"cleared": len(gone)}


@app.delete("/api/jobs/{job_id}")
def dismiss_job(job_id: str) -> dict:
    """Take one finished card off the board (its case stays in the library)."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    if job.status in ("queued", "running"):
        raise HTTPException(409, "That case is still being generated.")
    del JOBS[job_id]
    _persist()
    return {"dismissed": job_id}


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
    rendered = verify.render(draft, vals)
    for e in rendered["exhibits"]:  # a converted casebook case keeps each exhibit's original image too
        if e["id"] in (case.get("images") or {}):
            e["image_url"] = f"/api/cases/{case_id}/images/{e['id']}.png"
    return {"id": case["id"], "created_at": case["created_at"], "request": case["request"],
            "case": rendered, "quality": case["quality"], "usage": case.get("usage"), "second_opinion": case.get("second_opinion"),
            "pdf": case.get("pdf"), "pdf_folder": str(export.EXPORT_DIR), "flags": case.get("flags", []),
            "source": case.get("source")}


@app.get("/api/cases/{case_id}/images/{eid}.png")
def case_image(case_id: str, eid: str) -> FileResponse:
    case = generator.load_case(case_id)
    try:
        path = importer.image_path(case or {}, eid)
    except KeyError as exc:
        raise HTTPException(404, "No such image") from exc
    return FileResponse(path, media_type="image/png")


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


@app.get("/api/progress")
def get_progress() -> dict:
    return progress.summary()


@app.post("/api/progress/wipe")
def wipe_progress() -> dict:
    """Clear the practice history (it's archived, so the most recent clear can be undone)."""
    try:
        return progress.wipe()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/progress/undo-wipe")
def undo_wipe_progress() -> dict:
    try:
        return progress.undo_wipe()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/practice/{sid}")
def practice_get(sid: str) -> dict:
    s = interviewer.load(sid)
    if not s:
        raise HTTPException(404, "No such session")
    return interviewer.view(s)


@app.get("/api/practice/{sid}/images/{eid}.png")
def practice_image(sid: str, eid: str) -> FileResponse:
    s = interviewer.load(sid)
    if not s or eid not in s["released"]:
        raise HTTPException(404, "That exhibit hasn't been handed over")
    try:
        path = importer.image_path(generator.load_case(s["case_id"]) or {}, eid)
    except KeyError as exc:
        raise HTTPException(404, "No such image") from exc
    return FileResponse(path, media_type="image/png")


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


# ------------------------------------------------------------------ problem reports ("flag an error")

class FlagRequest(BaseModel):
    category: str
    note: str = Field("", max_length=500)
    where: str = Field("", max_length=80)


class FlagUpdate(BaseModel):
    resolved: bool


def _screen_report(note: str) -> None:
    # Open reports are shown to the reviewer agent on later cases, so they get the same screening as notes.
    if note and safety.screen_notes(note):
        raise HTTPException(422, "Reports can only describe a problem with the case. This one was blocked because it "
                                 "looks like instructions to the AI, or contains links, keys or code.")


@app.post("/api/cases/{case_id}/flags")
def flag_case(case_id: str, body: FlagRequest) -> dict:
    _screen_report(body.note)
    try:
        return generator.add_flag(case_id, body.category, body.note, body.where, source="library")
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/cases/{case_id}/flags/{flag_id}")
def update_flag(case_id: str, flag_id: str, body: FlagUpdate) -> dict:
    try:
        return generator.set_flag_resolved(case_id, flag_id, body.resolved)
    except KeyError as exc:
        raise HTTPException(404, "No such case or report") from exc


@app.get("/api/flag-categories")
def flag_categories() -> dict:
    return generator.FLAG_CATEGORIES


@app.post("/api/practice/{sid}/flag")
def practice_flag(sid: str, body: FlagRequest) -> dict:
    _screen_report(body.note)
    try:
        return interviewer.flag(sid, body.category, body.note)
    except KeyError as exc:
        raise HTTPException(404, "No such session") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


# ------------------------------------------------------------------ live partner mode

class LiveStart(BaseModel):
    case_id: str


class LivePrompt(BaseModel):
    shown: bool


class LiveExhibit(BaseModel):
    released: bool


def _live(token: str) -> dict:
    s = live.load(token)
    if not s:
        raise HTTPException(404, "No such live case")
    return s


@app.post("/api/live")
def live_start(body: LiveStart, request: Request) -> dict:
    try:
        s = live.create(body.case_id)
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc
    return live.host_view(s, str(request.base_url))


@app.get("/api/live/{token}/images/{eid}.png")
def live_case_image(token: str, eid: str) -> FileResponse:
    s = _live(token)
    if s.get("source") == "casebook" or eid not in s.get("released", []):
        raise HTTPException(404, "That exhibit hasn't been shared")
    try:
        path = importer.image_path(generator.load_case(s["case_id"]) or {}, eid)
    except KeyError as exc:
        raise HTTPException(404, "No such image") from exc
    return FileResponse(path, media_type="image/png")


@app.get("/api/casebook")
def casebook_list() -> dict:
    converted = importer.converted_map()
    return {**casebook.folder_info(), "cases": [{**c, "converted": converted.get(c["id"])} for c in casebook.cases()]}


class FolderRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


@app.post("/api/casebook/folder")
def casebook_set_folder(body: FolderRequest) -> dict:
    try:
        return casebook.set_folder(body.path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/casebook/folder")
def casebook_reset_folder() -> dict:
    return casebook.reset_folder()


def _start_conversion(cid: str, request: Request | str) -> dict:
    """Queue a conversion as a job on the BCG board (live progress and cost, retry, survives restarts)."""
    for j in JOBS.values():
        if j.import_ref == cid and j.status in ("queued", "running"):
            return {"job_id": j.id}  # already converting: don't pay twice
    if generator.spent_today() >= generator.DAILY_USD_BUDGET:
        raise HTTPException(429, f"Today's ${generator.DAILY_USD_BUDGET:.2f} model budget is used up.")
    if sum(j.status in ("queued", "running") for j in JOBS.values()) >= MAX_PENDING_JOBS:
        raise HTTPException(429, f"{MAX_PENDING_JOBS} cases are already being generated. Wait for one to finish.")
    try:
        meta = casebook.meta(cid)
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc
    job = Job(id=uuid.uuid4().hex[:10], request=GenerateRequest(difficulty=meta.get("level") or "medium"),
              base_url=request if isinstance(request, str) else str(request.base_url),
              meter=generator.Meter(generator.LUNA_MODEL, importer.MAX_USD_PER_IMPORT),
              import_ref=cid, import_title=meta["title"])
    JOBS[job.id] = job
    _persist()
    asyncio.create_task(_run(job))
    return {"job_id": job.id}


# ------------------------------------------------------------------ converting many casebook cases at once

BATCH_PATH = generator.BACKEND_DIR / "batch.json"
BATCH: dict | None = None
USD_PER_CONVERSION = (0.01, 0.025)  # measured range per case, finding exhibits included


def _save_batch() -> None:
    try:
        BATCH_PATH.write_text(json.dumps(BATCH), encoding="utf-8")
    except OSError as exc:
        print(f"couldn't save the batch: {exc}")


def batch_view() -> dict:
    """Where a batch conversion stands, counted from its jobs on the board."""
    if not BATCH:
        return {"status": "none"}
    jobs = [JOBS[j] for j in BATCH["jobs"].values() if j in JOBS]
    return {"id": BATCH["id"], "status": BATCH["status"], "reason": BATCH.get("reason"), "total": BATCH["total"],
            "waiting": len(BATCH["queue"]), "remaining": BATCH["queue"],
            "converting": sum(j.status in ("queued", "running") for j in jobs),
            "converted": sum(j.status == "done" for j in jobs),
            "failed": sum(j.status in ("error", "interrupted") for j in jobs),
            "skipped": len(BATCH["skipped"]), "usd": round(sum(j.meter.usd for j in jobs if j.meter), 4)}


async def _run_batch() -> None:
    """Feed the batch's conversions onto the board as slots free up. Stops when cancelled or when today's
    budget runs out; anything not started stays listed so the batch can be resumed."""
    b = BATCH
    while b is BATCH and b["status"] == "running" and b["queue"]:
        if generator.spent_today() >= generator.DAILY_USD_BUDGET:
            b["status"], b["reason"] = "stopped", f"Today's ${generator.DAILY_USD_BUDGET:.2f} budget is used up."
            break
        if sum(j.status in ("queued", "running") for j in JOBS.values()) >= MAX_PENDING_JOBS:
            await asyncio.sleep(2)
            continue
        cid = b["queue"].pop(0)
        if importer.converted_from(cid):
            b["skipped"].append(cid)
        else:
            try:
                b["jobs"][cid] = _start_conversion(cid, b["base_url"])["job_id"]
            except HTTPException as exc:
                b["queue"].insert(0, cid)
                if exc.status_code != 429:
                    b["status"], b["reason"] = "stopped", str(exc.detail)
                else:
                    await asyncio.sleep(2)
        _save_batch()
    while b is BATCH and any(JOBS[j].status in ("queued", "running") for j in b["jobs"].values() if j in JOBS):
        await asyncio.sleep(2)
    if b is BATCH and b["status"] == "running":
        b["status"] = "done"
    _save_batch()


class BatchRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=1000)


@app.get("/api/casebook/convert-batch")
def batch_status() -> dict:
    return batch_view()


@app.post("/api/casebook/convert-batch")
async def batch_start(body: BatchRequest, request: Request) -> dict:
    """Convert many casebook cases (the UI asks the user to confirm the count and the cost first)."""
    global BATCH
    if BATCH and BATCH["status"] == "running":
        raise HTTPException(409, "A batch conversion is already running. Stop it first.")
    if generator.spent_today() >= generator.DAILY_USD_BUDGET:
        raise HTTPException(429, f"Today's ${generator.DAILY_USD_BUDGET:.2f} model budget is used up.")
    converted = importer.converted_map()
    queue = []
    for cid in dict.fromkeys(body.ids):  # unique, in the order given
        try:
            casebook.path_of(cid)
        except KeyError:
            continue
        if cid not in converted:
            queue.append(cid)
    if not queue:
        raise HTTPException(409, "All of those cases are converted already.")
    BATCH = {"id": uuid.uuid4().hex[:8], "status": "running", "reason": None, "total": len(queue), "queue": queue,
             "jobs": {}, "skipped": [], "base_url": str(request.base_url), "started": time.time()}
    _save_batch()
    asyncio.create_task(_run_batch())
    return batch_view()


@app.post("/api/casebook/convert-batch/stop")
def batch_stop() -> dict:
    """Stop feeding new conversions. Ones already converting finish (they're paid for); the rest stay listed."""
    if BATCH and BATCH["status"] == "running":
        BATCH["status"], BATCH["reason"] = "cancelled", "Stopped by you."
        _save_batch()
    return batch_view()


async def _restore_batch() -> None:
    global BATCH
    try:
        BATCH = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if BATCH.get("status") == "running":
        asyncio.create_task(_run_batch())


class ConvertRequest(BaseModel):
    again: bool = False  # convert again even if this case was converted before


@app.post("/api/casebook/{cid}/convert")
async def casebook_convert(cid: str, body: ConvertRequest, request: Request) -> dict:
    """Turn a casebook case into a full case in BAIN (about 2-5 cents on Luna). Returns the case if it
    was converted before, else the job converting it."""
    try:
        casebook.path_of(cid)
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc
    if not body.again and (done := importer.converted_from(cid)):
        return {"case_id": done}
    return _start_conversion(cid, request)


@app.get("/api/casebook/{cid}/file")
def casebook_file(cid: str) -> FileResponse:
    """The whole casebook PDF, for the interviewer to read on this computer."""
    try:
        path = casebook.path_of(cid)
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")


@app.get("/api/live/{token}")
def live_candidate(token: str) -> dict:
    """The candidate's read-only view. The only API route other devices may call."""
    try:
        return live.candidate_view(_live(token))
    except KeyError as exc:  # the case was deleted
        raise HTTPException(404, "This case is no longer in the library") from exc


@app.get("/api/live/{token}/host")
def live_host(token: str, request: Request) -> dict:
    return live.host_view(_live(token), str(request.base_url))


@app.post("/api/live/{token}/prompt")
def live_prompt(token: str, body: LivePrompt, request: Request) -> dict:
    s = _live(token)
    live.set_prompt(s, body.shown)
    return live.host_view(s, str(request.base_url))


@app.post("/api/live/{token}/exhibits/{exhibit_id}")
def live_exhibit(token: str, exhibit_id: str, body: LiveExhibit, request: Request) -> dict:
    s = _live(token)
    try:
        live.set_exhibit(s, exhibit_id, body.released)
    except KeyError as exc:
        raise HTTPException(404, "No such exhibit") from exc
    return live.host_view(s, str(request.base_url))


@app.get("/live/{token}")
def live_page(token: str) -> FileResponse:
    _live(token)
    return FileResponse(STATIC_DIR / "live.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/bulldog-security")
def bulldog_security() -> FileResponse:
    """For visitors who don't go to Yale."""
    return FileResponse(STATIC_DIR / "trap.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
