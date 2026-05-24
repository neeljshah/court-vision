"""tests/test_fetch_injury_report.py — unit tests for the NBA injury PDF scraper.

These tests never hit the network and never parse a real PDF:
* HTTP is replaced by a fake `requests.Session` stub.
* `pdfplumber` is bypassed by monkey-patching `_extract_text` with a
  canned text fixture that mimics the layout of a real injury report.

Run:
    python -m pytest tests/test_fetch_injury_report.py -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import fetch_injury_report as fir


# ---------------------------------------------------------------------------
# Test 1 — URL builder produces the expected NBA CDN pattern.
# ---------------------------------------------------------------------------

def test_build_pdf_url_matches_nba_cdn_pattern() -> None:
    """The URL must match official.nba.com's exact path scheme."""
    d = date(2026, 5, 24)
    url = fir.build_pdf_url(d, "05PM")
    assert url == (
        "https://official.nba.com/wp-content/uploads/sites/4/"
        "2026/05/Injury-Report-2026-05-24_05PM.pdf"
    )

    # Single-digit month/day must be zero-padded.
    early = fir.build_pdf_url(date(2026, 1, 3), "01PM")
    assert "/2026/01/Injury-Report-2026-01-03_01PM.pdf" in early

    # build_pdf_filename mirrors the same zero-padding contract.
    assert fir.build_pdf_filename(d, "08PM") == "Injury-Report-2026-05-24_08PM.pdf"


# ---------------------------------------------------------------------------
# Test 2 — Parser extracts status/team/name/reason from a canned line block.
# ---------------------------------------------------------------------------

_CANNED_PDF_TEXT = """\
Injury Report: 2026-05-24 05:30 PM

Game Date Game Time Matchup Team Player Name Current Status Reason
Los Angeles Lakers James, LeBron QUESTIONABLE Foot; Soreness
Los Angeles Lakers Davis, Anthony OUT Knee; Sprain
Boston Celtics Tatum, Jayson PROBABLE Ankle; Soreness
Boston Celtics Brown, Jaylen AVAILABLE Wrist; Injury Management
Golden State Warriors Curry, Stephen DOUBTFUL Illness
"""


def test_parse_injury_text_extracts_expected_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_injury_text must convert canned PDF text to typed dicts."""
    rows = fir.parse_injury_text(_CANNED_PDF_TEXT)

    # Every status row above should resolve — five real player lines.
    assert len(rows) == 5

    by_name = {r["name"]: r for r in rows}
    assert by_name["LeBron James"]["team"] == "LAL"
    assert by_name["LeBron James"]["status"] == "QUESTIONABLE"
    assert by_name["LeBron James"]["reason"] == "Foot; Soreness"

    assert by_name["Anthony Davis"]["team"] == "LAL"
    assert by_name["Anthony Davis"]["status"] == "OUT"

    assert by_name["Jayson Tatum"]["team"] == "BOS"
    assert by_name["Jayson Tatum"]["status"] == "PROBABLE"

    assert by_name["Jaylen Brown"]["team"] == "BOS"
    assert by_name["Jaylen Brown"]["status"] == "AVAILABLE"

    assert by_name["Stephen Curry"]["team"] == "GSW"
    assert by_name["Stephen Curry"]["status"] == "DOUBTFUL"

    # Every status emitted must be one of the canonical tokens.
    for r in rows:
        assert r["status"] in {"OUT", "DOUBTFUL", "QUESTIONABLE",
                                "PROBABLE", "AVAILABLE", "NOT WITH TEAM"}


# ---------------------------------------------------------------------------
# Test 3 — fetch_pdf_bytes walks back through time slots and uses cached HTTP.
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Stand-in for requests.Response used by the fake session below."""

    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content


class _FakeSession:
    """Replays a scripted set of responses keyed by URL so tests can
    assert latest-first walk-back behaviour without hitting the network."""

    def __init__(self, scripted: dict) -> None:
        self._scripted = scripted
        self.calls: list = []

    def get(self, url: str, timeout: int = 30) -> _FakeResponse:  # noqa: D401
        self.calls.append(url)
        return self._scripted.get(url, _FakeResponse(404))


def test_fetch_pdf_bytes_walks_back_on_404(tmp_path) -> None:
    """When 08PM is missing, we should fall back to 05PM (latest-first)."""
    d = date(2026, 5, 24)
    pdf_bytes = b"%PDF-1.4 fake body"
    url_08 = fir.build_pdf_url(d, "08PM")
    url_05 = fir.build_pdf_url(d, "05PM")

    sess = _FakeSession({
        url_08: _FakeResponse(404),
        url_05: _FakeResponse(200, pdf_bytes),
    })
    result = fir.fetch_pdf_bytes(d, str(tmp_path), session=sess)
    assert result is not None
    body, slot = result
    assert slot == "05PM"
    assert body == pdf_bytes
    # 08PM tried first, 05PM second; 01PM never reached.
    assert sess.calls == [url_08, url_05]

    # Cached file must be written under the slot that actually resolved.
    cached = tmp_path / fir.build_pdf_filename(d, "05PM")
    assert cached.exists()
    assert cached.read_bytes() == pdf_bytes


# ---------------------------------------------------------------------------
# Test 4 — end-to-end fetch_and_parse with mocked HTTP + mocked PDF extraction.
# ---------------------------------------------------------------------------

def test_fetch_and_parse_writes_expected_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire a fake session + stub the pdfplumber pass; assert the JSON shape."""
    d = date(2026, 5, 24)
    pdf_bytes = b"%PDF-1.4 fake body"
    url_08 = fir.build_pdf_url(d, "08PM")
    sess = _FakeSession({url_08: _FakeResponse(200, pdf_bytes)})

    monkeypatch.setattr(fir, "_extract_text", lambda _b: _CANNED_PDF_TEXT)

    out = fir.fetch_and_parse(d, project_dir=str(tmp_path), session=sess)
    assert out is not None
    assert os.path.exists(out)

    with open(out) as f:
        payload = json.load(f)
    assert payload["date"] == "2026-05-24"
    assert payload["source_pdf"] == "Injury-Report-2026-05-24_08PM.pdf"
    assert "fetched_at" in payload
    assert len(payload["players"]) == 5
    assert payload["players"][0]["name"] == "LeBron James"
