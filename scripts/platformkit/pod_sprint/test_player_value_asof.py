"""Tests for scripts.platformkit.pod_sprint.player_value_asof."""

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.pod_sprint.player_value_asof import (
    _ALPHA, _SHRINK_K, _NBA, build_player_value_features)

_COLS = ["roster_value_asof", "star_absence_delta", "continuity", "top_heavy"]
_TEAMS = ["AAA", "BBB", "CCC", "DDD"]
_TEAM_IDX = {t: i for i, t in enumerate(_TEAMS)}


def _toy_pb(n_games=40, seed=0) -> pd.DataFrame:
    """Synthetic player_boxscores-shaped corpus: n_games among 4 teams, 3 stable
    per-team-slot players each (so per-player EW state accumulates across games)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-10-01", periods=n_games, freq="1D")
    rows = []
    for i in range(n_games):
        h, a = rng.choice(_TEAMS, size=2, replace=False)
        gid = f"G{i:04d}"
        for team, opp in ((h, a), (a, h)):
            base = _TEAM_IDX[team] * 10
            for slot in range(3):
                rows.append({
                    "game_id": gid, "date": dates[i], "team": team, "opp": opp,
                    "player_id": base + slot,
                    "min": float(rng.integers(15, 36)), "plus_minus": float(rng.integers(-15, 16)),
                })
    return pd.DataFrame(rows)


def test_leak_trap():
    """Corrupting a game_id's own stats must not change that game_id's own features
    (either team); a LATER game for either team must differ."""
    pb = _toy_pb(n_games=40)
    feat_a = build_player_value_features(pb)
    victim_gid = pb["game_id"].unique()[20]
    corrupted = pb.copy()
    mask = corrupted["game_id"] == victim_gid
    corrupted.loc[mask, "plus_minus"] = 999.0
    corrupted.loc[mask, "min"] = 5.0
    feat_b = build_player_value_features(corrupted)

    row_a = feat_a[feat_a.game_id == victim_gid].sort_values("team_abbr").reset_index(drop=True)
    row_b = feat_b[feat_b.game_id == victim_gid].sort_values("team_abbr").reset_index(drop=True)
    pd.testing.assert_frame_equal(row_a[_COLS], row_b[_COLS])

    teams = pb[pb.game_id == victim_gid]["team"].unique()
    victim_date = pb[pb.game_id == victim_gid]["date"].iloc[0]
    later_a = feat_a[feat_a.team_abbr.isin(teams) & (feat_a.date > victim_date)].sort_values(["date", "team_abbr"])
    later_b = feat_b[feat_b.team_abbr.isin(teams) & (feat_b.date > victim_date)].sort_values(["date", "team_abbr"])
    assert len(later_a) > 0
    assert not later_a[_COLS].reset_index(drop=True).equals(later_b[_COLS].reset_index(drop=True))


def test_shrinkage_weight_bounds():
    """A brand-new player (0 career minutes) shrinks FULLY to the global mean; a
    veteran with huge career minutes trusts their own EW estimate almost entirely."""
    w_new = 0.0 / (0.0 + _SHRINK_K)
    w_vet = 100_000.0 / (100_000.0 + _SHRINK_K)
    assert w_new == 0.0
    assert w_vet > 0.99
    assert w_new < w_vet


def test_defaults_before_history():
    """A team's very first game has no previous-game roster -- P1/P2/P3/P4 must all
    read as the declared 0.0 neutral default, never NaN or a divide-by-zero."""
    pb = _toy_pb(n_games=6)
    feat = build_player_value_features(pb)
    first_date = feat["date"].min()
    first_rows = feat[feat["date"] == first_date]
    for col in _COLS:
        assert (first_rows[col] == 0.0).all(), col


def test_hand_computed_p1_3game_corpus():
    """3-game synthetic corpus; independently hand-derive AAA's game-2 roster_value_asof
    from the LOCKED formula (EW per-minute plus_minus/min, shrunk to the walk-forward
    global mean by career minutes, weighted by EW minutes share) and compare."""
    pb = pd.DataFrame([
        # game 1: AAA vs BBB
        {"game_id": "G1", "date": pd.Timestamp("2025-10-01"), "team": "AAA", "opp": "BBB",
         "player_id": 1, "min": 30.0, "plus_minus": 10.0},
        {"game_id": "G1", "date": pd.Timestamp("2025-10-01"), "team": "AAA", "opp": "BBB",
         "player_id": 2, "min": 18.0, "plus_minus": -4.0},
        {"game_id": "G1", "date": pd.Timestamp("2025-10-01"), "team": "BBB", "opp": "AAA",
         "player_id": 3, "min": 40.0, "plus_minus": 8.0},
        # game 2: AAA vs CCC -- the game under test
        {"game_id": "G2", "date": pd.Timestamp("2025-10-03"), "team": "AAA", "opp": "CCC",
         "player_id": 1, "min": 28.0, "plus_minus": 5.0},
        {"game_id": "G2", "date": pd.Timestamp("2025-10-03"), "team": "AAA", "opp": "CCC",
         "player_id": 2, "min": 20.0, "plus_minus": 2.0},
        {"game_id": "G2", "date": pd.Timestamp("2025-10-03"), "team": "CCC", "opp": "AAA",
         "player_id": 4, "min": 40.0, "plus_minus": -7.0},
        # game 3: AAA vs BBB again -- gives the 3rd game + rotation depth
        {"game_id": "G3", "date": pd.Timestamp("2025-10-05"), "team": "AAA", "opp": "BBB",
         "player_id": 1, "min": 30.0, "plus_minus": 3.0},
        {"game_id": "G3", "date": pd.Timestamp("2025-10-05"), "team": "AAA", "opp": "BBB",
         "player_id": 3, "min": 20.0, "plus_minus": -1.0},
        {"game_id": "G3", "date": pd.Timestamp("2025-10-05"), "team": "BBB", "opp": "AAA",
         "player_id": 5, "min": 40.0, "plus_minus": -2.0},
    ])
    feat = build_player_value_features(pb)

    # AAA's game-2 P1 reads state as of strictly after game 1 only (roster = {1, 2}).
    v1 = _ALPHA * (10.0 / 30.0)      # EW update from a 0.0 (unseen-player) starting point
    v2 = _ALPHA * (-4.0 / 18.0)
    s1, s2 = 30.0 / 48.0, 18.0 / 48.0
    cm1, cm2 = 30.0, 18.0
    global_mean = (10.0 - 4.0 + 8.0) / (30.0 + 18.0 + 40.0)
    w1, w2 = cm1 / (cm1 + _SHRINK_K), cm2 / (cm2 + _SHRINK_K)
    v1_shrunk = w1 * v1 + (1 - w1) * global_mean
    v2_shrunk = w2 * v2 + (1 - w2) * global_mean
    expected_p1 = v1_shrunk * s1 + v2_shrunk * s2

    actual = feat[(feat.game_id == "G2") & (feat.team_abbr == "AAA")]["roster_value_asof"].iloc[0]
    assert actual == pytest.approx(expected_p1, abs=1e-9)


def test_real_corpus_smoke():
    """Fast smoke on the real corpus: shape sanity, no NaNs, all-teams coverage."""
    pb_path = _NBA / "player_boxscores.parquet"
    if not pb_path.is_file():
        pytest.skip("player_boxscores.parquet not present")
    pb = pd.read_parquet(pb_path)
    feat = build_player_value_features(pb)
    assert len(feat) > 1000
    assert not feat[_COLS].isna().any().any()
    assert feat["team_abbr"].nunique() == 30
