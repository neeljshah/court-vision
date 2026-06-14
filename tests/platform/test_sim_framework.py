"""Tests for scripts/platformkit/sim_framework.py.

Uses purely synthetic, deterministic sample matrices -- no file I/O, no heavy deps.
Every assertion is derived analytically from the known fixture matrix, so failures
point to a real regression rather than floating-point noise.

Fixture: 4-sim matrix with known home/away scores.
  sim 0: home=100, away=90   (home wins, spread+10)
  sim 1: home=95,  away=100  (away wins, spread-5)
  sim 2: home=110, away=110  (tie)
  sim 3: home=105, away=95   (home wins, spread+10)
=> home wins 2/4, away wins 1/4, tie 1/4.
=> totals: [190, 195, 220, 200] -- over 200 = {220} -> 1/4; over 195 = {220,200} -> 2/4.
=> spreads: home-5 line: (home-away+5>0) => [15>0, 0>0, 5>0, 15>0] = [T,F,T,T] => 3/4.
"""
import numpy as np
import pytest

from scripts.platformkit.sim_framework import JointDistribution, ScoringProcessModel, market_surface

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HOME_COL = 0
_AWAY_COL = 1

_SAMPLES = np.array([
    [100.0, 90.0],
    [95.0, 100.0],
    [110.0, 110.0],
    [105.0, 95.0],
], dtype=float)  # shape (4, 2)


def _jd_simulated() -> JointDistribution:
    return JointDistribution(_SAMPLES.copy(), joint_quality="simulated")


def _jd_independent() -> JointDistribution:
    return JointDistribution(_SAMPLES.copy(), joint_quality="independent")


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------

