"""Live partner mode: two people run a library case together.

The interviewer keeps the full guide on their screen; the candidate opens a link (or scans a QR
code) and sees only the read-aloud prompt once it's shown and the exhibits the interviewer has
released. No model calls. The candidate's link is an unguessable token and is read-only: every
control lives behind the interviewer's localhost-only endpoints (see main.local_only).
"""

from __future__ import annotations

import json
import re
import secrets
import socket
import time
from pathlib import Path

import segno

import generator
import verify
from models import CaseDraft

LIVE_DIR = generator.BACKEND_DIR / "live"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{12,32}")


def _path(token: str) -> Path:
    return LIVE_DIR / f"{token}.json"


def _save(s: dict) -> None:
    LIVE_DIR.mkdir(exist_ok=True)
    s["updated"] = time.time()
    _path(s["token"]).write_text(json.dumps(s, indent=1), encoding="utf-8")


def load(token: str) -> dict | None:
    if not _TOKEN.fullmatch(token or "") or not _path(token).exists():
        return None
    return json.loads(_path(token).read_text(encoding="utf-8"))


def _rendered(case_id: str) -> tuple[CaseDraft, dict]:
    case = generator.load_case(case_id)
    if case is None:
        raise KeyError(case_id)
    draft = CaseDraft.model_validate(case["draft"])
    vals, _ = verify.check(draft)
    return draft, verify.render(draft, vals)


def create(case_id: str) -> dict:
    _rendered(case_id)  # raises KeyError for an unknown case
    s = {"token": secrets.token_urlsafe(12), "case_id": case_id, "created": time.time(),
         "prompt_shown": False, "released": []}
    _save(s)
    return s


def candidate_view(s: dict) -> dict:
    """What the candidate's screen shows: no title (it can give the answer away), no guide."""
    draft, r = _rendered(s["case_id"])
    number = {e["id"]: i + 1 for i, e in enumerate(r["exhibits"])}
    order = {eid: i for i, eid in enumerate(s["released"])}
    images = (generator.load_case(s["case_id"]) or {}).get("images") or {}
    shown = sorted(({**e, "number": number[e["id"]]} for e in r["exhibits"] if e["id"] in order),
                   key=lambda e: order[e["id"]])
    exhibits = [e | ({"image_url": f"/api/live/{s['token']}/images/{e['id']}.png"} if e["id"] in images else {})
                for e in shown]
    return {"client": draft.client, "industry": draft.industry, "difficulty": draft.difficulty,
            "prompt": r["prompt"] if s["prompt_shown"] else None, "exhibits": exhibits, "updated": s.get("updated")}


def host_view(s: dict, base_url: str) -> dict:
    """The interviewer's controls: every exhibit with its release state, plus how to reach the candidate view."""
    draft, r = _rendered(s["case_id"])
    first_part = {}
    for k, sec in enumerate(draft.sections, 1):
        for eid in sec.exhibit_ids:
            first_part.setdefault(eid, k)
    links = links_for(s["token"], base_url)
    return {"token": s["token"], "case_id": s["case_id"], "prompt_shown": s["prompt_shown"],
            "exhibits": [{"id": e["id"], "number": i + 1, "title": e["title"], "part": first_part.get(e["id"]),
                          "released": e["id"] in s["released"]} for i, e in enumerate(r["exhibits"])],
            **links}


def set_prompt(s: dict, shown: bool) -> None:
    s["prompt_shown"] = bool(shown)
    _save(s)


def set_exhibit(s: dict, exhibit_id: str, released: bool) -> None:
    draft, _ = _rendered(s["case_id"])
    if exhibit_id not in {e.id for e in draft.exhibits}:
        raise KeyError(exhibit_id)
    if released and exhibit_id not in s["released"]:
        s["released"].append(exhibit_id)
    if not released and exhibit_id in s["released"]:
        s["released"].remove(exhibit_id)
    _save(s)


# ------------------------------------------------------------------------ reaching the candidate

def lan_ip() -> str | None:
    """This computer's address on the local network. Connecting a UDP socket sends no packets; it
    only asks the OS which interface it would use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def _listening(ip: str, port: int) -> bool:
    """True if the server also answers on the network address, i.e. it was started with --host 0.0.0.0."""
    try:
        with socket.create_connection((ip, port), timeout=0.3):
            return True
    except OSError:
        return False


def qr_svg(url: str) -> str:
    return segno.make(url, error="m").svg_data_uri(scale=5, border=2, dark="#00356b")


def links_for(token: str, base_url: str) -> dict:
    base = base_url.rstrip("/")
    port = int(base.rsplit(":", 1)[1]) if re.search(r":\d+$", base) else 80
    local = f"{base}/live/{token}"
    ip = lan_ip()
    lan = f"http://{ip}:{port}/live/{token}" if ip else None
    lan_ready = bool(ip and _listening(ip, port))
    return {"local_url": local, "lan_url": lan, "lan_ready": lan_ready,
            "qr": qr_svg(lan if lan_ready else local)}
