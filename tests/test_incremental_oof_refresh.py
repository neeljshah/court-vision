"""tests/test_incremental_oof_refresh.py — R18_K5.

Tests for the daemon at ``scripts/incremental_oof_refresh.py``:

1. detect-new-game — game with q4.json that is NOT in parquet is flagged new
2. idempotency — running refresh twice in a row adds nothing the 2nd time
3. atomic write — pregame_oof.parquet is never observed partially written
4. fold assignment — new rows get last_fold + 1
5. prediction-cache refresh — trigger fires only when rows were appended
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from typing import Dict, List
from unittest import mock

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import incremental_oof_refresh as oof  # noqa: E402


_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _seed_parquet(path: str, game_ids: List[str], fold: int = 1) -> None:
    """Write a minimal pregame_oof.parquet with one row per (game, player, stat)."""
    rows = []
    for gid in game_ids:
        for stat in _STATS:
            rows.append({
                "game_id":   gid,
                "player_id": 100,
                "stat":      stat,
                "oof_pred":  1.0,
                "actual":    1.0,
                "game_date": "2024-01-01",
                "fold":      fold,
                "season":    "2023-24",
            })
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_q4(quarter_dir: str, game_id: str, players: List[Dict]) -> None:
    """Write only the q4.json — the daemon's discovery key. For the
    aggregation step we also stub q1/q2/q3 with empty player lists when the
    test wants minute-summing to behave."""
    os.makedirs(quarter_dir, exist_ok=True)
    for q in (1, 2, 3, 4):
        payload = {
            "game_id": game_id,
            "period":  q,
            "players": players if q == 4 else [],
            "teams":   [],
        }
        with open(os.path.join(quarter_dir, f"{game_id}_q{q}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(payload, f)


def _stub_predict(*_a, **_kw) -> Dict[str, float]:
    """Stand-in for ``_predict_for_player`` — returns one float per stat."""
    return {s: 5.5 for s in _STATS}


class TestDetectNewGame(unittest.TestCase):
    """Test 1 — finished q4 game not yet in parquet must be detected."""

    def test_new_game_detected(self):
        with tempfile.TemporaryDirectory() as td:
            oof_path = os.path.join(td, "pregame_oof.parquet")
            qdir = os.path.join(td, "quarter_box")
            _seed_parquet(oof_path, ["0099999001"])

            # New finished game (id 0099999002) NOT in seed parquet.
            players = [{"player_id": 200, "team_abbreviation": "ATL",
                        "min": "30:00", "pts": 12, "reb": 4, "ast": 3,
                        "fg3m": 2, "stl": 1, "blk": 0, "to": 1}]
            _write_q4(qdir, "0099999002", players)

            game_idx = {"0099999002": {"season": "2023-24",
                                       "game_date": "2024-04-15",
                                       "home_team": "ATL", "away_team": "BOS"}}
            probe = os.path.join(td, "probe.json")
            with mock.patch.object(oof, "_load_game_index",
                                   return_value=game_idx), \
                 mock.patch.object(oof, "_predict_for_player",
                                   side_effect=_stub_predict):
                res = oof.refresh_once(
                    oof_path=oof_path, quarter_dir=qdir,
                    trigger_prediction_cache=False, probe_path=probe,
                )
            self.assertEqual(res["n_new_games_detected"], 1)
            self.assertEqual(res["n_rows_added"], len(_STATS))


class TestIdempotency(unittest.TestCase):
    """Test 2 — second consecutive refresh adds nothing."""

    def test_second_run_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            oof_path = os.path.join(td, "pregame_oof.parquet")
            qdir = os.path.join(td, "quarter_box")
            _seed_parquet(oof_path, ["0099999001"])
            players = [{"player_id": 200, "team_abbreviation": "ATL",
                        "min": "30:00", "pts": 12, "reb": 4, "ast": 3,
                        "fg3m": 2, "stl": 1, "blk": 0, "to": 1}]
            _write_q4(qdir, "0099999002", players)
            game_idx = {"0099999002": {"season": "2023-24",
                                       "game_date": "2024-04-15",
                                       "home_team": "ATL", "away_team": "BOS"}}
            probe = os.path.join(td, "probe.json")
            with mock.patch.object(oof, "_load_game_index",
                                   return_value=game_idx), \
                 mock.patch.object(oof, "_predict_for_player",
                                   side_effect=_stub_predict):
                r1 = oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                      trigger_prediction_cache=False,
                                      probe_path=probe)
                r2 = oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                      trigger_prediction_cache=False,
                                      probe_path=probe)
            self.assertGreater(r1["n_rows_added"], 0)
            self.assertEqual(r2["n_new_games_detected"], 0)
            self.assertEqual(r2["n_rows_added"], 0)


class TestAtomicWrite(unittest.TestCase):
    """Test 3 — the staging .tmp file is gone after refresh (no partial state)."""

    def test_no_tmp_file_remains(self):
        with tempfile.TemporaryDirectory() as td:
            oof_path = os.path.join(td, "pregame_oof.parquet")
            qdir = os.path.join(td, "quarter_box")
            _seed_parquet(oof_path, ["0099999001"])
            players = [{"player_id": 200, "team_abbreviation": "ATL",
                        "min": "30:00", "pts": 12, "reb": 4, "ast": 3,
                        "fg3m": 2, "stl": 1, "blk": 0, "to": 1}]
            _write_q4(qdir, "0099999002", players)
            game_idx = {"0099999002": {"season": "2023-24",
                                       "game_date": "2024-04-15",
                                       "home_team": "ATL", "away_team": "BOS"}}
            probe = os.path.join(td, "probe.json")
            with mock.patch.object(oof, "_load_game_index",
                                   return_value=game_idx), \
                 mock.patch.object(oof, "_predict_for_player",
                                   side_effect=_stub_predict):
                oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                 trigger_prediction_cache=False,
                                 probe_path=probe)
            # Atomic-rename guarantee: the .tmp staging file must not survive.
            self.assertFalse(os.path.exists(oof_path + ".tmp"))
            # And the destination must be a readable parquet.
            df = pd.read_parquet(oof_path)
            self.assertGreater(len(df), len(_STATS))  # seed + new rows


class TestFoldAssignment(unittest.TestCase):
    """Test 4 — new rows go into last_fold + 1, walk-forward intact."""

    def test_new_rows_get_next_fold(self):
        with tempfile.TemporaryDirectory() as td:
            oof_path = os.path.join(td, "pregame_oof.parquet")
            qdir = os.path.join(td, "quarter_box")
            _seed_parquet(oof_path, ["0099999001"], fold=4)  # seed max fold = 4
            players = [{"player_id": 200, "team_abbreviation": "ATL",
                        "min": "30:00", "pts": 12, "reb": 4, "ast": 3,
                        "fg3m": 2, "stl": 1, "blk": 0, "to": 1}]
            _write_q4(qdir, "0099999002", players)
            game_idx = {"0099999002": {"season": "2023-24",
                                       "game_date": "2024-04-15",
                                       "home_team": "ATL", "away_team": "BOS"}}
            probe = os.path.join(td, "probe.json")
            with mock.patch.object(oof, "_load_game_index",
                                   return_value=game_idx), \
                 mock.patch.object(oof, "_predict_for_player",
                                   side_effect=_stub_predict):
                res = oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                       trigger_prediction_cache=False,
                                       probe_path=probe)
            self.assertEqual(res["last_fold"], 5)
            df = pd.read_parquet(oof_path)
            new_rows = df[df["game_id"] == "0099999002"]
            self.assertTrue((new_rows["fold"] == 5).all())


class TestPredictionCacheRefreshTrigger(unittest.TestCase):
    """Test 5 — the R16_E3 refresh fires only when rows were appended."""

    def test_trigger_fires_only_when_rows_added(self):
        with tempfile.TemporaryDirectory() as td:
            oof_path = os.path.join(td, "pregame_oof.parquet")
            qdir = os.path.join(td, "quarter_box")
            _seed_parquet(oof_path, ["0099999001"])
            probe = os.path.join(td, "probe.json")

            # ── pass A: no new q4 files → cache rebuild MUST NOT fire ──
            with mock.patch.object(oof, "_refresh_prediction_cache",
                                   return_value=True) as m_no:
                res_a = oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                         trigger_prediction_cache=True,
                                         probe_path=probe)
            self.assertEqual(res_a["n_rows_added"], 0)
            self.assertFalse(res_a["prediction_cache_refreshed"])
            m_no.assert_not_called()

            # ── pass B: drop a new q4 file → cache rebuild MUST fire ──
            players = [{"player_id": 200, "team_abbreviation": "ATL",
                        "min": "30:00", "pts": 12, "reb": 4, "ast": 3,
                        "fg3m": 2, "stl": 1, "blk": 0, "to": 1}]
            _write_q4(qdir, "0099999002", players)
            game_idx = {"0099999002": {"season": "2023-24",
                                       "game_date": "2024-04-15",
                                       "home_team": "ATL", "away_team": "BOS"}}
            with mock.patch.object(oof, "_load_game_index",
                                   return_value=game_idx), \
                 mock.patch.object(oof, "_predict_for_player",
                                   side_effect=_stub_predict), \
                 mock.patch.object(oof, "_refresh_prediction_cache",
                                   return_value=True) as m_yes:
                res_b = oof.refresh_once(oof_path=oof_path, quarter_dir=qdir,
                                         trigger_prediction_cache=True,
                                         probe_path=probe)
            self.assertGreater(res_b["n_rows_added"], 0)
            self.assertTrue(res_b["prediction_cache_refreshed"])
            m_yes.assert_called_once()


class TestActualSummedAcrossQuarters(unittest.TestCase):
    """Bonus — full-game actual = sum over q1..q4, not just q4."""

    def test_actual_sums_quarters(self):
        with tempfile.TemporaryDirectory() as td:
            qdir = os.path.join(td, "quarter_box")
            os.makedirs(qdir)
            # 5 pts in each of 4 quarters → 20 pts total game.
            for q in (1, 2, 3, 4):
                payload = {
                    "game_id": "0099999003", "period": q,
                    "players": [{"player_id": 300,
                                 "team_abbreviation": "ATL",
                                 "min": "12:00", "pts": 5, "reb": 1,
                                 "ast": 1, "fg3m": 0, "stl": 0,
                                 "blk": 0, "to": 0}],
                    "teams": [],
                }
                with open(os.path.join(qdir, f"0099999003_q{q}.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(payload, f)
            totals = oof._sum_player_totals("0099999003", quarter_dir=qdir)
            self.assertIn(300, totals)
            self.assertEqual(totals[300]["pts"], 20.0)
            self.assertEqual(totals[300]["reb"], 4.0)
            self.assertEqual(totals[300]["min"], 48.0)


if __name__ == "__main__":
    unittest.main()
