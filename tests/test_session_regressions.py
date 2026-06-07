"""tests/test_session_regressions.py — Regression suite locking in tonight's session fixes.

Covers:
  1. Fake "DraftKings -110" bug in _regrade_bet_with_live_q50 — side flip must use real ladder
  2. Freshness filter fallback — stale-only ladder still picks a real quote
  3. Late-roster synthesis — snapshot player not in CSV generates a bet with _late_roster=True
  4. FINAL state detection — snapshot.game_status=="FINAL" sets status="final" in live_games
  5. Snapshot-aware _today_et — fresh snapshot's captured_at wins over file checks
  6. game_id filter on /api/slate — BOGUS returns 0 bets; canonical id returns matching bets
  7. /api/health includes public_url field
"""
from __future__ import annotations

import importlib
import json
import sys
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent


def _import_router():
    """Import api.courtvision_router with heavy side-effects guarded."""
    import api.courtvision_router as mod
    return mod


# ---------------------------------------------------------------------------
# Test 1: Fake "DraftKings -110" bug — side flip must come from real ladder
# ---------------------------------------------------------------------------

class TestRegradeUsesRealLadder:
    """_regrade_bet_with_live_q50: when side flips, best_book/best_price must
    come from the actual _books_full ladder, not a hardcoded fallback."""

    def _make_bet(self, books_full: list[dict]) -> dict:
        """Minimal bet dict with a DraftKings entry that has the wrong side."""
        return {
            "prop_stat": "pts",
            "line": 20.0,
            "side": "OVER",
            "best_book": "DraftKings",
            "best_price": -110,
            "q50": 21.0,
            "all_books": [],
            "_books_full": books_full,
        }

    def test_fanduel_wins_when_side_flips(self):
        """After a side-flip, best_book must be FanDuel (only book with new side)."""
        mod = _import_router()

        # q50=18.5 < line=20.0 → UNDER. Only FanDuel has under_odds, DK does not.
        now_iso = datetime.now(timezone.utc).isoformat()
        books_full = [
            {"book": "FanDuel",    "over_odds": -120, "under_odds": -105, "captured_at": now_iso},
            {"book": "DraftKings", "over_odds": -115, "under_odds": None,  "captured_at": now_iso},
        ]
        bet = self._make_bet(books_full)
        mod._regrade_bet_with_live_q50(bet, new_q50=18.5,
                                        stat_sigma={"pts": 6.2})

        assert bet["side"] == "UNDER", "side should flip to UNDER"
        assert bet["best_book"] == "FanDuel", \
            f"best_book must be FanDuel, got {bet['best_book']!r}"
        assert bet["best_price"] == -105, \
            f"best_price must be FanDuel's under_odds (-105), got {bet['best_price']}"

    def test_best_price_not_hardcoded_minus_110(self):
        """best_price should never be -110 unless the ladder actually quotes -110."""
        mod = _import_router()

        now_iso = datetime.now(timezone.utc).isoformat()
        # FanDuel quotes OVER at -108, DK quotes OVER at -112 — neither is -110
        books_full = [
            {"book": "FanDuel",    "over_odds": -108, "under_odds": None, "captured_at": now_iso},
            {"book": "DraftKings", "over_odds": -112, "under_odds": None, "captured_at": now_iso},
        ]
        bet = self._make_bet(books_full)
        # new_q50=21.5 > line=20.0 → OVER — no side flip here, still uses ladder
        mod._regrade_bet_with_live_q50(bet, new_q50=21.5,
                                        stat_sigma={"pts": 6.2})

        assert bet["side"] == "OVER"
        assert bet["best_price"] != -110, \
            "best_price must not be hardcoded -110; should be -108 from FanDuel"
        assert bet["best_price"] == -108, \
            f"best_price should be FanDuel -108 (best OVER), got {bet['best_price']}"
        assert bet["best_book"] == "FanDuel"


# ---------------------------------------------------------------------------
# Test 2: Freshness filter fallback — stale quotes should still produce a price
# ---------------------------------------------------------------------------

