"""Per-file test for interaction_factory.builders_ingame_state. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_ingame_state.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.interaction_factory import builders_ingame_state as big


def test_ingame_state_diff_col_uses_prefix_convention():
    # asof_quarter_shape.parquet names diff cols diff_<metric>_asof (PREFIX),
    # NOT the box_detail/carryover families' <metric>_diff_asof (SUFFIX).
    assert big._ingame_state_diff_col("q1_margin_asof") == "diff_q1_margin_asof"


def _linescores(n=8):
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "home_q1": [10] * n, "home_q2": [12] * n, "home_q3": [11] * n, "home_q4": [15] * n,
        "away_q1": [9] * n, "away_q2": [10] * n, "away_q3": [10] * n, "away_q4": [9] * n,
    })


def test_rest_of_game_margin_excludes_q1():
    ls = _linescores(3)
    out = big._rest_of_game_margin(ls)
    # home Q2+Q3+Q4 = 38, away Q2+Q3+Q4 = 29 -> margin 9, Q1 (10 vs 9) not counted.
    assert (out["rest_of_game_margin"] == 9).all()
    assert set(out.columns) == {"event_id", "rest_of_game_margin"}


def test_build_frame_merges_diff_cols_and_sets_y():
    ls = _linescores(5)
    asof = pd.DataFrame({
        "event_id": ls["event_id"],
        "diff_q1_margin_asof": [1.0, 2.0, -1.0, 0.5, None],
        "diff_q4_margin_asof": [0.2, -0.3, 1.1, 0.0, 2.0],
    })
    out = big.build_nba_ingame_state_frame(["q1_margin_asof", "q4_margin_asof"], asof, linescores=ls)
    assert {"asof__q1_margin_asof", "asof__q4_margin_asof", "y"} <= set(out.columns)
    assert len(out) == len(ls)  # inner join, every event_id present on both sides
    assert (out["y"] == 9).all()


def test_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(big, "_NBA_QSHAPE_SOURCE", big.Path("/does/not/exist.parquet"))
    assert big._nba_ingame_state_builder(["q1_margin_asof", "q4_margin_asof"], {}) is None


def test_assist_boxdetail_frame_pulls_each_attr_from_its_own_source(monkeypatch):
    # Two DISJOINT game_id sets (the real-world case on disk today: assist's
    # coverage and box-detail's coverage do not overlap) -- the merge must
    # still resolve each attr from the source that actually carries it, and
    # the outer p_base/Elo merge (via the stubbed build_candidate_frame) must
    # not invent rows.
    games = pd.DataFrame({"game_id": ["g1", "g2", "g3"], "home_win": [1.0, 0.0, 1.0]})
    assist = pd.DataFrame({"game_id": ["g1"], "ast_rate_diff_asof": [0.05]})
    boxdetail = pd.DataFrame({"game_id": ["g2"], "fast_break_pts_diff_asof": [3.0]})

    def _stub_build_candidate_frame(games=None, asof=None, feat_col=None):
        out = games.merge(asof[["game_id", feat_col]], on="game_id", how="left")
        out["p_base"] = 0.5
        return out

    monkeypatch.setattr(
        "domains.basketball_nba.asof_ast_rate_eval.build_candidate_frame",
        _stub_build_candidate_frame, raising=False)

    out = big.build_nba_assist_boxdetail_frame(
        ["ast_rate_asof", "fast_break_pts_asof"], assist, boxdetail, games=games)
    assert {"asof__ast_rate_asof", "asof__fast_break_pts_asof", "y"} <= set(out.columns)
    row_g1 = out[out["game_id"] == "g1"].iloc[0]
    row_g2 = out[out["game_id"] == "g2"].iloc[0]
    assert row_g1["asof__ast_rate_asof"] == 0.05
    assert pd.isna(row_g1["asof__fast_break_pts_asof"])
    assert row_g2["asof__fast_break_pts_asof"] == 3.0
    assert pd.isna(row_g2["asof__ast_rate_asof"])


def test_assist_boxdetail_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(big, "_NBA_ASSIST_SOURCE", big.Path("/does/not/exist.parquet"))
    assert big._nba_assist_boxdetail_builder(["ast_rate_asof", "fast_break_pts_asof"], {}) is None
