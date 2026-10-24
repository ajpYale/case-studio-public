"""The casebook room: give the real casebook cases (the ones the knowledge pack was built from) live.

The casebooks are copyrighted, so they never live in this repo: the app reads them from a local
folder and only on this computer. The folder is the one chosen in the app (saved in
backend/settings.json), else `CASEGEN_CASES_DIR`, else `../Cases` next to the repo; PDFs in its
subfolders count too. A candidate in live mode sees nothing but the individual pages the interviewer
shares, rendered as images. Cases are addressed by a short hash of folder and file, never by a path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import threading
import zlib
from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium

# pdfium isn't thread-safe, and the server renders thumbnails on several worker threads at once:
# every call into it goes through this lock (cached pages skip it).
_PDFIUM = threading.Lock()

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent
DEFAULT_CASES_DIR = Path(os.environ.get("CASEGEN_CASES_DIR") or REPO_DIR.parent / "Cases")
SETTINGS_PATH = BACKEND_DIR / "settings.json"  # git-ignored: the folder chosen in the app
ANNOTATIONS = REPO_DIR / "build_knowledge" / "work" / "annotations.jsonl"  # local only, from the knowledge build
PAGE_CACHE = BACKEND_DIR / "live" / "pages"
LEVEL_OF = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "instant_offer"}  # same as build_knowledge/distill.py
SCALES = {"thumb": 0.32, "full": 1.6}
MAX_FILES = 5000
_ID = re.compile(r"[0-9a-f]{12}")


def _saved_folder() -> Path | None:
    try:
        folder = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("cases_dir")
    except (OSError, json.JSONDecodeError):
        return None
    return Path(folder) if folder else None


CASES_DIR = _saved_folder() or DEFAULT_CASES_DIR


def _pdfs(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.pdf"))[:MAX_FILES] if folder.is_dir() else []


def available() -> bool:
    return CASES_DIR.is_dir() and any(CASES_DIR.rglob("*.pdf"))


def folder_info() -> dict:
    return {"folder": str(CASES_DIR), "default_folder": str(DEFAULT_CASES_DIR),
            "custom": CASES_DIR != DEFAULT_CASES_DIR, "available": available()}


def _reset_caches() -> None:
    _index.cache_clear()
    _page_count.cache_clear()


def _write_setting(folder: Path | None) -> None:
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        settings = {}
    if folder is None:
        settings.pop("cases_dir", None)
    else:
        settings["cases_dir"] = str(folder)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=1), encoding="utf-8")


def set_folder(path: str) -> dict:
    """Point the casebook room at another folder of case PDFs (this computer only)."""
    global CASES_DIR
    folder = Path(path.strip().strip('"')).expanduser()
    if not folder.is_absolute():
        raise ValueError("Give the folder's full path, e.g. C:\\Users\\you\\Documents\\Casebooks.")
    if not folder.is_dir():
        raise ValueError("That folder doesn't exist on this computer.")
    found = len(_pdfs(folder))
    if not found:
        raise ValueError("There are no PDF files in that folder (or its subfolders).")
    CASES_DIR = folder.resolve()
    _write_setting(CASES_DIR)
    _reset_caches()
    return {**folder_info(), "cases": found}


def reset_folder() -> dict:
    global CASES_DIR
    CASES_DIR = DEFAULT_CASES_DIR
    _write_setting(None)
    _reset_caches()
    return folder_info()


def _case_id(folder: Path, rel: str) -> str:
    # The folder is part of the id, so two folders with the same file names never share cached pages.
    return hashlib.sha1(f"{folder}|{rel}".encode("utf-8")).hexdigest()[:12]


def _split_name(stem: str) -> tuple[str, str, str]:
    """'School_2024-2025 Case Name' -> ('School', '2024-2025', 'Case Name'); a whole casebook
    named 'School_2024-2025' -> ('School', '2024-2025', 'Full casebook')."""
    m = re.match(r"^([^_\s]+)_(\S+)\s+(.*)$", stem)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.match(r"^([^_\s]+)_(\d{4}(?:-\d{4})?)$", stem)
    return (m.group(1), m.group(2), "Full casebook") if m else ("", "", stem)


@lru_cache(maxsize=1)
def _annotations() -> dict[str, dict]:
    if not ANNOTATIONS.exists():
        return {}
    out = {}
    for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            out[row["source"]] = row
        except (json.JSONDecodeError, KeyError):
            continue
    return out


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    if not available():
        return {}
    notes = _annotations()
    out = {}
    for pdf in _pdfs(CASES_DIR):
        rel = pdf.relative_to(CASES_DIR).as_posix()
        school, year, title = _split_name(pdf.stem)
        if not school and pdf.parent != CASES_DIR:  # "School/Case Name.pdf": the subfolder names the casebook
            school = pdf.parent.name
        a = notes.get(pdf.stem, {})
        cid = _case_id(CASES_DIR, rel)
        out[cid] = {"id": cid, "file": rel, "title": title, "school": school or "Other", "year": year,
                    "level": LEVEL_OF.get(a.get("assessed_difficulty")), "case_type": a.get("case_type"),
                    "industry": a.get("industry"), "format": a.get("format"), "exhibits": a.get("num_exhibits")}
    return out


def cases() -> list[dict]:
    return [{k: v for k, v in c.items() if k != "file"} for c in _index().values()]


def path_of(cid: str) -> Path:
    if not _ID.fullmatch(cid or "") or cid not in _index():
        raise KeyError(cid)
    return CASES_DIR / _index()[cid]["file"]


def meta(cid: str) -> dict:
    path = path_of(cid)
    c = {k: v for k, v in _index()[cid].items() if k != "file"}
    c["pages"] = _page_count(path)
    return c


@lru_cache(maxsize=512)
def _page_count(path: Path) -> int:
    with _PDFIUM:
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()


# ------------------------------------------------------------------ page images

def _png(width: int, height: int, pixels: bytes, stride: int, channels: int = 3) -> bytes:
    """A minimal PNG encoder for an RGB or RGBA bitmap (so no imaging library is needed)."""
    row = width * channels
    raw = b"".join(b"\x00" + pixels[y * stride:y * stride + row] for y in range(height))
    color_type = 6 if channels == 4 else 2

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def page_png(cid: str, page: int, size: str = "full") -> bytes:
    """One page as a PNG (1-based page numbers), cached on disk next to the live sessions."""
    if size not in SCALES:
        raise KeyError(size)
    path = path_of(cid)
    cached = PAGE_CACHE / f"{cid}-{page}-{size}.png"
    if cached.exists():
        return cached.read_bytes()
    with _PDFIUM:
        # Each cached page is written exactly once, here: re-check now that we hold the lock, so two
        # requests for the same page don't both render it (or replace a file another thread is reading).
        if cached.exists():
            return cached.read_bytes()
        pdf = pdfium.PdfDocument(str(path))
        try:
            if not 1 <= page <= len(pdf):
                raise KeyError(page)
            bitmap = pdf[page - 1].render(scale=SCALES[size], rev_byteorder=True)  # RGB(A) byte order
            data = _png(bitmap.width, bitmap.height, bytes(bitmap.buffer), bitmap.stride, bitmap.n_channels)
        finally:
            pdf.close()
        PAGE_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".tmp")  # a reader never sees a half-written file
        tmp.write_bytes(data)
        tmp.replace(cached)
    return data
