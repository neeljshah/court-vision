"""test_L21_lineup.py — Tests for L21_lineup_watcher.py

Nine tests using mocked HTTP via monkeypatch on _http_get; no live network calls.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_TEST_DIR    = Path(__file__).resolve().parent
_LOOP_DIR    = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L21_lineup_watcher as L21  # noqa: E402

# ── HTML fixtures ─────────────────────────────────────────────────────────────

# 5 confirmed starters for LAL
_LINEUPS_COM_5_HTML = """
<html><body>
  <div class="lineup__abbr">LAL</div>
  <ul class="lineup__list is-home">
    <li class="lineup__player"><a href="#">LeBron James</a></li>
    <li class="lineup__player"><a href="#">Anthony Davis</a></li>
    <li class="lineup__player"><a href="#">Austin Reaves</a></li>
    <li class="lineup__player"><a href="#">D'Angelo Russell</a></li>
    <li class="lineup__player"><a href="#">Jarred Vanderbilt</a></li>
  </ul>
</body></html>
"""

# Only 3 starters listed for BOS (partial)
_ROTOWIRE_PARTIAL_HTML = """
<html><body>
  <div class="lineup__abbr">BOS</div>
  <ul class="lineup__list is-home">
    <li class="lineup__player"><a href="#">Jayson Tatum</a></li>
    <li class="lineup__player"><a href="#">Jaylen Brown</a></li>
    <li class="lineup__player"><a href="#">Al Horford</a></li>
  </ul>
</body></html>
"""

# Surprise: Player_X is confirmed but not in top-5 fpts
_FPTS_DATA_WITH_SURPRISE = {
    "Star One":   {"mean": 55.0, "team": "LAL"},
    "Star Two":   {"mean": 50.0, "team": "LAL"},
    "Star Three": {"mean": 48.0, "team": "LAL"},
    "Star Four":  {"mean": 45.0, "team": "LAL"},
    "Star Five":  {"mean": 40.0, "team": "LAL"},
    # not in confirmed_starters → benched_expected
    "Player_X":   {"mean": 39.0, "team": "LAL"},
}

# Starters that match with a surprise (Player_New) and missing (Star Five)
_CONFIRMED_STARTERS_WITH_SURPRISE = [
    "star one", "star two", "star three", "star four",
    "player_new",  # surprise — not in top-5 fpts
]


# ── helper ────────────────────────────────────────────────────────────────────
def _mock_http(html: str):
    """Return a patcher that replaces L21._http_get with a callable returning html."""
    return patch.object(L21, "_http_get", return_value=html)


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — fetch_confirmed_lineups with 5-starter HTML → ≥1 LineupConfirmation
# ══════════════════════════════════════════════════════════════════════════════
def test_fetch_returns_lineup_confirmation(tmp_path, monkeypatch):
    """fetch_confirmed_lineups with mocked lineups.com HTML (5 LAL starters)
    returns ≥1 LineupConfirmation with exactly 5 confirmed_starters."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        # first call (lineups.com) returns valid HTML; subsequent → empty
        if call_count[0] == 1:
            return _LINEUPS_COM_5_HTML
        return ""

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    results = L21.fetch_confirmed_lineups(date="2026-05-25")

    assert len(results) >= 1, "Expected at least one LineupConfirmation"
    lal = next((c for c in results if c.team == "LAL"), None)
    assert lal is not None, "Expected a LineupConfirmation for LAL"
    assert len(lal.confirmed_starters) == 5, (
        f"Expected 5 starters, got {len(lal.confirmed_starters)}"
    )
    assert "lebron james" in lal.confirmed_starters
    assert lal.source == "lineups.com"


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — diff_against_expected: Player_X top-5 but NOT confirmed → benched;
#           surprise starter present
# ══════════════════════════════════════════════════════════════════════════════
def test_diff_against_expected_detects_surprise_and_benched():
    """diff_against_expected correctly identifies a surprise starter
    (confirmed but not top-5) and a benched expected (top-5 but not confirmed)."""
    conf = L21.LineupConfirmation(
        team="LAL",
        confirmed_starters=_CONFIRMED_STARTERS_WITH_SURPRISE,
        source="lineups.com",
        timestamp="2026-05-25T00:00:00+00:00",
    )

    result = L21.diff_against_expected(conf, _FPTS_DATA_WITH_SURPRISE)

    # "player_new" is confirmed but NOT in top-5 fpts → surprise
    assert "player_new" in result["surprise_starters"], (
        f"Expected 'player_new' in surprise_starters; got {result['surprise_starters']}"
    )
    # "star five" is top-5 fpts but NOT confirmed → benched
    assert "star five" in result["benched_expected"], (
        f"Expected 'star five' in benched_expected; got {result['benched_expected']}"
    )
    # in-place mutation
    assert conf.surprise_starters == result["surprise_starters"]
    assert conf.benched_expected  == result["benched_expected"]


