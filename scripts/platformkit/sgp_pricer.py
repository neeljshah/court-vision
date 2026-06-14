"""scripts.platformkit.sgp_pricer — Sport-blind correlated-leg / SGP pricer.

Surfaces LIFT = joint_prob / independent_product from coherent engine simulations.
HONEST: lift = correlation structure; realized SGP alpha needs real SGP market
prices (user/data-blocked); not a market-beating claim.
INVARIANTS: never edit src/ or kernel/; pure numpy + stdlib; <=300 LOC.
"""
from __future__ import annotations

import textwrap
from typing import Callable, Dict, List

import numpy as np

from scripts.platformkit.sim_framework import JointDistribution

_HONEST_NOTE = (
    "LIFT = correlation structure from engine's coherent joint simulation. "
    "Books that price SGP legs independently misprice this structure. "
    "Realized SGP alpha requires real multi-leg SGP market prices (user/data-blocked). "
    "Not a signal of market-beating capacity."
)
_BANNED_WORDS = {"guaranteed", "beat the market", "profit", "edge"}


# ---------------------------------------------------------------------------
# 1. jd_from_matrix — analytic 2-D PMF matrix -> JointDistribution
# ---------------------------------------------------------------------------

def jd_from_matrix(P: np.ndarray, n_sims: int = 20_000, seed: int = 0) -> JointDistribution:
    """Sample (home, away) score pairs from a 2-D PMF matrix P -> JointDistribution.

    P[i,j] = P(home=i, away=j).  Samples drawn via np.choice over flattened
    probability vector; marginals reproduce P's row/col sums within MC tolerance.
    Returns JointDistribution(samples shape (n_sims,2), joint_quality='simulated').
    """
    P = np.asarray(P, dtype=float)
    if P.ndim != 2:
        raise ValueError(f"P must be 2-D; got shape {P.shape}")
    if np.any(P < 0):
        raise ValueError("P must be non-negative")
    total = P.sum()
    if total <= 0:
        raise ValueError("P must have positive mass")
    P_norm = P / total
    rng = np.random.default_rng(seed)
    flat_idx = rng.choice(P_norm.size, size=n_sims, p=P_norm.ravel())
    rows, cols = np.unravel_index(flat_idx, P_norm.shape)
    samples = np.stack([rows.astype(float), cols.astype(float)], axis=1)
    return JointDistribution(samples, joint_quality="simulated")


# ---------------------------------------------------------------------------
# 2. Leg-builder helpers — predicate factories
# ---------------------------------------------------------------------------

def leg_over_total(idx_a: int, idx_b: int, line: float) -> Callable[[np.ndarray], np.ndarray]:
    """P(col_a + col_b > line) — totals / over-under leg."""
    def _pred(s: np.ndarray) -> np.ndarray:
        return s[:, idx_a] + s[:, idx_b] > line
    return _pred


def leg_side_win(a_idx: int, b_idx: int, winner: str) -> Callable[[np.ndarray], np.ndarray]:
    """Win leg: winner='a' -> P(col_a > col_b); winner='b' -> P(col_b > col_a)."""
    if winner not in ("a", "b"):
        raise ValueError(f"winner must be 'a' or 'b'; got {winner!r}")
    def _pred(s: np.ndarray) -> np.ndarray:
        return s[:, a_idx] > s[:, b_idx] if winner == "a" else s[:, b_idx] > s[:, a_idx]
    return _pred


def leg_score_at_least(idx: int, k: float) -> Callable[[np.ndarray], np.ndarray]:
    """P(samples[:, idx] >= k) — a team/player scores at least k."""
    def _pred(s: np.ndarray) -> np.ndarray:
        return s[:, idx] >= k
    return _pred


# ---------------------------------------------------------------------------
# 3. price_parlay — core pricer
# ---------------------------------------------------------------------------