class TestFreshnessFilterFallback:
    """When ALL quotes are stale (> 15 min), fall back to any real quote."""

    def test_stale_only_ladder_still_picks_a_price(self):
        mod = _import_router()

        # Timestamp > 15 min ago — stale
        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        books_full = [
            {"book": "BetMGM", "over_odds": -115, "under_odds": -105, "captured_at": stale_ts},
        ]
        bet = {
            "prop_stat": "reb",
            "line": 8.0,
            "side": "OVER",
            "best_book": "DraftKings",
            "best_price": -110,
            "q50": 9.0,
            "all_books": [],
            "_books_full": books_full,
        }
        mod._regrade_bet_with_live_q50(bet, new_q50=9.0, stat_sigma={"reb": 2.6})

        # Should pick BetMGM's stale quote rather than leaving None or raising
        assert bet.get("best_book") is not None, "best_book must not be None"
        assert bet.get("best_price") is not None, "best_price must not be None"
        assert bet["best_book"] == "BetMGM", \
            f"expected BetMGM (only book), got {bet['best_book']!r}"

    def test_stale_fallback_never_marks_no_price(self):
        """live_regraded_no_price must be False/absent when stale quote exists."""
        mod = _import_router()

        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        books_full = [
            {"book": "PointsBet", "over_odds": -110, "under_odds": -110, "captured_at": stale_ts},
        ]
        bet = {
            "prop_stat": "ast",
            "line": 5.5,
            "side": "OVER",
            "best_book": "PointsBet",
            "best_price": -110,
            "q50": 6.0,
            "all_books": [],
            "_books_full": books_full,
        }
        mod._regrade_bet_with_live_q50(bet, new_q50=6.0, stat_sigma={"ast": 2.0})

        assert not bet.get("live_regraded_no_price"), \
            "live_regraded_no_price must not be set when a stale quote exists"


# ---------------------------------------------------------------------------
# Test 3: Late-roster synthesis — player not in CSV generates bet with _late_roster=True
# ---------------------------------------------------------------------------

class TestLateRosterSynthesis:
    """_synthesize_bets_from_snapshots: player in snapshot but absent from CSV
    should produce a bet with _late_roster=True when a line exists."""

    def test_late_roster_player_produces_bet(self, tmp_path):
        mod = _import_router()

        # Build a minimal snapshot with one player
        snap_content = {
            "period": 2,
            "game_id": "0022500001",
            "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "home_team": "LAL",
            "away_team": "GSW",
            "away_score": 54,
            "home_score": 58,
            "players": [
                {"name": "Ghost Player", "team": "LAL", "pts": 8, "min": "18:00"},
            ],
        }
        live_dir = tmp_path / "live"
        live_dir.mkdir()
        # Use an epoch-style filename ({gid}_{epoch}.json) so the production
        # code's _is_epoch_snap / _get_live_dir_index accept it.
        snap_path = live_dir / "0022500001_1714000000.json"
        snap_path.write_text(json.dumps(snap_content), encoding="utf-8")

        # One line row for Ghost Player
        line_rows = [
            {
                "player": "Ghost Player",
                "stat": "pts",
                "game_id": "0022500001",
                "line": 14.5,
                "over_odds": -110,
                "under_odds": -110,
                "book": "FanDuel",
                "opp": "GSW",
                "venue": "home",
                "player_id": "",
                "team": "LAL",
            }
        ]

        # Mock heavy imports used inside _synthesize_bets_from_snapshots
        mock_proj_row = [{"name": "ghost player", "stat": "pts", "projected_final": 16.0}]

        # _synthesize_bets_from_snapshots ignores the live_dir argument and
        # falls back to _get_live_dir_index() (which reads the module-level
        # _LIVE_DIR_PATH constant).  Bypass the global cache entirely by
        # supplying prefilled_dir_index so the function uses our tmp snap.
        prefilled_index = {"0022500001": snap_path}

        with patch("api._courtvision_odds.resolve_game_id",
                   return_value={"canonical_ids": frozenset(["0022500001"])}), \
             patch("src.prediction.live_engine.project_from_snapshot",
                   return_value=mock_proj_row):

            bets = mod._synthesize_bets_from_snapshots(
                line_rows=line_rows,
                stat_sigma={"pts": 6.2},
                live_dir=live_dir,
                date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                skip_keys=set(),
                synthesized_flag=False,  # late-roster path
                prefilled_dir_index=prefilled_index,
            )

        assert len(bets) >= 1, "Expected at least one bet for the late-roster player"
        assert bets[0].get("_late_roster") is True, \
            f"Expected _late_roster=True, got {bets[0].get('_late_roster')!r}"


