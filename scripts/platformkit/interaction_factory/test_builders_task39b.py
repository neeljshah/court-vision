"""Per-file test for interaction_factory.builders_task39b. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_task39b.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.interaction_factory import builders_task39b as b


def _nba_synthetic():
    """games + boxdetail-asof sidecar (1 row absent), same convention as
    test_asof_ast_rate_eval.py's fixture -- diff col name matches the
    registry's <attr>_asof -> <attr>_diff_asof mapping."""
    rng = np.random.default_rng(3)
    n = 60
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    gids = [f"00{i:08d}" for i in range(n)]
    games = pd.DataFrame({
        "game_id": gids, "date": dates, "season": "2023-24",
        "home_team": [f"T{i % 8}" for i in range(n)],
        "away_team": [f"T{(i + 3) % 8}" for i in range(n)],
        "home_win": rng.integers(0, 2, n).astype(float),
    })
    asof = pd.DataFrame({
        "game_id": gids[:-1],
        "fast_break_pts_diff_asof": rng.normal(0, 2.0, n - 1),
        "home_n_prior": rng.integers(0, 10, n - 1),
        "away_n_prior": rng.integers(0, 10, n - 1),
    })
    return games, asof


def test_nba_boxdetail_diff_col_strips_asof_suffix():
    assert b._nba_boxdetail_diff_col("fast_break_pts_asof") == "fast_break_pts_diff_asof"
    assert b._nba_boxdetail_diff_col("no_suffix") == "no_suffix_diff_asof"


def test_build_nba_boxdetail_frame_renames_and_handles_missing_row():
    games, asof = _nba_synthetic()
    out = b.build_nba_boxdetail_frame(["fast_break_pts_asof"], asof, games=games)
    assert "asof__fast_break_pts_asof" in out.columns
    assert {"game_id", "home_win", "p_base", "y"} <= set(out.columns)
    # the row with no asof sidecar entry must be an honest NaN, never fabricated
    assert out["asof__fast_break_pts_asof"].isna().sum() == 1


def _mlb_profiles(rows):
    return pd.DataFrame(rows, columns=["entity_id", "window", "attribute", "raw_value"])


def test_build_mlb_battrack_frame_shifts_outcome_season_back_one():
    rows = [
        ("p1", "season_2024", "bat_speed", 75.0),
        ("p1", "season_2025", "contact_quality", 0.31),
        ("p2", "season_2024", "bat_speed", 70.0),
        ("p2", "season_2024", "contact_quality", 0.28),  # wrong season for p2 -> no (Y,Y+1) match
    ]
    out = b.build_mlb_battrack_frame(_mlb_profiles(rows), ["bat_speed", "contact_quality"])
    assert len(out) == 1
    assert out.iloc[0]["entity_id"] == "p1"
    assert out.iloc[0]["asof__bat_speed"] == 75.0
    assert out.iloc[0]["y"] == 0.31


def test_build_mlb_battrack_frame_no_overlap_returns_empty_not_crash():
    """Failure mode: bat-tracking and contact_quality corpora with zero
    (season-Y, season-Y+1) overlap must yield 0 rows honestly, not raise and
    not silently fabricate a merged row."""
    rows = [("p1", "season_2024", "bat_speed", 75.0)]  # no contact_quality at all
    out = b.build_mlb_battrack_frame(_mlb_profiles(rows), ["bat_speed", "contact_quality"])
    assert len(out) == 0
    assert "y" in out.columns


def test_build_tennis_match_frame_merges_return_and_features():
    matches = pd.DataFrame({"event_id": [1, 2], "tourney_id": ["t1", "t1"], "winner": [1, 2]})
    ret = pd.DataFrame({"event_id": [1, 2], "diff_return_asof": [0.1, -0.2]})
    feats = pd.DataFrame({"event_id": [1, 2], "diff_return_asof": [9.9, 9.9], "diff_serve_asof": [0.3, 0.4]})
    setdetail = pd.DataFrame({"event_id": [1, 2], "avg_games_per_set_asof_diff": [1.5, -1.5]})
    out = b.build_tennis_match_frame(matches, ret, feats,
                                      ["diff_return_asof", "diff_serve_asof", "avg_games_per_set_asof_diff"],
                                      setdetail=setdetail)
    assert list(out["y"]) == [1.0, 0.0]
    assert "asof__diff_return_asof" in out.columns and "asof__diff_serve_asof" in out.columns
    # a column present in BOTH ret and feats must come from ret (feats' duplicate ignored)
    assert out.loc[out["event_id"] == 1, "asof__diff_return_asof"].iloc[0] == 0.1
    # the 3rd source (asof_setdetail.parquet) merges in too, non-null.
    assert "asof__avg_games_per_set_asof_diff" in out.columns
    assert out["asof__avg_games_per_set_asof_diff"].notna().all()


def test_build_tennis_match_frame_setdetail_col_not_shadowed_by_ret_or_feats():
    # a name present in setdetail AND (ret or feats) must come from the
    # earlier source -- same precedence rule task-1's ret-over-feats already
    # locks in, extended to the 3rd source.
    matches = pd.DataFrame({"event_id": [1], "tourney_id": ["t1"], "winner": [1]})
    ret = pd.DataFrame({"event_id": [1], "dup_col": [0.1]})
    feats = pd.DataFrame({"event_id": [1]})
    setdetail = pd.DataFrame({"event_id": [1], "dup_col": [9.9]})
    out = b.build_tennis_match_frame(matches, ret, feats, ["dup_col"], setdetail=setdetail)
    assert out.loc[0, "asof__dup_col"] == 0.1


def test_build_soccer_match_frame_derives_home_win_from_goals():
    matches = pd.DataFrame({"event_id": [1, 2], "div": ["E0", "E0"], "fthg": [2, 0], "ftag": [1, 3]})
    feats = pd.DataFrame({"event_id": [1, 2], "diff_xg_asof": [0.4, -0.1]})
    xg = pd.DataFrame({"event_id": [1, 2], "diff_xg_supremacy_asof": [0.2, -0.3]})
    out = b.build_soccer_match_frame(matches, feats, ["diff_xg_asof", "diff_xg_supremacy_asof"], xg=xg)
    assert list(out["y"]) == [1.0, 0.0]
    assert "asof__diff_xg_asof" in out.columns
    # the 3rd source (asof_xg_proxy.parquet) merges in too, non-null.
    assert "asof__diff_xg_supremacy_asof" in out.columns
    assert out["asof__diff_xg_supremacy_asof"].notna().all()