def price_parlay(
    jd: JointDistribution,
    legs: List[Callable[[np.ndarray], np.ndarray]],
    *,
    vig: float = 0.0,
) -> Dict:
    """Price a correlated multi-leg parlay from a coherent JointDistribution.

    Parameters
    ----------
    jd : JointDistribution  (joint_quality must be 'simulated' or 'copula')
    legs : list of predicate callables on the (n_sims, n_outcomes) matrix
    vig : float  — fractional vig to apply to fair prices (default 0 = vig-free)

    Returns
    -------
    dict: n_legs, joint, independent, lift, fair_decimal_joint,
          fair_decimal_independent, correlation_sign, note.

    Raises
    ------
    ValueError if jd.joint_quality=='independent' (kernel gating honored) or
    if legs is empty.
    """
    if not legs:
        raise ValueError("legs must be non-empty")
    joint, indep, lift = jd.joint_prob(legs)  # raises if quality=='independent'
    fair_j = (1.0 / joint) * (1.0 - vig) if joint > 1e-9 else float("inf")
    fair_i = (1.0 / indep) * (1.0 - vig) if indep > 1e-9 else float("inf")
    if lift > 1.02:
        corr_sign = "positive"
    elif lift < 0.98:
        corr_sign = "negative"
    else:
        corr_sign = "~independent"
    return {
        "n_legs": len(legs),
        "joint": joint,
        "independent": indep,
        "lift": lift,
        "fair_decimal_joint": fair_j,
        "fair_decimal_independent": fair_i,
        "correlation_sign": corr_sign,
        "note": _HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# 4. demo_lift — run against real domain engines; print lift numbers
# ---------------------------------------------------------------------------

def demo_lift() -> None:
    """Build JDs from soccer, MLB, and tennis engines; print lift per sport.

    Soccer : home win AND over 2.5 goals  (lam_home=1.6, lam_away=1.1, rho=-0.1)
    MLB    : home win AND over 8.5 total runs  (lam_home=4.6, lam_away=4.2)
    Tennis : p1 win AND over total games (median+0.5)  (elo_p1=0.65, bo3)

    HONEST: structural correlation only; not a market-beating claim.
    """
    print("\n" + "=" * 68)
    print("SGP PRICER -- CORRELATION LIFT DEMO")
    print("Lift = joint / independent product")
    print(">1 = positively correlated  |  <1 = negatively correlated")
    print("HONEST: structure only; not a market-beating claim; SGP prices blocked")
    print("=" * 68)

    # Soccer
    print("\n--- SOCCER: home win AND over 2.5 goals ---")
    try:
        from domains.soccer.scoreline_engine import scoreline_matrix
        P_soc = scoreline_matrix(1.6, 1.1, rho=-0.1)
        jd_soc = jd_from_matrix(P_soc, n_sims=50_000, seed=7)
        r = price_parlay(jd_soc, [leg_side_win(0, 1, "a"), leg_over_total(0, 1, 2.5)])
        print(f"  joint={r['joint']:.4f}  indep={r['independent']:.4f}"
              f"  lift={r['lift']:.4f}  ({r['correlation_sign']})")
        print(f"  fair_parlay={r['fair_decimal_joint']:.2f}x"
              f"  vs independent_product={r['fair_decimal_independent']:.2f}x")
        if r['lift'] > 1.02:
            print("  -> Structural: home wins AND high-scoring games co-occur "
                  "(home scoring more goals causes both win AND over 2.5).")
        else:
            print("  -> Structural: home 1-0 wins are UNDER 2.5 (DC rho correction "
                  "inflates 0-0/1-1; home wins at 1-0 pull lift toward or below 1).")
    except Exception as exc:
        print(f"  [soccer skipped: {exc}]")

    # MLB
    print("\n--- MLB: home win AND over 8.5 total runs ---")
    try:
        from domains.mlb.inning_engine import runs_matrix
        P_mlb = runs_matrix(4.6, 4.2)
        jd_mlb = jd_from_matrix(P_mlb, n_sims=50_000, seed=13)
        r = price_parlay(jd_mlb, [leg_side_win(0, 1, "a"), leg_over_total(0, 1, 8.5)])
        print(f"  joint={r['joint']:.4f}  indep={r['independent']:.4f}"
              f"  lift={r['lift']:.4f}  ({r['correlation_sign']})")
        print(f"  fair_parlay={r['fair_decimal_joint']:.2f}x"
              f"  vs independent_product={r['fair_decimal_independent']:.2f}x")
        print("  -> Structural: home scoring more runs causes BOTH home win AND "
              "higher total; independent pricing underestimates joint probability.")
    except Exception as exc:
        print(f"  [MLB skipped: {exc}]")

    # Tennis
    print("\n--- TENNIS: p1 win AND over total games (elo_p1=0.65, bo3) ---")
    try:
        from domains.tennis.match_engine import serve_probs_from_winprob, _sim_matches
        ph1, ph2 = serve_probs_from_winprob(0.65, 3, n_sims=2000, seed=0)
        rng = np.random.default_rng(42)
        sims = _sim_matches(ph1, ph2, 3, 50_000, rng).astype(float)
        jd_ten = JointDistribution(sims, joint_quality="simulated")
        med_games = float(np.median(sims[:, 2]))
        r = price_parlay(jd_ten, [
            lambda s: s[:, 0] >= 2,
            lambda s, mg=med_games: s[:, 2] > mg + 0.5,
        ])
        print(f"  joint={r['joint']:.4f}  indep={r['independent']:.4f}"
              f"  lift={r['lift']:.4f}  ({r['correlation_sign']})")
        print(f"  fair_parlay={r['fair_decimal_joint']:.2f}x"
              f"  vs independent_product={r['fair_decimal_independent']:.2f}x")
        print(f"  median_games={med_games:.0f}, ph1={ph1:.3f}, ph2={ph2:.3f}")
        print("  -> Structural: p1 wins are concentrated in 2-0 straight sets "
              "(FEWER total games); over-games and p1-win are NEGATIVELY correlated.")
    except Exception as exc:
        print(f"  [tennis skipped: {exc}]")

    print("\n" + "=" * 68)
    print("NOTE:", textwrap.fill(_HONEST_NOTE, width=66, subsequent_indent="      "))
    print("=" * 68 + "\n")


if __name__ == "__main__":
    demo_lift()
