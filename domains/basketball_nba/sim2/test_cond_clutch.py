"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_cond_clutch.py -q

Covers the non-trivial new logic: NaN-skipping as-of history, full-vs-clutch
rotation-size extraction from stints, and the Q4 scoping (non-Q4 cells must be
byte-identical to v2 regardless of comp_b)."""
from __future__ import annotations

import types

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import (
    N_CELLS, N_TIME, N_MARGIN, PMAX, MIN_CELL, cell_index)
from domains.basketball_nba.sim2 import cond_clutch as C


def test_asof_skipnan_ignores_undefined_games():
    # nan games (never reached the clutch window) must not move the history mean
    got = C._asof_skipnan([float("nan"), 4.0, float("nan"), 8.0], base=0.0, k=1.0)
    assert got == [0.0, 0.0, 2.0, 2.0]


def test_team_game_rotation_full_vs_clutch_window():
    st = pd.DataFrame([
        {"game_id": "g1", "team_id": 1, "period": 1, "start_s": 0.0, "n_on_court": 5,
         "lineup_key": "1,2,3,4,5"},
        {"game_id": "g1", "team_id": 1, "period": 4, "start_s": 100.0, "n_on_court": 5,
         "lineup_key": "1,2,3,4,6"},          # clock_rem=620 -> NOT clutch (tb=3)
        {"game_id": "g1", "team_id": 1, "period": 4, "start_s": 600.0, "n_on_court": 5,
         "lineup_key": "1,2,3,7,8"},          # clock_rem=120 -> clutch (tb=4)
        {"game_id": "g1", "team_id": 1, "period": 4, "start_s": 650.0, "n_on_court": 4,
         "lineup_key": "9,10,11,12"},         # malformed (n_on_court!=5) -> excluded
    ])
    out = C._team_game_rotation(st).set_index(["game_id", "team_id"]).loc[("g1", 1)]
    assert out["full_size"] == 8            # {1,2,3,4,5,6,7,8}, row 4 excluded
    assert out["clutch_size"] == 5          # {1,2,3,7,8}


def _v2_stub():
    cdf = np.ones((N_CELLS, PMAX + 1))
    cdf[:, 0] = 0.0
    return types.SimpleNamespace(cdf=cdf)


def test_scoped_model_passthrough_outside_scope_conditions_inside():
    v2 = _v2_stub()
    n = MIN_CELL + 10
    out_of_scope = pd.DataFrame({           # time_b=0 (Q1) -> must equal v2 regardless of gcd
        "time_b": np.zeros(n, int), "margin_b": np.zeros(n, int),
        "off_t": np.zeros(n, int), "def_t": np.zeros(n, int), "pace_t": np.zeros(n, int),
        "points": np.full(n, 3, int), "game_id": ["g"] * n, "off_is_home": [True] * n,
    })
    in_scope = pd.DataFrame({               # time_b=3 (Q4>3min) -> conditioned
        "time_b": np.full(n, 3, int), "margin_b": np.zeros(n, int),
        "off_t": np.zeros(n, int), "def_t": np.zeros(n, int), "pace_t": np.zeros(n, int),
        "points": np.full(n, 2, int), "game_id": ["g"] * n, "off_is_home": [True] * n,
    })
    df = pd.concat([out_of_scope, in_scope], ignore_index=True)
    gcd = {"g": 100.0}                      # -> top comp bin (comp_b=2), offense-relative +100
    thr = [-5.0, 5.0]
    m = C.ScopedConditionedModel.fit(df, v2, gcd, thr, time_buckets=(3, 4))
    pmf = np.diff(m.cdf, axis=1, prepend=0.0)

    base_q1 = int(cell_index(0, 0, 0, 0, 0))
    for comp_b in (0, 1, 2):
        cell = base_q1 * C.N_COMP + comp_b
        assert pmf[cell].argmax() == 1, "out-of-scope cell must match v2 (mass at 1) always"

    base_q4 = int(cell_index(3, 0, 0, 0, 0))
    dense = base_q4 * C.N_COMP + 2          # this game's possessions land in comp_b=2
    assert pmf[dense].argmax() == 2, "in-scope dense cell learns its own pmf (mass at 2)"
    thin = base_q4 * C.N_COMP + 0           # no possessions here -> backoff to v2
    assert pmf[thin].argmax() == 1
    # every base cell whose time_b isn't in the 2-bucket scope is forced passthrough,
    # regardless of whether the synthetic df touched it (the loop scans all N_CELLS)
    expected_out = (N_TIME - 2) * N_MARGIN * 3 * 3 * 3 * C.N_COMP
    assert m.n_out_of_scope == expected_out
    assert m.n_out_of_scope + m.n_full6 + m.n_backoff_v2 == N_CELLS * C.N_COMP
