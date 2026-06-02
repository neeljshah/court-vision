"""tests/test_dk_scraper_live_gate.py — Bug A regression tests (data-loss-safe).

Invariant under test
---------------------
Live in-play DK category IDs (1686-1689) must NEVER be fetched/written under
book="dk" WHILE A GAME IS LIVE — that is the in-play contamination we prevent.
Pre-tip (no game live, OR liveness-detection failure treated as no-live), the
live categories MAY be used as an empty-fallback when a legacy pregame category
returns zero rows, so DK pregame coverage is never reduced vs. the original.

Cases
-----
(a) no-live + legacy 1215 non-empty -> uses legacy, never touches 1686.
(b) no-live + legacy 1215 empty     -> falls back to 1686 (data recovered).
(c) live game -> legacy only; 1686 NEVER fetched even if legacy is empty.
(d) _live_event_ids raises          -> behaves as no-live (fallback allowed).

These tests exercise the pure logic of one_snapshot() fully offline by
monkeypatching fetch_subcategory and the live-event detector.
"""
from __future__ import annotations

import sys
import os
import types
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root + scripts on sys.path
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for d in (PROJECT_DIR, SCRIPTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

# ---------------------------------------------------------------------------
# Stub curl_cffi so the module imports offline without the C extension
# ---------------------------------------------------------------------------
if "curl_cffi" not in sys.modules:
    curl_cffi_stub = types.ModuleType("curl_cffi")
    curl_cffi_requests_stub = types.ModuleType("curl_cffi.requests")
    curl_cffi_stub.requests = curl_cffi_requests_stub
    sys.modules["curl_cffi"] = curl_cffi_stub
    sys.modules["curl_cffi.requests"] = curl_cffi_requests_stub

import importlib

_dk_scraper = importlib.import_module("draftkings_scraper")
_dk_inplay = importlib.import_module("draftkings_inplay_scraper")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------
_EMPTY_PAYLOAD: dict = {"events": [], "markets": [], "selections": []}


def _ou_payload(player: str, line: float, over: int = -110,
                under: int = -110) -> dict:
    """Minimal pregame O/U payload that normalize() will emit one row from."""
    return {
        "events": [{"id": "ev1", "startEventDate": "2026-05-31T23:00:00Z"}],
        "markets": [{"id": "m1", "eventId": "ev1"}],
        "selections": [
            {
                "marketId": "m1", "label": "Over", "points": line,
                "id": "selOver",
                "displayOdds": {"american": str(over)},
                "participants": [{"type": "Player", "name": player, "id": "p1"}],
            },
            {
                "marketId": "m1", "label": "Under", "points": line,
                "id": "selUnder",
                "displayOdds": {"american": str(under)},
                "participants": [{"type": "Player", "name": player, "id": "p1"}],
            },
        ],
    }


def _make_fetch_spy(payloads_by_cat: dict):
    """Return a fetch_subcategory mock that records which cat IDs were called."""
    called = []

    def _fetch(cat_id, sub_id, timeout=15):
        called.append((cat_id, sub_id))
        return payloads_by_cat.get(cat_id, _EMPTY_PAYLOAD)

    _fetch.called_cats = called
    return _fetch


def _run_snapshot(payloads_by_cat: dict, live_event_ids, tmp_path,
                  monkeypatch, raises: bool = False):
    """Run one_snapshot() with mocked fetch + live detector.

    Returns (called_cat_ids_set, status_dict).
    """
    monkeypatch.setattr(_dk_scraper, "LINES_DIR", str(tmp_path))
    fetch_spy = _make_fetch_spy(payloads_by_cat)

    def _mock_live():
        if raises:
            raise RuntimeError("simulated _live_event_ids timeout")
        return live_event_ids

    inplay_stub = types.ModuleType("draftkings_inplay_scraper")
    inplay_stub._live_event_ids = _mock_live

    with patch.object(_dk_scraper, "fetch_subcategory", side_effect=fetch_spy):
        with patch.dict(sys.modules, {"draftkings_inplay_scraper": inplay_stub}):
            status = _dk_scraper.one_snapshot()

    return {c for c, _ in fetch_spy.called_cats}, status


_LIVE = _dk_scraper._DK_LIVE_CAT_IDS
_LEGACY = {1215, 1216, 1217, 1218}


# ---------------------------------------------------------------------------
# Static constant checks
# ---------------------------------------------------------------------------
class TestStaticConstants:
    def test_legacy_paths_exclude_live_cat_ids(self):
        for stat, (cat_id, _sub) in _dk_scraper._DK_STAT_PATHS.items():
            assert cat_id not in _LIVE, (
                f"Legacy _DK_STAT_PATHS['{stat}'] uses live cat {cat_id}."
            )

    def test_legacy_paths_use_expected_ids(self):
        assert _dk_scraper._DK_STAT_PATHS == {
            "pts": (1215, 12488),
            "reb": (1216, 12492),
            "ast": (1217, 12495),
            "fg3m": (1218, 12497),
        }

    def test_fallback_paths_are_live_cat_ids(self):
        """The fallback map must reference the live 1686-1689 categories."""
        fb_cats = {c for (c, _) in _dk_scraper._DK_LIVE_FALLBACK_PATHS.values()}
        assert fb_cats <= _LIVE
        assert fb_cats == {1686, 1687, 1688, 1689}

    def test_live_cat_ids_set_correct(self):
        assert _LIVE == frozenset({1686, 1687, 1688, 1689})

    def test_inplay_paths_use_live_cat_ids(self):
        inplay_cats = {cat for (cat, _) in _dk_inplay._DK_INPLAY_PATHS.values()}
        assert inplay_cats & _LIVE


# ---------------------------------------------------------------------------
# one_snapshot() behavioural cases
# ---------------------------------------------------------------------------
class TestOneSnapshotDataLossSafeGate:

    # (a) no-live + legacy non-empty -> legacy used, no live cat touched
    def test_no_live_legacy_nonempty_uses_legacy_no_live_cat(
            self, tmp_path, monkeypatch):
        payloads = {1215: _ou_payload("Player A", 24.5)}  # only pts populated
        fetched, status = _run_snapshot(
            payloads, live_event_ids=[], tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        # pts legacy returned rows -> no fallback for pts. Other stats are empty
        # so they WILL fall back (no game live) — that is allowed. Assert pts
        # specifically did not trigger the live cat 1686.
        assert 1215 in fetched
        assert 1686 not in fetched, (
            "pts legacy returned rows; live cat 1686 should not be fetched."
        )
        assert status["by_stat"]["pts"] == 1
        assert status["fallback_allowed"] is True
        assert "pts" not in status.get("fallback_stats", [])

    def test_no_live_all_legacy_nonempty_never_touches_live(
            self, tmp_path, monkeypatch):
        """When ALL legacy categories return rows, NO live cat is ever fetched."""
        payloads = {
            1215: _ou_payload("A", 24.5),
            1216: _ou_payload("B", 8.5),
            1217: _ou_payload("C", 5.5),
            1218: _ou_payload("D", 2.5),
        }
        fetched, status = _run_snapshot(
            payloads, live_event_ids=[], tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        assert fetched == _LEGACY
        assert not (fetched & _LIVE)
        assert status.get("fallback_stats", []) == []

    # (b) no-live + legacy empty -> falls back to live cat, data recovered
    def test_no_live_legacy_empty_falls_back_to_live(
            self, tmp_path, monkeypatch):
        # Legacy all empty; live cat 1686 (pts) serves a pregame line pre-tip.
        payloads = {1686: _ou_payload("Player A", 24.5)}
        fetched, status = _run_snapshot(
            payloads, live_event_ids=[], tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        assert 1686 in fetched, "Expected fallback to live cat 1686 pre-tip."
        assert status["by_stat"]["pts"] == 1, "pts data recovered via fallback."
        assert "pts" in status["fallback_stats"]
        assert status["rows"] >= 1

    # (c) live game -> legacy only; live cat NEVER fetched even if legacy empty
    def test_live_game_never_fetches_live_cat_even_if_legacy_empty(
            self, tmp_path, monkeypatch):
        # Everything empty AND a game is live -> must NOT fall back to 1686.
        fetched, status = _run_snapshot(
            payloads_by_cat={}, live_event_ids=["evLive1", "evLive2"],
            tmp_path=tmp_path, monkeypatch=monkeypatch,
        )
        assert not (fetched & _LIVE), (
            f"Live cats {fetched & _LIVE} fetched while a game was live — "
            "contaminates book='dk'."
        )
        assert fetched == _LEGACY  # only the four legacy cats attempted
        assert status["fallback_allowed"] is False
        assert status.get("fallback_stats", []) == []
        # Empty for a live game -> nothing written.
        assert status["rows"] == 0

    def test_live_game_legacy_nonempty_still_no_live_cat(
            self, tmp_path, monkeypatch):
        payloads = {1215: _ou_payload("Player A", 24.5)}
        fetched, status = _run_snapshot(
            payloads, live_event_ids=["evLive1"], tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        assert not (fetched & _LIVE)
        assert status["by_stat"]["pts"] == 1

    # (d) _live_event_ids raises -> behaves as no-live (fallback allowed)
    def test_detection_failure_behaves_as_no_live_fallback_allowed(
            self, tmp_path, monkeypatch):
        payloads = {1686: _ou_payload("Player A", 24.5)}  # only live cat has data
        fetched, status = _run_snapshot(
            payloads, live_event_ids=None, tmp_path=tmp_path,
            monkeypatch=monkeypatch, raises=True,
        )
        assert status["fallback_allowed"] is True, (
            "Detection failure must be treated as no-live so fallback is allowed."
        )
        assert 1686 in fetched, "Fallback recovered data despite detection error."
        assert status["by_stat"]["pts"] == 1
        assert "pts" in status["fallback_stats"]
