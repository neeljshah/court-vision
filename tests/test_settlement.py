"""tests/test_settlement.py — Unit tests for the shadow-log settlement engine.

Five tests covering:
  1. fetch_final_boxscore returns None for in-progress game (gameStatus=2)
  2. fetch_final_boxscore extracts all 7 stats for finalized game (fixture JSON)
  3. settle_shadow_log correctly resolves OVER hit / miss / push around line
  4. settle_shadow_log handles missing player_id in finals (outcome=no_actual)
  5. settle_day end-to-end: synthetic shadow CSV + mocked fetch -> correct settled CSV

All HTTP calls are mocked via unittest.mock.patch — no network required.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from typing import Dict
from unittest.mock import patch, MagicMock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.settlement import (
    fetch_final_boxscore,
    settle_shadow_log,
    settle_day,
    _SETTLED_COLS,
)

# Path to the realistic boxscore fixture.
FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "boxscore_sample.json"
)

# Minimal shadow-log columns used in tests.
_SHADOW_COLS_MIN = [
    "ts", "game_id", "period", "clock_remaining", "player_id", "name",
    "team", "stat", "side", "line", "book", "odds", "model_proj",
    "current_stat", "sigma", "raw_ev", "kelly", "tier", "gate_status",
    "gate_blocked_by", "source",
]


def _make_shadow_row(**overrides) -> Dict:
    """Build a minimal shadow-log row dict with sane defaults."""
    base = {
        "ts":              "2026-05-25T22:00:00+00:00",
        "game_id":         "0042500315",
        "period":          "3",
        "clock_remaining": "5:00",
        "player_id":       "1628369",   # Jayson Tatum by default
        "name":            "Jayson Tatum",
        "team":            "BOS",
        "stat":            "pts",
        "side":            "OVER",
        "line":            "29.5",
        "book":            "DK",
        "odds":            "-110",
        "model_proj":      "32.1",
        "current_stat":    "22",
        "sigma":           "5.0",
        "raw_ev":          "0.04",
        "kelly":           "0.02",
        "tier":            "A",
        "gate_status":     "passed",
        "gate_blocked_by": "",
        "source":          "live",
    }
    base.update(overrides)
    return base


def _write_shadow_csv(path: str, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_SHADOW_COLS_MIN, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _load_fixture_raw() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Test 1: fetch_final_boxscore returns None for gameStatus=2 (in-progress).  #
# --------------------------------------------------------------------------- #
class TestFetchFinalBoxscoreInProgress(unittest.TestCase):
    def test_returns_none_for_in_progress_game(self):
        """gameStatus=2 → function must return None (game not finalized)."""
        in_progress_payload = {
            "game": {
                "gameId": "0042500315",
                "gameStatus": 2,
                "gameStatusText": "Q3 5:00",
                "homeTeam": {"teamTricode": "BOS", "players": []},
                "awayTeam": {"teamTricode": "MIA", "players": []},
            }
        }
        with patch("src.prediction.settlement._fetch_json",
                   return_value=in_progress_payload):
            result = fetch_final_boxscore("0042500315")
        self.assertIsNone(result)


# --------------------------------------------------------------------------- #
# Test 2: fetch_final_boxscore extracts correct stats for finalized game.     #
# --------------------------------------------------------------------------- #
class TestFetchFinalBoxscoreFinalized(unittest.TestCase):
    def test_extracts_all_stats_from_fixture(self):
        """gameStatus=3 + fixture JSON → dict with correct pts/reb/ast/etc."""
        payload = _load_fixture_raw()
        with patch("src.prediction.settlement._fetch_json", return_value=payload):
            finals = fetch_final_boxscore("0042500315")

        self.assertIsNotNone(finals)
        # Jayson Tatum fixture: pts=32, reb=8, ast=5, fg3m=4, stl=2, blk=1, tov=3
        tatum_id = "1628369"
        self.assertEqual(finals[(tatum_id, "pts")],  32.0)
        self.assertEqual(finals[(tatum_id, "reb")],   8.0)
        self.assertEqual(finals[(tatum_id, "ast")],   5.0)
        self.assertEqual(finals[(tatum_id, "fg3m")],  4.0)
        self.assertEqual(finals[(tatum_id, "stl")],   2.0)
        self.assertEqual(finals[(tatum_id, "blk")],   1.0)
        self.assertEqual(finals[(tatum_id, "tov")],   3.0)

        # Also spot-check an away player: Jimmy Butler pts=28
        butler_id = "1626162"
        self.assertEqual(finals[(butler_id, "pts")], 28.0)

    def test_returns_none_when_fetch_fails(self):
        """Network failure → function returns None gracefully."""
        with patch("src.prediction.settlement._fetch_json", return_value=None):
            result = fetch_final_boxscore("0042500999")
        self.assertIsNone(result)


# --------------------------------------------------------------------------- #
# Test 3: settle_shadow_log hit/miss/push resolution around line value.       #
# --------------------------------------------------------------------------- #
class TestSettleShadowLogResolution(unittest.TestCase):
    def setUp(self):
        self.finals = {("1628369", "pts"): 32.0}   # Tatum scored 32

    def _run_single(self, tmp_path, **row_overrides):
        row = _make_shadow_row(**row_overrides)
        csv_path = os.path.join(tmp_path, "shadow.csv")
        _write_shadow_csv(csv_path, [row])
        return settle_shadow_log(csv_path, self.finals)[0]

    def test_over_hit(self):
        """OVER 29.5 + actual=32 → outcome=hit, return > 0."""
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_single(tmp, side="OVER", line="29.5", odds="-110")
        self.assertEqual(result["outcome"], "hit")
        self.assertGreater(float(result["realized_return_$1"]), 0)

    def test_over_miss(self):
        """OVER 34.5 + actual=32 → outcome=miss, return=-1."""
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_single(tmp, side="OVER", line="34.5", odds="-110")
        self.assertEqual(result["outcome"], "miss")
        self.assertAlmostEqual(float(result["realized_return_$1"]), -1.0)

    def test_push(self):
        """Exact line match (OVER 32.0 + actual=32) → outcome=push, return=0."""
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_single(tmp, side="OVER", line="32.0", odds="-110")
        self.assertEqual(result["outcome"], "push")
        self.assertAlmostEqual(float(result["realized_return_$1"]), 0.0)

    def test_under_hit(self):
        """UNDER 34.5 + actual=32 → outcome=hit."""
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_single(tmp, side="UNDER", line="34.5", odds="-115")
        self.assertEqual(result["outcome"], "hit")

    def test_under_miss(self):
        """UNDER 29.5 + actual=32 → outcome=miss."""
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_single(tmp, side="UNDER", line="29.5", odds="-115")
        self.assertEqual(result["outcome"], "miss")


# --------------------------------------------------------------------------- #
# Test 4: settle_shadow_log handles missing player_id (outcome=no_actual).    #
# --------------------------------------------------------------------------- #
class TestSettleShadowLogMissingPlayer(unittest.TestCase):
    def test_missing_player_returns_no_actual(self):
        """player_id not in finals dict → outcome=no_actual, return=0."""
        finals: Dict = {}   # empty — no actuals at all
        with tempfile.TemporaryDirectory() as tmp:
            row = _make_shadow_row(player_id="9999999", stat="pts")
            csv_path = os.path.join(tmp, "shadow.csv")
            _write_shadow_csv(csv_path, [row])
            results = settle_shadow_log(csv_path, finals)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["outcome"], "no_actual")
        self.assertAlmostEqual(float(r["realized_return_$1"]), 0.0)
        self.assertEqual(r["actual_stat"], "")

    def test_empty_shadow_csv_returns_empty_list(self):
        """Shadow CSV with only a header → empty result list."""
        finals = {("1628369", "pts"): 32.0}
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "shadow.csv")
            _write_shadow_csv(csv_path, [])  # no data rows
            results = settle_shadow_log(csv_path, finals)
        self.assertEqual(results, [])


# --------------------------------------------------------------------------- #
# Test 5: settle_day end-to-end with synthetic shadow CSV + mocked fetch.     #
# --------------------------------------------------------------------------- #
class TestSettleDayEndToEnd(unittest.TestCase):
    def test_settle_day_produces_correct_settled_csv(self):
        """
        Synthetic shadow CSV (3 rows, 1 game) + mocked finalized boxscore
        → settled_<date>.csv has correct hit/miss/no_actual outcomes.
        """
        date_str = "2026-05-25"
        game_id  = "0042500315"

        rows = [
            # Row 1: OVER 29.5 pts — Tatum actual=32 → hit
            _make_shadow_row(
                player_id="1628369", stat="pts",
                side="OVER", line="29.5", odds="-110",
                gate_status="passed",
            ),
            # Row 2: OVER 34.5 pts — Tatum actual=32 → miss
            _make_shadow_row(
                player_id="1628369", stat="pts",
                side="OVER", line="34.5", odds="-110",
                gate_status="blocked",
                gate_blocked_by="kelly_too_low",
            ),
            # Row 3: unknown player → no_actual
            _make_shadow_row(
                player_id="9999999", stat="pts",
                side="OVER", line="20.0", odds="-110",
                gate_status="passed",
            ),
        ]

        # Finals: only Tatum pts=32.
        mock_finals = {("1628369", "pts"): 32.0}

        with tempfile.TemporaryDirectory() as tmp:
            shadow_path = os.path.join(tmp, f"{game_id}_{date_str}.csv")
            _write_shadow_csv(shadow_path, rows)

            with patch(
                "src.prediction.settlement.fetch_final_boxscore",
                return_value=mock_finals,
            ):
                n_settled = settle_day(date_str=date_str, base_dir=tmp)

            # Should have settled all 3 rows.
            self.assertEqual(n_settled, 3)

            # Read back the settled CSV.
            settled_path = os.path.join(tmp, f"settled_{date_str}.csv")
            self.assertTrue(os.path.exists(settled_path))
            with open(settled_path, encoding="utf-8") as fh:
                settled_rows = list(csv.DictReader(fh))

            self.assertEqual(len(settled_rows), 3)

            outcomes = [r["outcome"] for r in settled_rows]
            self.assertIn("hit", outcomes)
            self.assertIn("miss", outcomes)
            self.assertIn("no_actual", outcomes)

            # Row 1 is a hit — realized_return_$1 > 0.
            hit_row = next(r for r in settled_rows if r["outcome"] == "hit")
            self.assertGreater(float(hit_row["realized_return_$1"]), 0)

            # Row 2 is a miss — realized_return_$1 == -1.
            miss_row = next(r for r in settled_rows if r["outcome"] == "miss")
            self.assertAlmostEqual(float(miss_row["realized_return_$1"]), -1.0)

            # Row 3 is no_actual — realized_return_$1 == 0.
            na_row = next(r for r in settled_rows if r["outcome"] == "no_actual")
            self.assertAlmostEqual(float(na_row["realized_return_$1"]), 0.0)

    def test_settle_day_skips_non_final_games(self):
        """fetch returns None (game in progress) → 0 rows settled, file still written."""
        date_str = "2026-05-25"
        game_id  = "0042500999"

        with tempfile.TemporaryDirectory() as tmp:
            shadow_path = os.path.join(tmp, f"{game_id}_{date_str}.csv")
            _write_shadow_csv(shadow_path, [_make_shadow_row(game_id=game_id)])

            with patch(
                "src.prediction.settlement.fetch_final_boxscore",
                return_value=None,   # game not final
            ):
                n_settled = settle_day(date_str=date_str, base_dir=tmp)

            self.assertEqual(n_settled, 0)

            settled_path = os.path.join(tmp, f"settled_{date_str}.csv")
            self.assertTrue(os.path.exists(settled_path))
            with open(settled_path, encoding="utf-8") as fh:
                content = list(csv.DictReader(fh))
            self.assertEqual(content, [])


if __name__ == "__main__":
    unittest.main()
