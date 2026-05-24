"""tests/test_pregame_spreads.py — cycle 91c (loop 5).

Four tests covering the pre-game spread fetcher + aggregator + prop_pergame
join introduced in cycle 91c:

1. parse_odds_detail — string → signed home_spread (LAL -4.5 vs BOS @ LAL).
2. aggregate_spreads_to_parquet — mock ESPN payload → exactly 1 parquet row per game.
3. build_pregame_spreads — graceful empty wrapper when parquet absent.
4. prop_pergame row join — home-team player gets -X, away-team player gets +X.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import the module under test.
from scripts import aggregate_spreads_to_parquet as agg  # noqa: E402
from src.prediction import prop_pergame as pp  # noqa: E402


def _mock_event(date_iso: str, home_abbr: str, away_abbr: str,
                details: str, total: float = 225.5) -> dict:
    """Return one ESPN-shaped event dict."""
    return {
        "date": f"{date_iso}T00:30Z",
        "competitions": [{
            "date": f"{date_iso}T00:30Z",
            "competitors": [
                {"homeAway": "home",
                 "team": {"abbreviation": home_abbr}},
                {"homeAway": "away",
                 "team": {"abbreviation": away_abbr}},
            ],
            "odds": [{"details": details, "overUnder": total}],
        }],
    }


class TestParseOdds(unittest.TestCase):
    """Test 1 — Mock ESPN response parsed correctly."""

    def test_home_favoured_negative_spread(self):
        # LAL (home) favoured by 4.5 over BOS (away).
        self.assertEqual(
            agg.parse_odds_detail("LAL -4.5", "LAL", "BOS"),
            -4.5,
        )

    def test_away_favoured_positive_spread(self):
        # NYK (away) favoured by 3 over BOS (home).
        self.assertEqual(
            agg.parse_odds_detail("NYK -3", "BOS", "NYK"),
            3.0,
        )

    def test_pick_em_zero_spread(self):
        for s in ("EVEN", "PK", "Pick", "PICK 'EM"):
            self.assertEqual(
                agg.parse_odds_detail(s, "BOS", "NYK"),
                0.0,
                msg=s,
            )

    def test_malformed_returns_none(self):
        self.assertIsNone(
            agg.parse_odds_detail("", "BOS", "NYK"),
        )
        self.assertIsNone(
            agg.parse_odds_detail("XYZ -7", "BOS", "NYK"),
        )


class TestAggregation(unittest.TestCase):
    """Test 2 — Aggregation produces 1 row per game (no dupes)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="spreads_")
        # Two distinct games on the same date, plus a duplicate event of game 1
        # appearing again to assert dedup.
        payload = {"events": [
            _mock_event("2025-11-05", "LAL", "BOS", "LAL -4.5", 225.5),
            _mock_event("2025-11-05", "NYK", "MIA", "NYK -2", 218.0),
            _mock_event("2025-11-05", "LAL", "BOS", "LAL -4.5", 225.5),  # dup
        ]}
        with open(os.path.join(self.tmp, "20251105.json"), "w") as fh:
            json.dump(payload, fh)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_one_row_per_game(self):
        rows = agg.aggregate(self.tmp)
        # Expect 2 rows (dedup drops the third).
        self.assertEqual(len(rows), 2)
        # Verify column structure on the first row.
        r = rows[0]
        for col in ("game_date", "home_team", "away_team", "home_spread", "total"):
            self.assertIn(col, r, msg=f"missing {col}")
        # LAL row first (alphabetical not enforced — assert via lookup).
        by_home = {r["home_team"]: r for r in rows}
        self.assertEqual(by_home["LAL"]["home_spread"], -4.5)
        self.assertEqual(by_home["LAL"]["away_team"], "BOS")
        self.assertEqual(by_home["NYK"]["home_spread"], -2.0)
        self.assertEqual(by_home["NYK"]["total"], 218.0)


class TestBuilderGraceful(unittest.TestCase):
    """Test 3 — Join graceful when parquet absent."""

    def test_missing_parquet_yields_empty_wrapper(self):
        # Point the builder at a non-existent path.
        wrapper = pp.build_pregame_spreads("/nonexistent/path/pregame_spreads.parquet")
        self.assertEqual(len(wrapper), 0)
        out = wrapper.features("LAL", "BOS",
                                datetime(2025, 11, 5))
        # Both keys present; both None.
        self.assertIsNone(out["home_spread"])
        self.assertIsNone(out["total"])


class TestPlayerPerspectiveSign(unittest.TestCase):
    """Test 4 — Player from home team gets row.home_spread = -X;
    away team gets +X (verify convention)."""

    def test_sign_flip_for_home_vs_away_player(self):
        # Build an in-memory _PregameSpreads with LAL home favoured by 4.5.
        canonical_home_spread = -4.5
        lookup = {
            ("2025-11-05", "LAL", "BOS"): {
                "home_spread": canonical_home_spread,
                "total":       225.5,
            }
        }
        ws = pp._PregameSpreads(lookup)

        # Direct lookup returns canonical sign (LAL home favoured by 4.5).
        raw = ws.features("LAL", "BOS", datetime(2025, 11, 5))
        self.assertEqual(raw["home_spread"], -4.5)
        self.assertEqual(raw["total"], 225.5)

        # Mirror the prop_pergame row-build logic for each player:
        #   home player (LAL): sign=+1  ⇒ row["home_spread"] = -4.5
        #   away player (BOS): sign=-1  ⇒ row["home_spread"] = +4.5
        for is_home, expected in ((True, -4.5), (False, 4.5)):
            with self.subTest(is_home=is_home):
                if is_home:
                    sp_home, sp_away, sign = "LAL", "BOS", 1.0
                else:
                    sp_home, sp_away, sign = "LAL", "BOS", -1.0
                feats = ws.features(sp_home, sp_away, datetime(2025, 11, 5))
                hs = feats["home_spread"]
                self.assertIsNotNone(hs)
                self.assertEqual(sign * hs, expected)


if __name__ == "__main__":
    unittest.main()
