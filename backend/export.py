"""Save a generated case as a PDF in Project/Generated Cases.

The PDF is the app's own print view (interviewer guide, then candidate handouts, each handout on
its own page), printed by headless Microsoft Edge or Chrome, so it looks exactly like the app.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent


def _default_export_dir() -> Path:
    # The author keeps PDFs in a "Generated Cases" folder next to the repo; a fresh clone has no
    # such folder, so PDFs go inside the repo instead (git-ignored).
    beside = REPO_DIR.parent / "Generated Cases"
    return beside if beside.is_dir() else REPO_DIR / "Generated Cases"


EXPORT_DIR = Path(os.environ.get("CASEGEN_EXPORT_DIR") or _default_export_dir())
LEVEL_LABEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "instant_offer": "Instant Offer"}

_BROWSERS = [
    os.environ.get("CASEGEN_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    *(shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "msedge")),
]


# "auto" prints PDFs on the server with headless Edge/Chrome when one is installed; "off" never does
# (e.g. on a hosted server), and the app falls back to the browser's own Print / Save as PDF.
PDF_MODE = os.environ.get("CASEGEN_PDF", "auto").strip().lower()
NO_SERVER_PDF = ("Server-side PDFs aren't available here ({why}). Use “Print / Save as PDF” in the case view: "
                 "your browser's print dialog can save the same document as a PDF.")


class ExportError(RuntimeError):
    pass


def browser_path() -> str | None:
    return next((b for b in _BROWSERS if b and Path(b).exists()), None)


def available() -> bool:
    """Whether this server can print PDFs itself."""
    return PDF_MODE != "off" and browser_path() is not None


def pdf_name(difficulty: str, title: str) -> str:
    safe = " ".join("".join(c for c in title if c not in '<>:"/\\|?*').split()).rstrip(". ") or "Untitled"
    return f"{LEVEL_LABEL.get(difficulty, difficulty)} - {safe}.pdf"


def _unique(path: Path, case_id: str) -> Path:
    if not path.exists():
        return path
    return path.with_name(f"{path.stem} ({case_id[-6:]}){path.suffix}")


async def export_pdf(case_id: str, difficulty: str, title: str, base_url: str, existing: str | None = None) -> str:
    """Print the case to EXPORT_DIR and return the file name."""
    if not re.fullmatch(r"[0-9A-Za-z-]+", case_id):
        raise ExportError("bad case id")
    if PDF_MODE == "off":
        raise ExportError(NO_SERVER_PDF.format(why="CASEGEN_PDF=off"))
    browser = browser_path()
    if not browser:
        raise ExportError(NO_SERVER_PDF.format(why="no Edge or Chrome found; set CASEGEN_BROWSER to its path"))
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = EXPORT_DIR / existing if existing else _unique(EXPORT_DIR / pdf_name(difficulty, title), case_id)
    if target.exists():  # re-saving: remove the old file so we don't mistake it for the new one
        target.unlink()
    url = f"{base_url.rstrip('/')}/?print={case_id}"
    # Throwaway profile: never touches the user's browser data. On Windows, Edge's helper processes
    # can still hold a cache file when we finish, so a failed cleanup must not fail the case.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = await asyncio.create_subprocess_exec(
            browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={profile}", "--no-pdf-header-footer", "--virtual-time-budget=20000",
            f"--print-to-pdf={target}", url,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=90)
        except asyncio.TimeoutError:
            proc.kill()
            raise ExportError("PDF export timed out")
        # On Windows the launcher can exit before the renderer finishes writing, so wait for the
        # file to appear and stop growing (and keep the temp profile alive until it has).
        last, stable = -1, 0
        for _ in range(240):  # up to ~60 s
            size = target.stat().st_size if target.exists() else -1
            stable = stable + 1 if size == last and size > 2000 else 0
            if stable >= 4:
                return target.name
            last = size
            await asyncio.sleep(0.25)
    raise ExportError("PDF export produced no file")


def remove_pdf(name: str | None) -> None:
    if name and "/" not in name and "\\" not in name:
        p = EXPORT_DIR / name
        if p.exists():
            p.unlink()
