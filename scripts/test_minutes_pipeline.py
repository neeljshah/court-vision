"""
test_minutes_pipeline.py — Demo: minutes-aware prop adjustment for 5 star players.

Shows before/after prop values for a B2B game vs a normal rested game.

Usage:
    python scripts/test_minutes_pipeline.py
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.minutes_predictor import MinutesPredictor
from src.prediction.minutes_aware_props import adjust_props_for_minutes

# ── Star players ──────────────────────────────────────────────────────────────
STARS = [
    {"name": "LeBron James",            "id": 2544,    "season_min": 34.9},
    {"name": "Nikola Jokic",            "id": 203999,  "season_min": 36.7},
    {"name": "Jayson Tatum",            "id": 1628369, "season_min": 36.4},
    {"name": "Shai Gilgeous-Alexander", "id": 1628983, "season_min": 34.2},
    {"name": "Luka Doncic",             "id": 1629029, "season_min": 35.4},
]

# Hypothetical base props (2024-25 season averages, simplified)
BASE_PROPS: dict[int, dict] = {
    2544:    {"pts": 24.4, "reb": 7.8,  "ast": 8.2,  "fg3m": 2.1, "stl": 1.3, "blk": 0.6, "tov": 3.5},
    203999:  {"pts": 29.6, "reb": 12.7, "ast": 10.2, "fg3m": 1.4, "stl": 1.4, "blk": 0.7, "tov": 3.1},
    1628369: {"pts": 26.8, "reb": 8.7,  "ast": 6.0,  "fg3m": 3.3, "stl": 1.1, "blk": 0.5, "tov": 2.9},
    1628983: {"pts": 32.7, "reb": 5.0,  "ast": 6.4,  "fg3m": 2.6, "stl": 2.0, "blk": 0.5, "tov": 2.5},
    1629029: {"pts": 28.2, "reb": 8.2,  "ast": 7.7,  "fg3m": 2.3, "stl": 1.3, "blk": 0.4, "tov": 3.7},
}

# Game contexts
CTX_RESTED = {
    "is_b2b": 0, "rest_days": 2, "games_in_last_7": 2,
    "opponent_strength": "average", "game_importance": "regular",
    "team_blowout_prob": 0.15, "usage_rate": 30.0, "age": 30,
}
CTX_B2B = {
    "is_b2b": 1, "rest_days": 0, "games_in_last_7": 4,
    "opponent_strength": "average", "game_importance": "regular",
    "team_blowout_prob": 0.15, "usage_rate": 30.0, "age": 30,
}


def _pct(new, old):
    if old == 0:
        return 0.0
    return (new - old) / abs(old) * 100


def run_comparison():
    predictor = MinutesPredictor()

    header = (
        f"{'Player':<28} {'Scenario':<10} "
        f"{'Exp Min':>7} {'p_DNP':>6} {'p_Load':>6} "
        f"{'PTS raw':>8} {'PTS adj':>8} "
        f"{'REB raw':>8} {'REB adj':>8} "
        f"{'AST raw':>8} {'AST adj':>8} "
        f"{'Factor':>7}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    for star in STARS:
        pid = star["id"]
        name = star["name"]
        base = BASE_PROPS[pid]
        avg_min = star["season_min"]

        for label, ctx in [("Rested", CTX_RESTED), ("B2B", CTX_B2B)]:
            adj = adjust_props_for_minutes(base, pid, ctx, avg_min, predictor=predictor)

            print(
                f"{name:<28} {label:<10} "
                f"{adj['expected_minutes']:>7.1f} "
                f"{adj['p_dnp']:>6.3f} "
                f"{adj['p_load_mgmt']:>6.3f} "
                f"{base['pts']:>8.1f} {adj['pts']:>8.1f} "
                f"{base['reb']:>8.1f} {adj['reb']:>8.1f} "
                f"{base['ast']:>8.1f} {adj['ast']:>8.1f} "
                f"{adj['minutes_factor']:>7.3f}"
            )

        print("-" * len(header))

    print()
    print("Notes:")
    print("  Factor = expected_minutes / season_avg_minutes")
    print("  Adj stat = raw * (factor ^ elasticity)")
    print("  Elasticity: pts=0.95, reb=1.00, ast=0.95, tov=1.05")
    print("  Rate stats (FG%, FT%, 3P%) are NOT adjusted")


if __name__ == "__main__":
    run_comparison()
