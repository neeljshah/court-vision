"""Per-file tests for scripts.platformkit.predictive_validity.absence_swing --
SYNTHETIC boxscore fixtures only.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/predictive_validity/test_absence_swing.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.predictive_validity.absence_swing import (
    MIN_GAMES,
    compute_swing,
    score_index,
    validity_caveat,
    write_artifact,
)

SEASON = "2025-26"


def _synthetic_box() -> pd.DataFrame:
    """Two teams (A, B) play 40 games against each other. Player X (team A)
    plays >=10 min in half the games and 0 min in the other half. When X is
    IN, team A allows fewer points (team B scores less) -- so recomputed
    swing for X must be NEGATIVE. A filler teammate always plays 15 min in
    every A game (keeps team A's boxscore non-empty on X's OUT games)."""
    rng = np.random.default_rng(0)
    rows = []
    n_games = 2 * MIN_GAMES + 4
    for g in range(n_games):
        gid = f"g{g}"
        x_in = g % 2 == 0
        b_pts = rng.normal(95, 3) if x_in else rng.normal(105, 3)  # A allows less when X in
        a_pts = rng.normal(100, 3)
        # team A rows
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "A", "opp": "B", "player_id": 1, "min": 20.0 if x_in else 0.0,
                      "pts": a_pts * 0.3})
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "A", "opp": "B", "player_id": 2, "min": 15.0,
                      "pts": a_pts * 0.7})
        # team B rows (single scorer suffices for team points)
        rows.append({"game_id": gid, "date": f"2025-11-{(g % 28) + 1:02d}", "season": SEASON,
                      "team": "B", "opp": "A", "player_id": 3, "min": 30.0,
                      "pts": b_pts})
    return pd.DataFrame(rows)


def test_absence_swing_sign_and_floor():
    box = _synthetic_box()
    swing = compute_swing(box)
    row = swing[swing["player_id"] == 1]
    assert len(row) == 1
    r = row.iloc[0]
    assert r["n_in"] >= MIN_GAMES and r["n_out"] >= MIN_GAMES
    assert r["swing"] < 0  # team allows FEWER points with player 1 in

    # player 2 (always in, never out) must not qualify -- no OUT games
    assert 2 not in set(swing["player_id"])


def test_below_floor_excluded():
    box = _synthetic_box()
    # trim to below MIN_GAMES qualifying games for a fresh player_id=4
    small = box[box["game_id"].isin([f"g{i}" for i in range(6)])].copy()
    small_p1 = small.copy()
    small_p1["player_id"] = small_p1["player_id"].replace({1: 4})
    swing = compute_swing(pd.concat([box, small_p1], ignore_index=True))
    assert 4 not in set(swing["player_id"])  # too few games either side


def _graded_players_box(n_players: int = MIN_GAMES + 5) -> pd.DataFrame:
    """n_players independent players, each on his own (team, game_id) space,
    with a graded effect size so swings vary player-to-player -- lets
    score_index find a real (non-constant) rank correlation."""
    rng = np.random.default_rng(2)
    n_games = 2 * MIN_GAMES + 4
    rows = []
    for p in range(n_players):
        effect = 2.0 + p * 1.5  # bigger player index -> bigger true effect
        for g in range(n_games):
            gid = f"p{p}_g{g}"
            x_in = g % 2 == 0
            b_pts = rng.normal(100 - (effect if x_in else 0), 3)
            a_pts = rng.normal(100, 3)
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


def test_score_index_finds_planted_correlation():
    box2 = _graded_players_box()
    swing2 = compute_swing(box2)
    # index = "goodness" (bigger effect -> more negative swing -> higher index).
    # score_index correlates index directly against swing (no sign flip), and
    # under this module's sign convention (negative swing = better defense),
    # a valid "goodness" index is NEGATIVELY rank-correlated with swing.
    series2 = {int(pid): -float(s) for pid, s in zip(swing2["player_id"], swing2["swing"])}
    result = score_index("planted", series2, swing2)
    assert result["n"] >= MIN_GAMES
    assert result["rho"] < -0.5
    assert result["verdict"] == "VALID_SIGNAL"
    assert result["ci"]["hi"] < 0


def test_validity_caveat_missing_artifact(tmp_path):
    missing = tmp_path / "nope.json"
    msg = validity_caveat("some_index", path=missing)
    assert "no absence-swing" in msg


def test_validity_caveat_present(tmp_path):
    doc = {
        "as_of": "2026-07-18T00:00:00+00:00",
        "indexes": {"idx": {"rho": 0.52, "ci": {"lo": 0.2, "hi": 0.7}, "n": 50, "verdict": "VALID_SIGNAL"}},
    }
    path = tmp_path / "artifact.json"
    write_artifact(doc, path)
    msg = validity_caveat("idx", path=path)
    assert "rho +0.520" in msg
    assert "n=50" in msg
    assert "VALID_SIGNAL" in msg
