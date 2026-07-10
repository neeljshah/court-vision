"""python -m pytest domains/mlb/pitch_engine/test_validate_v4.py -q

Fast: reuses validate_v3.compare_snapshot_v3 (already unit-tested) plus
bullpen_v4's per-team fit/predict path on a tiny synthetic frame -- no
parquet load (the full walk-forward run is the CLI)."""
from __future__ import annotations

import numpy as np

from domains.mlb.pitch_engine.bullpen_v4 import TeamReliever
from domains.mlb.pitch_engine.validate_v4 import _fit, _REGRESSION_EPS
from domains.mlb.pitch_engine.game_sim import GameStart
from domains.mlb.pitch_engine.validate_v3 import compare_snapshot_v3
from domains.mlb.pitch_engine.test_game_sim_v2 import _trans, _removal
from domains.mlb.pitch_engine.test_game_sim_v3 import _dists_v3
from domains.mlb.pitch_engine.test_bullpen_v3 import _team_relief_frame


def test_team_matrices_differ_by_side_and_feed_the_same_compare_snapshot_v3():
    """AAA (high-K) and DDD (low-K) get GENUINELY different matrices when passed
    as the two sides -- confirms v4 conditions on the SPECIFIC simulated team's
    identity, not one shared pooled table (v3/v3_team's inertness)."""
    pa = _team_relief_frame()
    tr = TeamReliever.fit(pa)
    m_aaa, _, _ = tr.team_matrix("AAA")
    m_ddd, _, _ = tr.team_matrix("DDD")
    assert not np.allclose(m_aaa, m_ddd)
    trns = _trans(); rem = _removal(); sp, _ = _dists_v3()
    st = GameStart(inning=7, half=0, home_score=1, away_score=0)
    p1, p4 = compare_snapshot_v3(sp, sp, m_aaa, m_ddd, trns, rem, fh=3, fa=2, st=st, seed=5, n=300)
    assert 0.0 <= p1 <= 1.0 and 0.0 <= p4 <= 1.0


def test_fit_module_importable_and_exposes_run_pieces():
    """Smoke-check the gate module's private _fit signature stays wired to
    bullpen_v4.TeamReliever without a parquet load (import-level only)."""
    assert callable(_fit)
    assert _REGRESSION_EPS > 0
