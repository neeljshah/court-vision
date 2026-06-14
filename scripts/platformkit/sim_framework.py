"""Sport-blind simulation framework: one joint sample matrix -> coherent full market surface.

DESIGN: One matrix, every market by counting.
  The key insight from the NBA possession engine (src/sim/basketball_sim.py) and SGP pricer
  (src/sim/sgp_from_sim.py): all markets derived from the SAME (n_sims, n_outcomes) sample
  matrix are internally consistent by construction. P(A win) + P(B win) + P(tie) == 1.0 because
  we count the same sims three ways. Joint/parlay probabilities are the fraction of sims where
  ALL legs hit -- the correlation structure EMERGES from the simulator, no rho-matrix imposed.

  The domain's job: produce a (n_sims, K) matrix via ScoringProcessModel.sample().
  The kernel's job (this file): own every market read-off thereafter.

HONEST framing: this is structure, not alpha. Market efficiency is not claimed; see the
  platform memory (44/44 REJECT, 0 SHIP on real signal catalogs). The framework surfaces
  probabilities; whether any of them beat the market is a gate question, not a counting question.

No src/ or kernel/ edits. Pure numpy + stdlib. <=300 LOC.
"""
from __future__ import annotations

from typing import Callable, Protocol, Sequence, runtime_checkable

import numpy as np


# ---------------------------------------------------------------------------
# Protocol: the domain plug-in contract
# ---------------------------------------------------------------------------

@runtime_checkable
class ScoringProcessModel(Protocol):
    """A sport's simulation model.  The domain owns everything above; the kernel owns everything below.

    sample() returns an (n_sims, K) array where K is the number of outcome dimensions (e.g.
    K=2 for home/away total score, K=N for per-player stats).  The kernel never calls __init__
    directly -- it receives a finished array from the domain.
    """

    def sample(self, n_sims: int, rng_seed: int = 0) -> np.ndarray:
        """Draw n_sims independent game/match outcomes.

        Returns
        -------
        np.ndarray, shape (n_sims, K), dtype float64
            Row i = one simulated outcome; column j = outcome dimension j.
        """
        ...


# ---------------------------------------------------------------------------
# Core: JointDistribution
# ---------------------------------------------------------------------------

