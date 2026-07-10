"""python -m pytest domains/mlb/pitch_engine/test_bullpen_v4.py -q"""
from __future__ import annotations

import numpy as np

from domains.mlb.pitch_engine.bullpen_v4 import TeamReliever, N_PA
from domains.mlb.pitch_engine.bullpen import N_BUCKET, N_LEAD
from domains.mlb.pitch_engine.pa_chain import _PA_IX
from domains.mlb.pitch_engine.test_bullpen_v3 import _team_relief_frame


def test_direct_cell_reflects_the_teams_own_history_not_the_pooled_mix():
    """AAA (all-K) and DDD (all-OUT) each have >= _TEAM_MIN=40 PAs ONLY at
    (bucket=1, lead=2) -- their direct cells must differ from each other AND
    from a 50/50 pooled mix, proving the matrix conditions on team identity."""
    pa = _team_relief_frame()
    tr = TeamReliever.fit(pa)
    k_ix = _PA_IX["K"]
    m_aaa, nd_a, nf_a = tr.team_matrix("AAA")
    m_ddd, nd_d, nf_d = tr.team_matrix("DDD")
    assert nd_a == 1 and nf_a == N_BUCKET * N_LEAD - 1
    assert nd_d == 1 and nf_d == N_BUCKET * N_LEAD - 1
    assert m_aaa[1, 2, k_ix] > 0.9      # AAA's own reliever pool is all-K
    assert m_ddd[1, 2, k_ix] < 0.1      # DDD's own reliever pool is all-OUT
    assert not np.allclose(m_aaa, m_ddd)


def test_unknown_team_falls_back_on_every_cell():
    pa = _team_relief_frame()
    tr = TeamReliever.fit(pa)
    m, nd, nf = tr.team_matrix("ZZZ")
    assert nd == 0 and nf == N_BUCKET * N_LEAD
    assert np.allclose(m.sum(axis=2), 1.0)
    assert (m >= 0).all()


def test_matrix_shape_and_valid_distribution():
    pa = _team_relief_frame()
    tr = TeamReliever.fit(pa)
    m, _, _ = tr.team_matrix("AAA")
    assert m.shape == (N_BUCKET, N_LEAD, N_PA)
    assert np.allclose(m.sum(axis=2), 1.0)


def test_summary_reports_team_and_cell_counts():
    pa = _team_relief_frame()
    tr = TeamReliever.fit(pa)
    s = tr.summary()
    assert s["n_teams_with_any_direct_cell"] == 2   # AAA, DDD
    assert s["n_direct_cells_total"] == 2            # one cell each
    assert s["cells_per_team"] == N_BUCKET * N_LEAD
