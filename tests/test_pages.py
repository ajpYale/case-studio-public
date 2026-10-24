"""The app's pages load (no model calls)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)


def test_main_page_has_all_three_rooms():
    html = client.get("/").text
    for room in ("Bulldog Case Generator", "BCG", "Bulldog Archive of INterviews", "BAIN", "Generated cases",
                 "Casebook cases", "Practice with Handsome Dan"):
        assert room in html


def test_bulldog_security_page_is_served_and_makes_no_model_calls():
    r = client.get("/bulldog-security")
    assert r.status_code == 200 and "Bulldog Security Forces" in r.text
    assert "/api/" not in r.text