# ══════════════════════════════════════════════════════════════════════════════
# Test 3 — alert_on_surprises with monkeypatched send_alert called per surprise
# ══════════════════════════════════════════════════════════════════════════════
def test_alert_on_surprises_calls_send_alert(monkeypatch):
    """alert_on_surprises calls send_alert once per surprise starter
    with channel='news'."""
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr(L21, "send_alert", mock_send)

    conf = L21.LineupConfirmation(
        team="LAL",
        confirmed_starters=["player_new", "star one", "star two", "star three", "star four"],
        surprise_starters=["player_new"],
        benched_expected=["star five"],
        source="rotowire",
        timestamp="2026-05-25T00:00:00+00:00",
    )

    n = L21.alert_on_surprises([conf])

    assert n == 1, f"Expected 1 alert, got {n}"
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    # channel must be "news"
    channel_arg = (
        call_kwargs.kwargs.get("channel")
        if call_kwargs.kwargs
        else (call_kwargs.args[0] if call_kwargs.args else None)
    )
    assert channel_arg == "news", f"Expected channel='news', got channel='{channel_arg}'"


# ══════════════════════════════════════════════════════════════════════════════
# Test 4 — Partial lineup (3 starters) → note contains "partial"
# ══════════════════════════════════════════════════════════════════════════════
def test_partial_lineup_note(tmp_path, monkeypatch):
    """When only 3 starters appear in HTML, returned confirmation.note
    contains the word 'partial'."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return ""  # lineups.com empty
        return _ROTOWIRE_PARTIAL_HTML  # rotowire returns 3 starters

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    results = L21.fetch_confirmed_lineups(date="2026-05-25")

    bos = next((c for c in results if c.team == "BOS"), None)
    assert bos is not None, "Expected LineupConfirmation for BOS"
    assert len(bos.confirmed_starters) == 3
    assert "partial" in bos.note.lower(), (
        f"Expected 'partial' in note, got '{bos.note}'"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 5 — Empty/blocked HTTP → returns [], no exception, WARN logged
# ══════════════════════════════════════════════════════════════════════════════
def test_all_sources_blocked_returns_empty(tmp_path, monkeypatch, caplog):
    """When all HTTP sources return '' and no seed exists,
    fetch_confirmed_lineups returns [] and logs a warning."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)
    monkeypatch.setattr(L21, "_http_get", lambda url: "")

    with caplog.at_level(logging.WARNING, logger="L21_lineup_watcher"):
        results = L21.fetch_confirmed_lineups(date="2026-05-25")

    assert results == [], f"Expected [], got {results}"
    # At least one WARN about blocked sources
    warn_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warn_records, "Expected at least one WARNING log when all sources blocked"