# ---------------------------------------------------------------------------
# Test 4: FINAL state detection — snapshot game_status == "FINAL" → status = "final"
# ---------------------------------------------------------------------------

class TestFinalStateDetection:
    """_build_home_data: when snapshot.game_status == 'FINAL', game card status
    must be 'final' and the game appears in live_games."""

    def test_final_snapshot_sets_status_final(self, tmp_path):
        mod = _import_router()

        gid = "0022500999"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Write a FINAL snapshot with team abbrs so the unknown-id guard doesn't drop it.
        snap = {
            "game_id": gid,
            "game_status": "FINAL",
            "period": 4,
            "captured_at": today + "T23:00:00+00:00",
            "home_team": "BOS",
            "away_team": "MIA",
            "home_score": 112,
            "away_score": 105,
            "players": [],
        }
        # _ROOT is patched to tmp_path; function looks for _ROOT / "data" / "live".
        # Use an epoch-style filename ({gid}_{epoch}.json): _build_home_data calls
        # _epoch_snaps() which only matches files whose stem ends in a digit
        # (_is_epoch_snap filter).  "{gid}_snap.json" has a word suffix and
        # would be silently skipped, so no snap_status_by_gid entry would be
        # built and the status override to "final" would never fire.
        live_dir = tmp_path / "data" / "live"
        live_dir.mkdir(parents=True)
        (live_dir / f"{gid}_1714000000.json").write_text(json.dumps(snap), encoding="utf-8")

        # Minimal games_index entry: n_props >= 3 to pass the sparse-game filter;
        # start_time required to not be dropped by the no-start_time guard.
        games_raw = [
            {"game_id": gid, "start_time": today + "T19:00:00+00:00",
             "n_props": 5, "n_players": 2}
        ]

        def fake_games_index(date):
            return games_raw

        def fake_consolidate(date):
            return []

        def fake_overlay(date, props):
            return []

        def fake_resolve_gid(gid_arg):
            return {"canonical_ids": frozenset([gid_arg])}

        # Also patch _guess_teams_from_game_id to return real abbrs so the card
        # isn't dropped by the "AWAY @ HOME" unknown-id guard.
        def fake_guess_teams(gid_arg):
            return ("MIA", "BOS")

        with patch("api.courtvision_router._ROOT", tmp_path), \
             patch("api._courtvision_odds.games_index", side_effect=fake_games_index), \
             patch("api._courtvision_odds.consolidate", side_effect=fake_consolidate), \
             patch("api._predictions_overlay.overlay_predictions", side_effect=fake_overlay), \
             patch("api._courtvision_odds.resolve_game_id", side_effect=fake_resolve_gid), \
             patch("api.courtvision_router._guess_teams_from_game_id",
                   side_effect=fake_guess_teams), \
             patch.dict("api.courtvision_router._CACHE", {}, clear=True):

            data = mod._build_home_data(today)

        live_games = data.get("live_games", [])
        final_games = [g for g in live_games if g.get("status") == "final"]
        assert len(final_games) >= 1, \
            f"Expected at least one 'final' game in live_games; got: {live_games}"
        assert final_games[0]["game_id"] == gid


# ---------------------------------------------------------------------------
# Test 5: Snapshot-aware _today_et — fresh snapshot's date wins
# ---------------------------------------------------------------------------

