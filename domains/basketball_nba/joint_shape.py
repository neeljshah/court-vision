"""domains.basketball_nba.joint_shape -- Total-margin dependence for NBA joint distributions.

BACKLOG pa4: replace the independence assumption in predictor.to_jd with a correlated
bivariate normal sampler (Cholesky factor of the 2x2 correlation matrix).  When rho=0
this is identical to the prior independent sampler.  P(margin>0)==p_home_win is
preserved by anchoring mu_M to the Elo win-prob (same approach as predictor.to_jd).

PUBLIC API:
  JointShapeParams -- dataclass: mu_T, sigma_T, mu_M, sigma_M, rho, p_home_win
  fit_corr(box_df)  -- empirical rho from game corpus
  sample_joint(params, n_sims, seed) -> (n_sims, 2): col0=total, col1=margin
  make_jd(params, n_sims, seed) -> JointDistribution (copula quality)
  params_from_predict(pred_output, ...) -> JointShapeParams

INVARIANTS: <=300 LOC; numpy only; calibration not edge; no $ fields; ASCII only.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
import numpy as np

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Empirical NBA total-margin correlation (measured from 1969-game corpus).
# Very close to zero, consistent with "approximately independent" in predictor.to_jd.
# Stored as a sensible default; callers can override via fit_corr() or pass rho directly.
_EMPIRICAL_RHO: float = -0.016

# NBA baseline sigmas (fallback when no corpus available)
_DEFAULT_TOTAL_SIGMA: float = 14.0
_DEFAULT_MARGIN_SIGMA: float = 13.5


# ---------------------------------------------------------------------------
# Parameters dataclass
# ---------------------------------------------------------------------------

@dataclass
class JointShapeParams:
    """Parameters for the correlated (total, margin) bivariate normal sampler.

    Attributes
    ----------
    mu_T : float
        Mean total points (home + away).
    sigma_T : float
        Std dev of total points.
    mu_M : float
        Mean margin (home - away).  Should be anchored to Elo win-prob so that
        P(margin > 0) == p_home_win.
    sigma_M : float
        Std dev of margin.
    rho : float
        Pearson correlation between total and margin.  rho=0 -> independent.
        Must satisfy |rho| < 1.
    p_home_win : float
        The Elo win probability (used only for auditing; mu_M encodes it).
    """
    mu_T: float
    sigma_T: float
    mu_M: float
    sigma_M: float
    rho: float = _EMPIRICAL_RHO
    p_home_win: float = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ndtri_approx(p: float) -> float:
    """Inverse standard-normal CDF (rational approximation; avoids scipy in hot path)."""
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    bb = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((bb[0]*r+bb[1])*r+bb[2])*r+bb[3])*r+bb[4])*r+1.0)


def _anchor_mu_M(p_home_win: float, sigma_M: float) -> float:
    """Return mu_M such that P(margin > 0) == p_home_win under N(mu_M, sigma_M).

    Derivation: P(margin > 0) = P(Z > -mu_M/sigma_M) = Phi(mu_M/sigma_M)
    So mu_M = sigma_M * Phi^{-1}(p_home_win).
    """
    p = min(max(p_home_win, 1e-4), 1.0 - 1e-4)
    return float(_ndtri_approx(p) * sigma_M)


# ---------------------------------------------------------------------------
# Empirical correlation estimator
# ---------------------------------------------------------------------------

def fit_corr(box_df) -> float:
    """Estimate empirical Pearson corr(total, margin) from a game corpus DataFrame.

    Parameters
    ----------
    box_df : pd.DataFrame
        Must have columns 'home_pts' and 'away_pts'.

    Returns
    -------
    float
        Empirical correlation; falls back to _EMPIRICAL_RHO on error or tiny corpus.
    """
    try:
        hp = box_df["home_pts"].to_numpy(dtype=float)
        ap = box_df["away_pts"].to_numpy(dtype=float)
        if len(hp) < 30:
            return _EMPIRICAL_RHO
        total = hp + ap
        margin = hp - ap
        c = float(np.corrcoef(total, margin)[0, 1])
        return c if math.isfinite(c) else _EMPIRICAL_RHO
    except Exception:  # noqa: BLE001
        return _EMPIRICAL_RHO


# ---------------------------------------------------------------------------
# Correlated bivariate normal sampler (Cholesky)
# ---------------------------------------------------------------------------

def sample_joint(
    params: JointShapeParams,
    n_sims: int = 20_000,
    seed: int = 0,
) -> np.ndarray:
    """Draw correlated (total, margin) samples via Cholesky-factored bivariate normal.

    Uses the lower-triangular Cholesky factor of the 2x2 correlation matrix:
        [[1, rho], [rho, 1]] = L @ L.T
        L = [[1, 0], [rho, sqrt(1 - rho^2)]]

    Scales by (sigma_T, sigma_M) and shifts by (mu_T, mu_M).

    Parameters
    ----------
    params : JointShapeParams
    n_sims : int
    seed : int
        Fixed seed -> deterministic output.

    Returns
    -------
    np.ndarray, shape (n_sims, 2)
        Column 0: total_pts (home + away), clipped >= 0.
        Column 1: margin_home (home - away), unconstrained.
    """
    rho = float(np.clip(params.rho, -0.9999, 0.9999))
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_sims, 2))
    # Cholesky: z_corr[i] = L @ z[i].  Vectorised: Z @ L.T
    z0 = z[:, 0]
    z1 = rho * z[:, 0] + math.sqrt(1.0 - rho * rho) * z[:, 1]
    total = params.mu_T + params.sigma_T * z0
    margin = params.mu_M + params.sigma_M * z1
    total = np.clip(total, 0.0, None)
    return np.column_stack([total, margin])


# ---------------------------------------------------------------------------
# JointDistribution factory
# ---------------------------------------------------------------------------

def make_jd(
    params: JointShapeParams,
    n_sims: int = 20_000,
    seed: int = 0,
):
    """Build a JointDistribution of (home_score, away_score) with dependence baked in.

    Converts (total, margin) samples -> (home_score, away_score):
        home_score = (total + margin) / 2,  clipped >= 0
        away_score = (total - margin) / 2,  clipped >= 0

    The returned JointDistribution has joint_quality='copula' because the
    total-margin correlation structure was imposed post-hoc (not from a
    full possession MC sim).

    Parameters
    ----------
    params : JointShapeParams
    n_sims : int
    seed : int

    Returns
    -------
    JointDistribution (scripts.platformkit.sim_framework)
    """
    from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415

    raw = sample_joint(params, n_sims=n_sims, seed=seed)
    total = raw[:, 0]
    margin = raw[:, 1]
    hs = np.clip((total + margin) / 2.0, 0.0, None)
    as_ = np.clip((total - margin) / 2.0, 0.0, None)
    return JointDistribution(np.column_stack([hs, as_]), joint_quality="copula")


# ---------------------------------------------------------------------------
# Convenience: build params from predictor.predict() output
# ---------------------------------------------------------------------------

def params_from_predict(
    pred_output: dict,
    *,
    total_sigma: float = _DEFAULT_TOTAL_SIGMA,
    margin_sigma: float = _DEFAULT_MARGIN_SIGMA,
    rho: float = _EMPIRICAL_RHO,
) -> JointShapeParams:
    """Construct JointShapeParams from the dict returned by NBAPredictor.predict().

    Parameters
    ----------
    pred_output : dict
        Must have keys 'p_home_win' and 'total_mean'.
    total_sigma, margin_sigma : float
        Dispersions (from NBAPredictor.total_sigma / .margin_sigma).
    rho : float
        Total-margin correlation.  Use fit_corr() on the corpus for a data-driven value.

    Returns
    -------
    JointShapeParams
    """
    p_home_win = float(pred_output["p_home_win"])
    mu_T = float(pred_output["total_mean"])
    mu_M = _anchor_mu_M(p_home_win, margin_sigma)
    return JointShapeParams(
        mu_T=mu_T,
        sigma_T=total_sigma,
        mu_M=mu_M,
        sigma_M=margin_sigma,
        rho=rho,
        p_home_win=p_home_win,
    )


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

def _main() -> int:
    params = JointShapeParams(
        mu_T=226.0,
        sigma_T=14.0,
        mu_M=_anchor_mu_M(0.55, 13.5),
        sigma_M=13.5,
        rho=_EMPIRICAL_RHO,
        p_home_win=0.55,
    )
    raw = sample_joint(params, n_sims=50_000, seed=0)
    total = raw[:, 0]
    margin = raw[:, 1]
    emp_rho = float(np.corrcoef(total, margin)[0, 1])
    emp_phw = float(np.mean(margin > 0))
    print(f"target rho={_EMPIRICAL_RHO:.4f}  empirical={emp_rho:.4f}  diff={emp_rho - _EMPIRICAL_RHO:+.4f}")
    print(f"target p_home_win=0.55  empirical={emp_phw:.4f}  diff={emp_phw - 0.55:+.4f}")
    ok_rho = abs(emp_rho - _EMPIRICAL_RHO) <= 0.05
    ok_pw = abs(emp_phw - 0.55) <= 0.01
    print(f"corr_ok={ok_rho}  phw_ok={ok_pw}")
    return 0 if (ok_rho and ok_pw) else 1


if __name__ == "__main__":
    sys.exit(_main())
