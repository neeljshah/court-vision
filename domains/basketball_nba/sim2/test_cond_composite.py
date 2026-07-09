"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_cond_composite.py -q

Covers the non-trivial v3 logic: offense-relative sign, tercile binning, backoff to
the unconditioned v2 cell, and the strict prior-season exclusion (no leak)."""
from __future__ import annotations

import types

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import N_CELLS, PMAX, MIN_CELL, cell_index
from domains.basketball_nba.sim2 import cond_composite as C


def _v2_stub():
    """Fake v2 model: every cell's PMF is all mass on points=1 (cdf steps at idx 1)."""
    cdf = np.ones((N_CELLS, PMAX + 1))
    cdf[:, 0] = 0.0                      # P(0)=0, P(1)=1 -> pmf mass at 1
    return types.SimpleNamespace(cdf=cdf)


def test_offrel_sign_and_neutral():
    poss = pd.DataFrame({"game_id": ["g1", "g1", "g2"],
                         "off_is_home": [True, False, True]})
    gcd = {"g1": 10.0}                   # g2 has no composite -> neutral 0
    v = C.offrel_values(poss, gcd)
    assert v[0] == 10.0 and v[1] == -10.0 and v[2] == 0.0


def test_comp_bin_edges():
    thr = [-5.0, 5.0]
    got = C.comp_bin(np.array([-6.0, 0.0, 6.0, -5.0, 5.0]), thr)
    # searchsorted right: <-5 ->0 ; in [-5,5) ->1 ; >=5 ->2 (edge lands in upper bin)
    assert list(got) == [0, 1, 2, 1, 2]


def test_backoff_to_v2_when_thin():
    v2 = _v2_stub()
    # dense conditioned cell: base cell 0, comp_b=2, 50 possessions all points=2
    n = MIN_CELL + 10
    df = pd.DataFrame({
        "time_b": np.zeros(n, int), "margin_b": np.zeros(n, int),
        "off_t": np.zeros(n, int), "def_t": np.zeros(n, int), "pace_t": np.zeros(n, int),
        "points": np.full(n, 2, int),
        "game_id": ["g"] * n, "off_is_home": [True] * n,
    })
    gcd = {"g": 100.0}                   # off-relative +100 -> top bin (comp_b=2)
    thr = [-5.0, 5.0]
    m = C.ConditionedPointModel.fit(df, v2, gcd, thr)
    base0 = int(cell_index(0, 0, 0, 0, 0))
    dense = base0 * C.N_COMP + 2
    pmf = np.diff(m.cdf, axis=1, prepend=0.0)
    assert pmf[dense].argmax() == 2               # learned its own PMF (mass at 2)
    # a thin sibling cell (comp_b=0 of same base) backs off to v2 (mass at 1)
    thin = base0 * C.N_COMP + 0
    assert pmf[thin].argmax() == 1
    assert m.n_full6 == 1 and m.n_backoff_v2 == N_CELLS * C.N_COMP - 1


def test_excluded_season_no_prior_returns_empty():
    # 2023-24 has no prior profile window on disk -> strict exclusion, not a fill.
    assert C.game_comp_diff("2023_24") == {}