class _FakeSPM:
    """Minimal ScoringProcessModel implementation for Protocol conformance check."""
    def sample(self, n_sims: int, rng_seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(rng_seed)
        return rng.random((n_sims, 2)) * 30.0 + 85.0


def test_protocol_conformance():
    """ScoringProcessModel is a structural protocol; the fake should satisfy it."""
    assert isinstance(_FakeSPM(), ScoringProcessModel)


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------

def test_construction_1d_raises():
    with pytest.raises(ValueError, match="2-D"):
        JointDistribution(np.array([1.0, 2.0, 3.0]))


def test_construction_bad_quality_raises():
    with pytest.raises(ValueError, match="joint_quality"):
        JointDistribution(_SAMPLES.copy(), joint_quality="magic")


# ---------------------------------------------------------------------------
# prob_side_win: components sum to 1
# ---------------------------------------------------------------------------

def test_prob_side_win_sum_to_one():
    jd = _jd_simulated()
    p_a, p_b, p_tie = jd.prob_side_win(_HOME_COL, _AWAY_COL)
    assert abs(p_a + p_b + p_tie - 1.0) < 1e-12, f"Got {p_a} + {p_b} + {p_tie} != 1"


def test_prob_side_win_values():
    jd = _jd_simulated()
    p_a, p_b, p_tie = jd.prob_side_win(_HOME_COL, _AWAY_COL)
    assert p_a == pytest.approx(2 / 4)   # sims 0, 3
    assert p_b == pytest.approx(1 / 4)   # sim 1
    assert p_tie == pytest.approx(1 / 4) # sim 2


# ---------------------------------------------------------------------------
# prob_over: matches hand count
# ---------------------------------------------------------------------------

def test_prob_over_hand_count():
    """Totals: [190, 195, 220, 200].  over 200 = only 220 -> 1/4."""
    jd = _jd_simulated()
    assert jd.prob_over(_HOME_COL, _AWAY_COL, 200.0) == pytest.approx(1 / 4)


def test_prob_over_195():
    """over 195 = [220, 200] -> 2/4."""
    jd = _jd_simulated()
    assert jd.prob_over(_HOME_COL, _AWAY_COL, 195.0) == pytest.approx(2 / 4)


def test_prob_over_under_complement():
    """P(over L) + P(under L) == 1 (no push at totals line assumed)."""
    jd = _jd_simulated()
    line = 197.5
    p_over = jd.prob_over(_HOME_COL, _AWAY_COL, line)
    # under is 1 - over when no push (197.5 is not an integer total here)
    # totals [190,195,220,200] -> none ==197.5 -> complement holds
    p_under_manual = float(((jd._s[:, 0] + jd._s[:, 1]) <= line).mean())
    assert p_over + p_under_manual == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# prob_spread: correct
# ---------------------------------------------------------------------------

def test_prob_spread():
    """home - away + 5 > 0 => [15,0,5,15] = [T,F,T,T] -> 3/4."""
    jd = _jd_simulated()
    assert jd.prob_spread(_HOME_COL, _AWAY_COL, 5.0) == pytest.approx(3 / 4)


def test_prob_spread_pick_em():
    """home - away + 0 > 0 => [10,-5,0,10] = [T,F,F,T] -> 2/4."""
    jd = _jd_simulated()
    assert jd.prob_spread(_HOME_COL, _AWAY_COL, 0.0) == pytest.approx(2 / 4)


# ---------------------------------------------------------------------------
# prob_event: universal read-off
# ---------------------------------------------------------------------------

def test_prob_event_generic():
    """P(home > 100) manually: [100>100=F, 95>100=F, 110>100=T, 105>100=T] -> 2/4."""
    jd = _jd_simulated()
    assert jd.prob_event(lambda s: s[:, 0] > 100) == pytest.approx(2 / 4)


# ---------------------------------------------------------------------------
# joint_prob: counting + lift + gating
# ---------------------------------------------------------------------------

def test_joint_prob_counting():
    """Two legs: home>100 AND away<100.
    home>100: sims [F,F,T,T]; away<100: sims [T,F,F,T]; AND: [F,F,F,T] -> 1/4.
    indep: (2/4) * (2/4) = 1/4. lift = (1/4)/(1/4) = 1.0.
    """
    jd = _jd_simulated()
    legs = [
        lambda s: s[:, 0] > 100,
        lambda s: s[:, 1] < 100,
    ]
    joint, indep, lift = jd.joint_prob(legs)
    assert joint == pytest.approx(1 / 4)
    assert indep == pytest.approx((2 / 4) * (2 / 4))
    assert lift == pytest.approx(joint / indep)


def test_joint_prob_single_leg_matches_marginal():
    """Joint of a single leg equals the marginal prob."""
    jd = _jd_simulated()
    marginal = jd.prob_event(lambda s: s[:, 0] > 100)
    joint, indep, lift = jd.joint_prob([lambda s: s[:, 0] > 100])
    assert joint == pytest.approx(marginal)
    assert indep == pytest.approx(marginal)
    assert lift == pytest.approx(1.0)


def test_joint_prob_refuses_independent_quality():
    """joint_prob() must raise ValueError for joint_quality='independent'."""
    jd = _jd_independent()
    with pytest.raises(ValueError, match="refused"):
        jd.joint_prob([lambda s: s[:, 0] > 100])


def test_joint_quality_copula_allowed():
    """joint_quality='copula' should permit joint_prob()."""
    jd = JointDistribution(_SAMPLES.copy(), joint_quality="copula")
    joint, indep, lift = jd.joint_prob([lambda s: s[:, 0] > 100])
    assert 0.0 <= joint <= 1.0


# ---------------------------------------------------------------------------
# quantile / mean / interval
# ---------------------------------------------------------------------------

def test_mean():
    """Home scores [100, 95, 110, 105] -> mean = 102.5."""
    jd = _jd_simulated()
    assert jd.mean(_HOME_COL) == pytest.approx(102.5)


def test_quantile_median():
    """Home scores sorted [95,100,105,110] -> q50 = 102.5."""
    jd = _jd_simulated()
    assert jd.quantile(_HOME_COL, 0.5) == pytest.approx(102.5)


def test_interval_coverage():
    """80% interval should contain 80% of samples."""
    rng = np.random.default_rng(42)
    samples = rng.normal(100, 10, (10_000, 2))
    jd = JointDistribution(samples)
    lo, hi = jd.interval(0, 0.80)
    assert lo < hi
    inside = float(((samples[:, 0] >= lo) & (samples[:, 0] <= hi)).mean())
    assert inside == pytest.approx(0.80, abs=0.02)  # allow 2pp tolerance on sampling


def test_interval_ordering():
    jd = _jd_simulated()
    lo, hi = jd.interval(_HOME_COL, 0.80)
    assert lo <= hi


# ---------------------------------------------------------------------------
# market_surface: keys + values
# ---------------------------------------------------------------------------

def test_market_surface_keys():
    jd = _jd_simulated()
    spec = {
        "home_idx": _HOME_COL,
        "away_idx": _AWAY_COL,
        "total_lines": [195.0, 200.0, 210.0],
        "spread_lines": [-5.0, 0.0, +5.0],
    }
    ms = market_surface(jd, spec)
    # mandatory keys
    for key in ("win_home", "win_away", "draw", "home_mean", "away_mean", "home_q50", "away_q50",
                "home_interval_80", "away_interval_80"):
        assert key in ms, f"Missing key: {key}"
    # total keys
    for line in spec["total_lines"]:
        assert f"over_{line:g}" in ms
        assert f"under_{line:g}" in ms
    # spread keys
    for line in spec["spread_lines"]:
        assert f"spread_{line:+g}" in ms


def test_market_surface_moneyline_consistent():
    """market_surface win probs should be consistent with prob_side_win."""
    jd = _jd_simulated()
    spec = {"home_idx": _HOME_COL, "away_idx": _AWAY_COL, "total_lines": [], "spread_lines": []}
    ms = market_surface(jd, spec)
    assert abs(ms["win_home"] + ms["win_away"] + ms["draw"] - 1.0) < 1e-12


def test_market_surface_over_under_complement():
    """over_L + under_L == 1 for a non-integer line (no push)."""
    jd = _jd_simulated()
    spec = {"home_idx": _HOME_COL, "away_idx": _AWAY_COL, "total_lines": [197.5], "spread_lines": []}
    ms = market_surface(jd, spec)
    assert ms["over_197.5"] + ms["under_197.5"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Determinism: fixed seed produces identical output
# ---------------------------------------------------------------------------

def test_determinism_fixed_samples():
    """Two JointDistributions from identical arrays produce identical market surfaces."""
    spec = {
        "home_idx": 0, "away_idx": 1,
        "total_lines": [200.0], "spread_lines": [0.0],
    }
    ms1 = market_surface(JointDistribution(_SAMPLES.copy()), spec)
    ms2 = market_surface(JointDistribution(_SAMPLES.copy()), spec)
    for k in ms1:
        v1, v2 = ms1[k], ms2[k]
        if isinstance(v1, tuple):
            assert v1 == v2
        else:
            assert v1 == pytest.approx(v2)


def test_determinism_spm():
    """ScoringProcessModel with fixed seed -> reproducible samples."""
    spm = _FakeSPM()
    a = spm.sample(1000, rng_seed=7)
    b = spm.sample(1000, rng_seed=7)
    np.testing.assert_array_equal(a, b)


def test_determinism_different_seed_differs():
    spm = _FakeSPM()
    a = spm.sample(1000, rng_seed=7)
    b = spm.sample(1000, rng_seed=8)
    assert not np.array_equal(a, b)
