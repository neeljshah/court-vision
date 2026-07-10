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
