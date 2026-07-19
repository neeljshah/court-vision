"""Per-file tests for scripts.platformkit.predictive_validity.absence_swing_offense
-- SYNTHETIC boxscore fixtures only.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/predictive_validity/test_absence_swing_offense.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.predictive_validity.absence_swing import MIN_GAMES
from scripts.platformkit.predictive_validity.absence_swing_offense import (
    compute_swing_offense,
    score_offense_index,
)

SEASON = "2025-26"


def _synthetic_box() -> pd.DataFrame:
    """Team A plays 40 games vs team B. Player X (team A) plays >=10 min in
    half the games, 0 min in the other half. When X is IN, team A SCORES
    MORE -- so recomputed offensive swing for X must be POSITIVE (opposite
    sign of the defensive-swing fixture in test_absence_swing.py, which
    varies points ALLOWED)."""
    rng = np.random.default_rng(0)
    rows = []
    n_games = 2 * MIN_GAMES + 4
    for g in range(n_games):
        gid = f"g{g}"
        x_in = g % 2 == 0
        a_pts = rng.normal(105, 3) if x_in else rng.normal(95, 3)  # A scores more when X in
        b_pts = rng.normal(100, 3)
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "A", "opp": "B", "player_id": 1, "min": 20.0 if x_in else 0.0,
                      "pts": a_pts * 0.3})
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "A", "opp": "B", "player_id": 2, "min": 15.0,
                      "pts": a_pts * 0.7})
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "B", "opp": "A", "player_id": 3, "min": 30.0,
                      "pts": b_pts})
    return pd.DataFrame(rows)


def test_offense_swing_sign_and_floor():
    box = _synthetic_box()
    swing = compute_swing_offense(box)
    row = swing[swing["player_id"] == 1]
    assert len(row) == 1
    r = row.iloc[0]
    assert r["n_in"] >= MIN_GAMES and r["n_out"] >= MIN_GAMES
    assert r["swing"] > 0  # team scores MORE points with player 1 in

    assert 2 not in set(swing["player_id"])  # never OUT -- doesn't qualify


def test_below_floor_excluded():
    box = _synthetic_box()
    small = box[box["game_id"].isin([f"g{i}" for i in range(6)])].copy()
    small_p1 = small.copy()
    small_p1["player_id"] = small_p1["player_id"].replace({1: 4})
    swing = compute_swing_offense(pd.concat([box, small_p1], ignore_index=True))
    assert 4 not in set(swing["player_id"])


def _graded_players_box(n_players: int = MIN_GAMES + 5) -> pd.DataFrame:
    """n_players independent players with a graded true offensive effect
    size, so score_offense_index can find a real rank correlation."""
    rng = np.random.default_rng(2)
    n_games = 2 * MIN_GAMES + 4
    rows = []
    for p in range(n_players):
        effect = 2.0 + p * 1.5
        for g in range(n_games):
            gid = f"p{p}_g{g}"
            x_in = g % 2 == 0
            a_pts = rng.normal(100 + (effect if x_in else 0), 3)
            b_pts = rng.normal(100, 3)
            rows.append({"game_id": gid, "date": "2025-11-01", "season": SEASON,
                         "team": f"A{p}", "opp": f"B{p}", "player_id": p,
                         "min": 20.0 if x_in else 0.0, "pts": a_pts * 0.3})
            rows.append({"game_id": gid, "date": "2025-11-01", "season": SEASON,
                         "team": f"A{p}", "opp": f"B{p}", "player_id": 1000 + p,
                         "min": 15.0, "pts": a_pts * 0.7})
            rows.append({"game_id": gid, "date": "2025-11-01", "season": SEASON,
                         "team": f"B{p}", "opp": f"A{p}", "player_id": 2000 + p,
                         "min": 30.0, "pts": b_pts})
    return pd.DataFrame(rows)


def test_score_offense_index_full_independence_finds_planted_correlation():
    box2 = _graded_players_box()
    swing2 = compute_swing_offense(box2)
    # index = "goodness" (bigger effect -> more positive swing); score
    # directly against swing under the "full" independence label.
    series2 = {int(pid): float(s) for pid, s in zip(swing2["player_id"], swing2["swing"])}
    result = score_offense_index("planted_shooter", series2, "full", swing2)
    assert result["n"] >= MIN_GAMES
    assert result["rho"] > 0.5
    assert result["verdict"] == "VALID_SIGNAL"
    assert result["ci"]["lo"] > 0
    assert result["judge_independence"] == "full"


def test_score_offense_index_partial_overlap_relabels_verdict():
    box2 = _graded_players_box()
    swing2 = compute_swing_offense(box2)
    series2 = {int(pid): float(s) for pid, s in zip(swing2["player_id"], swing2["swing"])}
    result = score_offense_index("planted_gravity", series2, "partial_overlap", swing2)
    assert result["verdict"] == "VALID_SIGNAL_PARTIAL_JUDGE"
    assert result["judge_independence"] == "partial_overlap"


def test_score_offense_index_null_stays_null_even_if_partial():
    # empty series -> NULL verdict must not be relabeled to PARTIAL_JUDGE
    swing = compute_swing_offense(_synthetic_box())
    result = score_offense_index("empty_idx", {}, "partial_overlap", swing)
    assert result["verdict"] == "NULL"
