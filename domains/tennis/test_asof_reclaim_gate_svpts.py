"""Per-file test for the svpts_won_* CANDIDATES rows added to
domains.tennis.asof_reclaim_gate (utilization_matrix_2026_07_10.md wiring item:
svpts-won% overall + per-surface, built in asof_hold.parquet, never gated before).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/test_asof_reclaim_gate_svpts.py -q
"""
from __future__ import annotations

import pytest

from domains.tennis.asof_reclaim_gate import CANDIDATES, gate_feature

_SVPTS_NAMES = {
    "svpts_won_diff_asof", "svpts_won_hard_diff_asof",
    "svpts_won_clay_diff_asof", "svpts_won_grass_diff_asof",
}


def test_svpts_candidates_registered():
    names = {spec[0] for spec in CANDIDATES}
    assert _SVPTS_NAMES <= names


@pytest.mark.parametrize("feat_col", sorted(_SVPTS_NAMES))
def test_svpts_candidate_gates_without_error(feat_col):
    spec = next(s for s in CANDIDATES if s[0] == feat_col)
    res = gate_feature(feat_col, spec)
    assert res["feature"] == feat_col
    assert res["n_rows"] > 0
    assert res["vs_elo"]["real"]["verdict"] in ("SHIP", "REJECT", "NOT_TESTABLE")
