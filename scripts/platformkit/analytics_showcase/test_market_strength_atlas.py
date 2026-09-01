"""Fixture-only checks for market_strength_atlas."""
import unittest

import pandas as pd

from scripts.platformkit.analytics_showcase.market_strength_atlas import (
    decimal_odds,
    devig,
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


if __name__ == "__main__":
    unittest.main()