class JointDistribution:
    """Wraps a finished (n_sims, n_outcomes) sample matrix and exposes coherent market read-offs.

    All market probabilities are derived by counting over the same n_sims rows, so they are
    internally consistent: prob_side_win(a, b) components sum to exactly 1.0; joint_prob
    can only be called when the joint structure is real (joint_quality == 'simulated').

    Parameters
    ----------
    samples : np.ndarray, shape (n_sims, n_outcomes)
        The joint sample matrix. Copied on construction so the caller can mutate freely.
    joint_quality : str, one of {'simulated', 'copula', 'independent'}
        Describes how the samples were generated.
        - 'simulated'  : full coherent simulation (possession MC, Poisson, etc.) -- joint_prob allowed.
        - 'copula'     : marginals coupled post-hoc via a copula -- joint_prob allowed with caveat.
        - 'independent': marginals sampled independently -- joint_prob REFUSED (independence
                         mis-prices correlated legs; the kernel enforces this boundary).
    """

    _JOINT_CAPABLE = frozenset({"simulated", "copula"})

    def __init__(self, samples: np.ndarray, joint_quality: str = "simulated") -> None:
        if samples.ndim != 2:
            raise ValueError(f"samples must be 2-D (n_sims, n_outcomes); got shape {samples.shape}")
        if joint_quality not in ("simulated", "copula", "independent"):
            raise ValueError(f"joint_quality must be 'simulated', 'copula', or 'independent'; got {joint_quality!r}")
        self._s = np.array(samples, dtype=float)
        self.joint_quality = joint_quality
        self.n_sims, self.n_outcomes = self._s.shape

    # ------------------------------------------------------------------
    # Universal read-off
    # ------------------------------------------------------------------

    def prob_event(self, predicate: Callable[[np.ndarray], np.ndarray]) -> float:
        """P(predicate) -- the universal read-off: mean of a boolean mask over sims.

        Parameters
        ----------
        predicate : callable (samples_array) -> bool array shape (n_sims,)
            Receives the full (n_sims, n_outcomes) matrix; returns a bool mask.

        Examples
        --------
        >>> jd.prob_event(lambda s: s[:, 0] > 110)   # P(home scores > 110)
        """
        mask = predicate(self._s)
        return float(np.asarray(mask, dtype=float).mean())

    # ------------------------------------------------------------------
    # Named market read-offs (all delegate to prob_event internally)
    # ------------------------------------------------------------------

    def prob_over(self, idx_a: int, idx_b: int, line: float) -> float:
        """P(samples[:, idx_a] + samples[:, idx_b] > line) -- totals / over-under market."""
        return self.prob_event(lambda s: s[:, idx_a] + s[:, idx_b] > line)

    def prob_side_win(self, a_idx: int, b_idx: int) -> tuple[float, float, float]:
        """P(A wins), P(B wins), P(tie) -- 1X2 / moneyline.  The three values sum to exactly 1.0."""
        a_arr = self._s[:, a_idx]
        b_arr = self._s[:, b_idx]
        p_a = float((a_arr > b_arr).mean())
        p_b = float((b_arr > a_arr).mean())
        p_tie = float((a_arr == b_arr).mean())
        return p_a, p_b, p_tie

    def prob_spread(self, a_idx: int, b_idx: int, line: float) -> float:
        """P(A - B + line > 0) -- spread / handicap market (A covers when A - B > -line)."""
        return self.prob_event(lambda s: s[:, a_idx] - s[:, b_idx] + line > 0)

    # ------------------------------------------------------------------
    # Joint / parlay read-off (gated on joint_quality)
    # ------------------------------------------------------------------

    def joint_prob(
        self,
        predicates: Sequence[Callable[[np.ndarray], np.ndarray]],
    ) -> tuple[float, float, float]:
        """P(all legs hit), independent product, and correlation lift.

        Replicates the pure counting pattern from src/sim/sgp_from_sim.py::joint_prob, which
        is the NBA reference implementation.  Imported concept only; no runtime import of that
        module to avoid heavy basketball_sim deps.

        Returns
        -------
        (joint, independent, lift) : tuple[float, float, float]
            joint       = fraction of sims where ALL predicates are True (coherent joint prob)
            independent = product of individual marginal probs (independence assumption)
            lift        = joint / independent  (>1 positively correlated, <1 negatively)

        Raises
        ------
        ValueError
            If joint_quality == 'independent': the kernel refuses this call because pricing
            multi-leg markets as independent systematically mis-prices correlated legs.
        """
        if self.joint_quality not in self._JOINT_CAPABLE:
            raise ValueError(
                f"joint_prob() refused: joint_quality={self.joint_quality!r}. "
                "Samples were generated independently; calling joint_prob() on them would "
                "mis-price correlated legs (see sgp_from_sim.py for the NBA reference). "
                "Use a 'simulated' or 'copula' JointDistribution."
            )
        hits = np.ones(self.n_sims, dtype=bool)
        indep = 1.0
        for pred in predicates:
            mask = np.asarray(pred(self._s), dtype=bool)
            hits &= mask
            indep *= float(mask.mean())
        joint = float(hits.mean())
        lift = joint / indep if indep > 1e-9 else float("nan")
        return joint, indep, lift

    # ------------------------------------------------------------------
    # Distribution markets (quantile / mean / interval)
    # ------------------------------------------------------------------

    def quantile(self, idx: int, q: float) -> float:
        """q-th quantile of outcome dimension idx (e.g. median projected score)."""
        return float(np.quantile(self._s[:, idx], q))

    def mean(self, idx: int) -> float:
        """Mean of outcome dimension idx."""
        return float(self._s[:, idx].mean())

    def interval(self, idx: int, alpha: float = 0.80) -> tuple[float, float]:
        """Central (1-alpha) credible interval for outcome dimension idx.

        Returns (lo, hi) such that P(lo <= X <= hi) ~= alpha.
        """
        lo = (1.0 - alpha) / 2.0
        hi = 1.0 - lo
        return (float(np.quantile(self._s[:, idx], lo)), float(np.quantile(self._s[:, idx], hi)))


# ---------------------------------------------------------------------------
# Market surface helper
# ---------------------------------------------------------------------------

def market_surface(jd: JointDistribution, spec: dict) -> dict:
    """Emit a standard market surface dict from one JointDistribution by counting.

    Parameters
    ----------
    jd : JointDistribution
        The wrapped sample matrix.
    spec : dict with keys:
        'home_idx'   : int    -- column index for home/A score
        'away_idx'   : int    -- column index for away/B score
        'total_lines': list[float] -- over/under lines to price (e.g. [210.5, 215.5, 220.5])
        'spread_lines': list[float] -- handicap lines for home/A (e.g. [-3.5, 0.0, +3.5])

    Returns
    -------
    dict with keys:
        'win_home', 'win_away', 'draw'   : moneyline probabilities
        'over_{line}', 'under_{line}'    : total market probs for each line
        'spread_{line:+g}'               : home spread cover prob for each handicap line
        'home_mean', 'away_mean'         : projected mean scores
        'home_q50', 'away_q50'           : median projected scores
        'home_interval_80', 'away_interval_80' : 80% credible intervals
    """
    hi = spec["home_idx"]
    ai = spec["away_idx"]
    p_home, p_away, p_draw = jd.prob_side_win(hi, ai)
    out: dict = {
        "win_home": p_home,
        "win_away": p_away,
        "draw": p_draw,
        "home_mean": jd.mean(hi),
        "away_mean": jd.mean(ai),
        "home_q50": jd.quantile(hi, 0.5),
        "away_q50": jd.quantile(ai, 0.5),
        "home_interval_80": jd.interval(hi, 0.80),
        "away_interval_80": jd.interval(ai, 0.80),
    }
    for line in spec.get("total_lines", []):
        p_over = jd.prob_over(hi, ai, line)
        out[f"over_{line:g}"] = p_over
        out[f"under_{line:g}"] = 1.0 - p_over
    for line in spec.get("spread_lines", []):
        out[f"spread_{line:+g}"] = jd.prob_spread(hi, ai, line)
    return out
