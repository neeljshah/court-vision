"""Fixture-only checks for market_strength_atlas."""
import unittest

import pandas as pd

from scripts.platformkit.analytics_showcase.market_strength_atlas import (
    adapt_source,
    decimal_odds,
    devig,
    odds_format,
    prepare_games,
    walk_forward,
)


class MarketStrengthAtlasTests(unittest.TestCase):
    def test_devig_sums_to_one(self):
        home, away = devig(-120, 100)
        self.assertAlmostEqual(home + away, 1.0)
        self.assertGreater(home, away)

    def test_american_and_decimal_conversion(self):
        self.assertAlmostEqual(decimal_odds(-110), 1.0 + 100.0 / 110.0)
        self.assertAlmostEqual(decimal_odds(150), 2.5)
        self.assertAlmostEqual(decimal_odds(1.8), 1.8)
        home, away = devig(1.8, 2.2)
        self.assertAlmostEqual(home, 0.55)
        self.assertAlmostEqual(away, 0.45)

    def test_moneyline_format_uses_same_boundary_as_conversion(self):
        self.assertEqual(odds_format(-110), "american")
        self.assertEqual(odds_format(150), "american")
        self.assertEqual(odds_format(1.8), "decimal")
        self.assertEqual(odds_format(1.0), "invalid")

    def test_consistently_stronger_team_ranks_first(self):
        rows = []
        for i, opponent in enumerate(("B", "C") * 2):
            rows.append({"date": f"2025-01-{i + 1:02d}", "home_team": "A", "away_team": opponent,
                         "home_ml": 1.6666667, "away_ml": 2.5, "total": 0.0, "spread": 0.0})
        _, ratings, _ = walk_forward(prepare_games(pd.DataFrame(rows)), 8, 0)
        self.assertEqual(max(ratings, key=ratings.get), "A")

    def test_prediction_precedes_its_own_line_update(self):
        base = pd.DataFrame([{"date": "2025-01-01", "home_team": "A", "away_team": "B",
                              "home_ml": 2.0, "away_ml": 2.0, "total": 0.0, "spread": 0.0}])
        changed = base.copy()
        changed.loc[0, ["home_ml", "away_ml"]] = [1.1, 8.0]
        first = walk_forward(prepare_games(base), 16, 40)[0][0]["p_model"]
        second = walk_forward(prepare_games(changed), 16, 40)[0][0]["p_model"]
        self.assertAlmostEqual(first, second)
        self.assertAlmostEqual(first, 1.0 / (1.0 + 10.0 ** (-40.0 / 400.0)))

    def test_update_uses_elo_points_once(self):
        games = prepare_games(pd.DataFrame([{
            "date": "2025-01-01", "home_team": "A", "away_team": "B",
            "home_ml": 4 / 3, "away_ml": 4.0,  # Devigged home close is 0.75.
        }]))
        _, ratings, _ = walk_forward(games, 8, 0)
        self.assertAlmostEqual(ratings["A"], 1502.0)
        self.assertAlmostEqual(ratings["B"], 1498.0)

    def test_explicit_mlb_and_tennis_adapters(self):
        mlb, note = adapt_source("mlb", pd.DataFrame([{
            "event_id": "20100404-BOS-NYY-1", "date": "2010-04-04",
            "ml_close_home_am": -117, "ml_close_away_am": -103,
        }]))
        self.assertIsNone(note)
        self.assertEqual(mlb.loc[0, "home_team"], "BOS")
        self.assertEqual(mlb.loc[0, "away_team"], "NYY")

        tennis, note = adapt_source("tennis", pd.DataFrame([{
            "event_id": "20150104-atp-2015-339-103898-106423-10", "date_td": "2015-01-05",
            "ps_p1": 1.53, "ps_p2": 2.67,
        }]))
        self.assertIsNone(note)
        self.assertEqual(tennis.loc[0, "home_team"], "player_103898")
        self.assertEqual(tennis.loc[0, "away_team"], "player_106423")

    def test_soccer_totals_only_source_is_not_adapted(self):
        adapted, note = adapt_source("soccer", pd.DataFrame([{"ou_close_over": 1.9}]))
        self.assertIsNone(adapted)
        self.assertIn("over/under", note)


if __name__ == "__main__":
    unittest.main()