# ══════════════════════════════════════════════════════════════════════════════
# Test 6 — New confirmed lineup publishes a "lineup.confirmed" event
# ══════════════════════════════════════════════════════════════════════════════
def test_new_lineup_publishes_event(tmp_path, monkeypatch):
    """When a team appears for the first time, _publish_lineup_event is called
    with previously_unknown=True and the correct game_id / team / starters."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return _LINEUPS_COM_5_HTML
        return ""

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    published: list = []

    def _fake_publish(game_id, team, starters, confirmed_at, previously_unknown):
        published.append({
            "game_id": game_id,
            "team": team,
            "starters": starters,
            "previously_unknown": previously_unknown,
        })

    monkeypatch.setattr(L21, "_publish_lineup_event", _fake_publish)

    results = L21.fetch_confirmed_lineups(date="2026-05-25")

    assert len(results) >= 1
    assert len(published) >= 1, "Expected at least one event published for new lineup"
    lal_events = [e for e in published if e["team"] == "LAL"]
    assert lal_events, "Expected a lineup.confirmed event for LAL"
    assert lal_events[0]["game_id"] == "2026-05-25"
    assert lal_events[0]["previously_unknown"] is True
    assert "lebron james" in lal_events[0]["starters"]


# ══════════════════════════════════════════════════════════════════════════════
# Test 7 — No new lineup → no event published
# ══════════════════════════════════════════════════════════════════════════════
def test_no_new_lineup_publishes_nothing(tmp_path, monkeypatch):
    """When the persisted snapshot already contains the same starters as the
    freshly fetched data, _publish_lineup_event is NOT called."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    # Pre-seed the persisted file with LAL's 5 starters (already known)
    existing = {
        "LAL": {
            "team": "LAL",
            "confirmed_starters": [
                "lebron james", "anthony davis", "austin reaves",
                "d'angelo russell", "jarred vanderbilt",
            ],
            "surprise_starters": [],
            "benched_expected": [],
            "source": "lineups.com",
            "timestamp": "2026-05-25T00:00:00+00:00",
            "note": "",
        }
    }
    (tmp_path / "2026-05-25.json").write_text(json.dumps(existing), encoding="utf-8")

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return _LINEUPS_COM_5_HTML
        return ""

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    published: list = []

    def _fake_publish(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(L21, "_publish_lineup_event", _fake_publish)

    L21.fetch_confirmed_lineups(date="2026-05-25")

    assert published == [], (
        f"Expected no events for unchanged lineup; got {published}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 8 — EventBus publish failure does not break fetch
# ══════════════════════════════════════════════════════════════════════════════
def test_publish_failure_does_not_break_fetch(tmp_path, monkeypatch):
    """If _publish_lineup_event raises an exception, fetch_confirmed_lineups
    still returns its results (publish errors must not propagate)."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return _LINEUPS_COM_5_HTML
        return ""

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    def _exploding_publish(**kwargs):
        raise RuntimeError("bus is down")

    monkeypatch.setattr(L21, "_publish_lineup_event", _exploding_publish)

    # Should not raise despite publish exploding
    results = L21.fetch_confirmed_lineups(date="2026-05-25")

    lal = next((c for c in results if c.team == "LAL"), None)
    assert lal is not None, "LAL should still be returned even when publish fails"
    assert len(lal.confirmed_starters) == 5


# ══════════════════════════════════════════════════════════════════════════════
# Test 9 — Atomic write: tmp file replaced, no partial file left on disk
# ══════════════════════════════════════════════════════════════════════════════
def test_atomic_write(tmp_path, monkeypatch):
    """_persist writes a .tmp then atomically replaces the target JSON;
    no temporary file should remain after a successful persist."""
    monkeypatch.setattr(L21, "_LINEUP_DIR", tmp_path)

    call_count = [0]

    def _fake_http(url: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return _LINEUPS_COM_5_HTML
        return ""

    monkeypatch.setattr(L21, "_http_get", _fake_http)

    # Suppress event publication — not relevant to this test
    monkeypatch.setattr(L21, "_publish_lineup_event", lambda **kw: None)

    L21.fetch_confirmed_lineups(date="2026-05-25")

    final_file = tmp_path / "2026-05-25.json"
    assert final_file.exists(), "Persisted JSON file should exist after fetch"

    # No stray .tmp files should remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Stray .tmp files found: {tmp_files}"

    # The JSON should be valid and contain LAL
    data = json.loads(final_file.read_text(encoding="utf-8"))
    assert "LAL" in data, f"Expected LAL key in persisted JSON; got keys: {list(data)}"
