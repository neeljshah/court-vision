"""Per-file test for interaction_factory.builders_state_conditioner (A22a).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_state_conditioner.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_state_conditioner as bsc
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template registration shape: nba_state_conditioner reuses the SAME
# TEMPLATES dict shape + Candidate dataclass every other template uses (no
# new machinery), a cross between the two families the flagship conditioner
# needs (carryover_asof / ingame_state_asof).
def test_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["nba_state_conditioner"]
    assert tpl["sport"] == "basketball_nba"
    assert tpl["pairing"] == "cross"
    assert tpl["outcome"] == "rest_of_game_margin"
    assert tpl["left_pool"] == {"entity": "team", "family": "carryover_asof"}
    assert tpl["right_pool"] == {"entity": "team", "family": "ingame_state_asof"}
    assert tpl["feature_builder"] == "nba_state_conditioner_asof"


def test_builder_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["nba_state_conditioner_asof"] is bsc._nba_state_conditioner_builder


# --------------------------------------------------------------------------
# 2. Candidate enumeration non-empty, and the flagship b2b_rest_penalty x
# realized-early-state conditioner (rest_days_asof x q1_margin_asof, #14 x
# #34) is among them -- a Candidate object, same dataclass every other
# template's enumeration produces.
def test_enumeration_nonempty_and_includes_flagship_conditioner():
    cands = GEN.enumerate_candidates("nba_state_conditioner")
    assert len(cands) > 0
    assert all(isinstance(c, GEN.Candidate) for c in cands)
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("rest_days_asof", "q1_margin_asof") in pairs
    flagship = next(c for c in cands if (c.attr_a, c.attr_b) == ("rest_days_asof", "q1_margin_asof"))
    assert flagship.template_id == "nba_state_conditioner"
    assert flagship.feature_builder == "nba_state_conditioner_asof"


# --------------------------------------------------------------------------
# 3. Builder frame: synthetic carryover (SUFFIX cols, keyed game_id) +
# qshape (PREFIX cols, keyed game_id+event_id, doubling as the bridge) +
# linescores (keyed event_id) -> one asof__ column per attr, correct y.
def _carryover(n=4):
    return pd.DataFrame({
        "game_id": [f"g{i}" for i in range(n)],
        "rest_days_diff_asof": [0.0, 1.0, -1.0, 2.0],
        "heavy_min_load_diff_asof": [3.0, -2.0, 1.5, 0.0],
    })


def _qshape(n=4):
    return pd.DataFrame({
        "game_id": [f"g{i}" for i in range(n)],
        "event_id": [f"e{i}" for i in range(n)],
        "diff_q1_margin_asof": [1.0, -1.0, 0.5, 2.0],
    })


def _linescores(n=4):
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "home_q1": [10] * n, "home_q2": [12] * n, "home_q3": [11] * n, "home_q4": [15] * n,
        "away_q1": [9] * n, "away_q2": [10] * n, "away_q3": [10] * n, "away_q4": [9] * n,
    })


def test_build_frame_merges_both_conventions_and_sets_y():
    out = bsc.build_nba_state_conditioner_frame(
        ["rest_days_asof", "q1_margin_asof"], _carryover(), _qshape(), linescores=_linescores())
    assert {"asof__rest_days_asof", "asof__q1_margin_asof", "y"} <= set(out.columns)
    assert len(out) == 4
    assert (out["y"] == 9).all()  # home Q2+Q3+Q4=38, away=29 -> 9 (same fixture as ingame_state's own test)
    assert out["asof__rest_days_asof"].tolist() == [0.0, 1.0, -1.0, 2.0]
    assert out["asof__q1_margin_asof"].tolist() == [1.0, -1.0, 0.5, 2.0]


def test_build_frame_drops_unknown_attr_without_crash():
    # negative case: an attr present in NEITHER source -> honestly dropped
    # (no asof__ column for it), no crash -- the missing asof__ column is
    # what makes runner._fit_candidate call this candidate NOT_TESTABLE.
    out = bsc.build_nba_state_conditioner_frame(
        ["rest_days_asof", "not_a_real_attr"], _carryover(), _qshape(), linescores=_linescores())
    assert "asof__rest_days_asof" in out.columns
    assert "asof__not_a_real_attr" not in out.columns


def test_build_frame_all_unknown_attrs_returns_empty_frame_without_crash():
    out = bsc.build_nba_state_conditioner_frame(
        ["not_a_real_attr"], _carryover(), _qshape(), linescores=_linescores())
    assert list(out.columns) == ["event_id", "y"]
    assert len(out) == 0


def test_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bsc, "_NBA_CARRYOVER_SOURCE", Path("/does/not/exist.parquet"))
    assert bsc._nba_state_conditioner_builder(["rest_days_asof", "q1_margin_asof"], {}) is None