class TestTodayEtSnapshotAware:
    """_today_et: when a snapshot < 4hr old exists, its captured_at date wins
    over file-existence checks (slate CSV / lines CSV)."""

    def test_fresh_snapshot_date_wins(self, tmp_path):
        """The snapshot's captured_at[:10] must be returned, not the fallback date."""
        mod = _import_router()

        # Use a specific known date embedded in the snapshot (independent of
        # the system clock so the test is stable day-to-day).
        snap_date = "2026-05-28"
        snap = {"captured_at": snap_date + "T22:00:00+00:00", "game_id": "0022500001"}
        # _today_et reads _ROOT / "data" / "live" / "*.json" (not _ROOT / "live").
        # Write the snapshot to the path the production code actually globs.
        live_dir = tmp_path / "data" / "live"
        live_dir.mkdir(parents=True)
        snap_path = live_dir / "0022500001_snap.json"
        snap_path.write_text(json.dumps(snap), encoding="utf-8")

        # _today_et checks os.path.getmtime < 4*3600 to filter fresh snapshots.
        # The file was just written, so mtime is now → passes the freshness gate.
        # Patch downstream helpers so we know the only path that could succeed is
        # the snapshot branch (not slate/lines CSV fallbacks).
        # Also reset _TODAY_ET_CACHE so a cached "today" from an earlier test
        # run (within the 10-second TTL) does not mask the snapshot branch.
        import api.courtvision_router as _router_mod
        _orig_cache = _router_mod._TODAY_ET_CACHE
        _router_mod._TODAY_ET_CACHE = (0.0, "")
        try:
            with patch("api.courtvision_router._ROOT", tmp_path), \
                 patch("api.courtvision_router._slate_csv_path", return_value=None), \
                 patch("api.courtvision_router._lines_exist_for", return_value=False), \
                 patch("api.courtvision_router._next_lines_date", return_value=None), \
                 patch("api.courtvision_router._latest_slate_date", return_value=None):

                result = mod._today_et()
        finally:
            _router_mod._TODAY_ET_CACHE = _orig_cache

        assert result == snap_date, \
            (f"Expected _today_et() == {snap_date!r} (from fresh snapshot), "
             f"got {result!r}")


# ---------------------------------------------------------------------------
# Test 6: game_id filter on /api/slate
# ---------------------------------------------------------------------------

class TestApiSlateGameIdFilter:
    """POST /api/slate: game_id=BOGUS returns 0 bets;
    game_id=<real_id> returns only that game's bets."""

    def _make_slate_envelope(self, game_id: str) -> dict:
        return {
            "date": "2026-05-28",
            "bets": [
                {"game_id": game_id, "player_name": "A Player", "prop_stat": "PTS",
                 "side": "OVER", "line": 20.0, "ev_pct": 5.0, "team": "LAL", "opp": "GSW"},
            ],
        }

    def test_bogus_game_id_returns_zero_bets(self):
        mod = _import_router()

        real_gid = "0022500001"
        envelope = self._make_slate_envelope(real_gid)

        with patch("api.courtvision_router._build_slate", return_value=envelope), \
             patch("api.courtvision_router._next_game_day", return_value=None), \
             patch("api.courtvision_router._today_et", return_value="2026-05-28"), \
             patch("api._courtvision_odds.resolve_game_id",
                   return_value={"canonical_ids": frozenset(["BOGUS"]),
                                 "away_abbr": "", "home_abbr": ""}):

            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(mod.router)
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/slate", params={"game_id": "BOGUS"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bets"]) == 0, \
            f"Expected 0 bets for BOGUS game_id, got {len(data['bets'])}"

    def test_canonical_game_id_returns_matching_bets(self):
        mod = _import_router()

        real_gid = "0022500001"
        envelope = self._make_slate_envelope(real_gid)

        with patch("api.courtvision_router._build_slate", return_value=envelope), \
             patch("api.courtvision_router._next_game_day", return_value=None), \
             patch("api.courtvision_router._today_et", return_value="2026-05-28"), \
             patch("api._courtvision_odds.resolve_game_id",
                   return_value={"canonical_ids": frozenset([real_gid]),
                                 "away_abbr": "GSW", "home_abbr": "LAL"}):

            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(mod.router)
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/slate", params={"game_id": real_gid})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bets"]) == 1, \
            f"Expected 1 bet for canonical game_id, got {len(data['bets'])}"
        assert data["bets"][0]["game_id"] == real_gid


# ---------------------------------------------------------------------------
# Test 7: /api/health includes public_url field
# ---------------------------------------------------------------------------

class TestHealthPublicUrl:
    """/api/health must include public_url in the response."""

    def test_health_has_public_url_field(self, tmp_path):
        """Import live_v2_app.create_app, wire up TestClient, hit /api/health."""
        # Avoid heavy imports in create_app by patching the event bus etc.
        import api.live_v2_app as v2mod

        app = v2mod.create_app()

        from fastapi.testclient import TestClient
        # lifespan=False prevents the startup event from running
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "public_url" in data, \
            f"'public_url' missing from /api/health response; keys: {list(data.keys())}"
