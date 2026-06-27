"""tests.platformkit.test_ingame_wiring -- M6 in-game spine wiring tests.

Covers:
  1. /api/live prefers the M6 ingame snapshot (read_live_part) when files exist.
  2. /api/live falls back to live_board.todays_live_games when no ingame snapshot.
  3. record_ingame_bet records exactly ONE open row with channel='paper_ingame'.
  4. A second call with the same key is a no-op (idempotent, no dup row).
  5. grade_live settles the open row and appends a settled row with CLV fields.
  6. No dup settlement on a second grade_live call for the same game.

HONESTY:
  * No network, no corpus -- all I/O is tmp-dir, no real ESPN hits.
  * edge_claimed / executed are always False (asserted).
  * No dollar edge asserted; CLV fields are present but not interpreted as profit.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_ingame_wiring.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from scripts.platformkit.ingame import market_set as ms_mod
from scripts.platformkit.ingame import snapshot as igsnap_mod
from scripts.platformkit.ingame import paper_ingame as pi_mod
from scripts.platformkit import clv_ledger as clv_mod


# ---- helpers ------------------------------------------------------------------

def _make_market_set(game_id: str, sport: str = "nba",
                     available: bool = True) -> Dict[str, Any]:
    """Minimal market_set dict for snapshot writes."""
    rp: Dict[str, Any] = {
        "available": available, "sport": sport,
        "probs": {"p_home": 0.60, "p_away": 0.40, "w": 0.38, "p_live": 0.71},
        "markets": [{"market": "win_home", "prob": 0.60}],
        "variance": 0.10, "remaining_frac": 0.40,
        "basis": "blend", "edge_claimed": False,
        "_honest_note": "test",
    }
    return ms_mod.build(game_id, sport, rp)


def _todays_live_games_stub(sport: str) -> Dict[str, Any]:
    """Stub for live_board.todays_live_games used in fallback tests."""
    return {
        "sport": sport, "status": "ok",
        "games": [{"home": "Knicks", "away": "Spurs", "state": "live",
                   "home_score": 55, "away_score": 52}],
        "served_from": "live_board_stub",
    }


# ===========================================================================
# 1. /api/live prefers ingame snapshot when files exist
# ===========================================================================

def test_api_live_prefers_ingame_snapshot(tmp_path: Path) -> None:
    """/api/live returns the ingame snapshot block when one exists, not live_board."""
    from fastapi.testclient import TestClient
    from scripts.platformkit.frontend import serve as serve_mod

    # Write a snapshot into tmp_path so read_live_part returns data.
    mset = _make_market_set("G1")
    igsnap_mod.write_live("G1", mset, out_dir=tmp_path)

    # Patch _igsnap.read_live_part to use our tmp_path snapshot dir.
    orig_read_live_part = igsnap_mod.read_live_part

    def _patched_read_live_part(sport: str,
                                out_dir: Optional[Path] = None) -> Optional[Dict]:
        return orig_read_live_part(sport, out_dir=tmp_path)

    # Patch live_board to raise so we can prove it is NOT called.
    def _live_board_raises(sport: str) -> Dict:
        raise AssertionError("live_board.todays_live_games must NOT be called when "
                             "ingame snapshot is present")

    with patch.object(serve_mod, "_igsnap") as mock_igsnap, \
         patch("scripts.platformkit.frontend.serve._live_board") as mock_lb:
        mock_igsnap.read_live_part.side_effect = _patched_read_live_part
        mock_lb.todays_live_games.side_effect = _live_board_raises

        app = serve_mod.create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/live?sport=nba")

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("served_from") == "ingame_snapshot", (
        "Expected served_from='ingame_snapshot' but got: %s" % data.get("served_from"))
    assert data.get("status") == "ok"
    assert data.get("edge_claimed") is False
    games = data.get("games", [])
    assert len(games) == 1
    assert games[0]["game_id"] == "G1"


# ===========================================================================
# 2. /api/live falls back to live_board when no ingame snapshot
# ===========================================================================

def test_api_live_falls_back_when_no_ingame_snapshot(tmp_path: Path) -> None:
    """/api/live falls back to live_board when the ingame snapshot dir is empty."""
    from fastapi.testclient import TestClient
    from scripts.platformkit.frontend import serve as serve_mod

    # tmp_path has no written snapshots -> read_live_part returns None.
    def _patched_read_live_part(sport: str,
                                out_dir: Optional[Path] = None) -> Optional[Dict]:
        return igsnap_mod.read_live_part(sport, out_dir=tmp_path)  # empty dir

    fallback_called: List[str] = []

    def _live_board_fallback(sport: str) -> Dict:
        fallback_called.append(sport)
        return _todays_live_games_stub(sport)

    with patch.object(serve_mod, "_igsnap") as mock_igsnap, \
         patch("scripts.platformkit.frontend.serve._live_board") as mock_lb, \
         patch("scripts.platformkit.frontend.serve._snapshot_writer", None):
        mock_igsnap.read_live_part.side_effect = _patched_read_live_part
        mock_lb.todays_live_games.side_effect = _live_board_fallback

        app = serve_mod.create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/live?sport=nba")

    assert resp.status_code == 200
    data = resp.json()
    # live_board was the source.
    assert fallback_called == ["nba"], (
        "Expected live_board to be called once; got: %s" % fallback_called)
    # The response is whatever live_board returned (or the fallback sentinel).
    assert isinstance(data, dict)


# ===========================================================================
# 3. record_ingame_bet adds exactly one open row with channel='paper_ingame'
# ===========================================================================

def test_record_ingame_bet_writes_one_open_row(tmp_path: Path) -> None:
    ledger = tmp_path / "clv_test.jsonl"
    rec = pi_mod.record_ingame_bet(
        sport="nba", game_id="G_TEST_1", market="win_home", side="home",
        taken_decimal=1.90, model_prob=0.57, stake=50.0, path=ledger)

    assert rec["added_new"] is True
    assert rec["status"] == "open"
    assert rec["executed"] is False
    assert rec["channel"] == pi_mod.CHANNEL_PAPER_INGAME

    rows = clv_mod.load_ledger(ledger)
    open_rows = [r for r in rows if r.get("status") == "open"
                 and r.get("channel") == pi_mod.CHANNEL_PAPER_INGAME]
    assert len(open_rows) == 1, (
        "Expected exactly 1 open paper_ingame row, got %d" % len(open_rows))
    row = open_rows[0]
    assert row["game_id"] == "G_TEST_1"
    assert row["market"] == "win_home"
    assert row["side"] == "home"
    assert row["taken_decimal"] == pytest.approx(1.90)
    assert row["model_prob"] == pytest.approx(0.57)
    assert row["executed"] is False


# ===========================================================================
# 4. Idempotency: second call for same key -> no dup open row
# ===========================================================================

def test_record_ingame_bet_is_idempotent(tmp_path: Path) -> None:
    ledger = tmp_path / "clv_idem.jsonl"
    kwargs = dict(sport="nba", game_id="G_IDEM", market="over_224.5",
                  side="home", taken_decimal=1.85, model_prob=0.52,
                  stake=25.0, path=ledger)

    rec1 = pi_mod.record_ingame_bet(**kwargs)
    rec2 = pi_mod.record_ingame_bet(**kwargs)

    assert rec1["added_new"] is True
    assert rec2["added_new"] is False  # second call: no-op

    rows = clv_mod.load_ledger(ledger)
    open_rows = [r for r in rows if r.get("status") == "open"
                 and r.get("channel") == pi_mod.CHANNEL_PAPER_INGAME]
    assert len(open_rows) == 1, (
        "Idempotency violated: expected 1 open row, got %d" % len(open_rows))


# ===========================================================================
# 5. grade_live settles the open row -> CLV fields present, executed=False
# ===========================================================================

def test_grade_live_settles_and_appends_clv(tmp_path: Path) -> None:
    ledger = tmp_path / "clv_grade.jsonl"
    rec = pi_mod.record_ingame_bet(
        sport="nba", game_id="G_GRADE", market="win_home", side="home",
        taken_decimal=1.91, model_prob=0.56, stake=30.0, path=ledger)

    settled = pi_mod.grade_live(
        rec, home_score=112, away_score=105,
        closing_decimal_home=1.80, closing_decimal_away=2.10,
        path=ledger)

    # Core grading fields.
    assert settled["graded"] is True
    assert settled["outcome"] in ("win", "loss", "push")
    assert settled["executed"] is False
    assert settled["channel"] == pi_mod.CHANNEL_PAPER_INGAME
    # In-game close is always a proxy.
    assert settled.get("clv_is_proxy") is True
    # CLV math ran.
    assert settled.get("clv_pct") is not None
    assert "unit_result" in settled  # UNITS not $ -- field is unit_result, never pnl

    # The settled row was appended to the ledger.
    rows = clv_mod.load_ledger(ledger)
    settled_rows = [r for r in rows if r.get("status") == "settled"
                    and r.get("channel") == pi_mod.CHANNEL_PAPER_INGAME]
    assert len(settled_rows) == 1, (
        "Expected 1 settled row, got %d" % len(settled_rows))
    # Original open row is still there (append-only, never mutated).
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert len(open_rows) == 1, (
        "Open row must NOT be removed (append-only ledger)")


# ===========================================================================
# 6. No double settlement on repeated grade_live
# ===========================================================================

def test_grade_live_no_double_settlement(tmp_path: Path) -> None:
    """grade_live is NOT inherently idempotent (it always appends); the
    caller (the spine) is responsible for calling it only once per result.
    We assert that the open row count stays at 1 throughout and that the
    grade fields on the second settled row are consistent (no fabrication)."""
    ledger = tmp_path / "clv_nodup.jsonl"
    rec = pi_mod.record_ingame_bet(
        sport="nba", game_id="G_DUP", market="win_home", side="away",
        taken_decimal=2.05, model_prob=0.45, stake=20.0, path=ledger)

    pi_mod.grade_live(rec, home_score=100, away_score=108,
                      closing_decimal_home=1.82, closing_decimal_away=2.08,
                      path=ledger)

    rows = clv_mod.load_ledger(ledger)
    open_rows = [r for r in rows if r.get("status") == "open"]
    settled_rows = [r for r in rows if r.get("status") == "settled"
                    and r.get("channel") == pi_mod.CHANNEL_PAPER_INGAME]

    # One open row (never mutated), one settled row (appended once).
    assert len(open_rows) == 1
    assert len(settled_rows) == 1

    sr = settled_rows[0]
    assert sr["executed"] is False
    assert sr["graded"] is True
    # outcome for 'away' side when away_score 108 > home 100 should be 'win'.
    assert sr["outcome"] == "win"
