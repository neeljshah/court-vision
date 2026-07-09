"""Per-file tests: simulator determinism, clock/OT logic, CRPS/PIT correctness."""
import math
import numpy as np

from domains.basketball_nba.sim2.possession_model import N_CELLS, PMAX
from domains.basketball_nba.sim2.pace_model import DMAX, N_DCELLS
from domains.basketball_nba.sim2 import simulator as S


def _cdfs():
    # point PMF: 45% zero, 30% two, 15% three, else spread -> deterministic CDF
    pmf = np.zeros(PMAX + 1)
    pmf[0], pmf[2], pmf[3] = 0.5, 0.35, 0.15
    pcdf = np.tile(np.cumsum(pmf), (N_CELLS, 1))
    pcdf[:, -1] = 1.0
    # duration ~ point mass at 15s
    d = np.zeros(DMAX)
    d[14] = 1.0
    dcdf = np.tile(np.cumsum(d), (N_DCELLS, 1))
    dcdf[:, -1] = 1.0
    return pcdf, dcdf


def test_determinism_under_seed():
    pcdf, dcdf = _cdfs()
    ter = S.GameTerciles(1, 1, 1, 1, 1)
    a = S.simulate(1, 720.0, 0, 0, ter, pcdf, dcdf, n=500, seed=42)
    b = S.simulate(1, 720.0, 0, 0, ter, pcdf, dcdf, n=500, seed=42)
    c = S.simulate(1, 720.0, 0, 0, ter, pcdf, dcdf, n=500, seed=43)
    assert np.array_equal(a, b)          # same seed -> identical
    assert not np.array_equal(a, c)      # different seed -> differs


def test_no_ties_via_ot():
    pcdf, dcdf = _cdfs()
    ter = S.GameTerciles(1, 1, 1, 1, 1)
    fm = S.simulate(1, 720.0, 0, 0, ter, pcdf, dcdf, n=800, seed=0)
    assert np.all(fm != 0)               # OT resolves every tie


def test_late_lead_high_pwin():
    pcdf, dcdf = _cdfs()
    ter = S.GameTerciles(1, 1, 1, 1, 1)
    # home +12 with 30s left in Q4 -> near-certain home win
    fm = S.simulate(4, 30.0, 100, 88, ter, pcdf, dcdf, n=1000, seed=0)
    assert S.p_home_win(fm) > 0.95


def test_crps_gaussian_closed_form():
    # CRPS(N(0,1), 0) = 2*phi(0) - 1/sqrt(pi) = 1/sqrt(2pi)*2... check known value
    val = S.crps_gaussian(0.0, 1.0, 0.0)
    expect = 2.0 * (1.0 / math.sqrt(2 * math.pi)) - 1.0 / math.sqrt(math.pi)
    assert abs(val - expect) < 1e-9


def test_crps_ensemble_matches_gaussian_on_normal():
    rng = np.random.default_rng(0)
    s = rng.normal(3.0, 5.0, 40000)
    ce = S.crps_ensemble(s, 4.0)
    cg = S.crps_gaussian(3.0, 5.0, 4.0)
    assert abs(ce - cg) < 0.15           # ensemble CRPS converges to the Gaussian's


def test_pit_value():
    s = np.arange(0, 100, dtype=float)   # 0..99
    assert abs(S.pit_value(s, 50.0) - 0.505) < 1e-6   # 50 below + half of the tie
    assert S.pit_value(s, -1.0) == 0.0
    assert S.pit_value(s, 200.0) == 1.0
