"""S450: MLB starting-pitcher strikeout distribution -- arms A/B/C + PMF scoring.

Three arms, all built on the UNEDITED served law (prop_engine_mlb.prop_distribution):
  Arm A = the served call verbatim (exposure=None, no dispersion) -- Poisson.
  Arm B = the SAME call with a fit NB dispersion r (grid-fit on FIT corpus only).
  Arm C = Arm B's lam scaled by a fit opponent-K-rate term, fed into the SAME
          shared pmf fn (domains.soccer.prop_engine._make_p_over) directly.

ONE HISTORY POLICY (S450 AMENDMENT 1(b)): every pool used here (pitcher history via
prop_distribution's own leak guard, the opponent/league K-rate pools in
mlb_pitcher_k_distribution_manifest.py) admits only rows with date STRICTLY BEFORE
the start's own date. This module does its own as-of filtering; it does not rely on
any generic CPCV split to enforce chronology.

PMF adapter (AMENDMENT 1(d)): prop_distribution returns an exceedance callable
(p_over(line) = P(X > line)), never a PMF. ``pmf_from_exceedance`` turns that into a
PMF over the fixed support 0..60, and CRPS / pinball / log-score / K-line exceedance
are computed directly from that PMF (crps_discrete / median_and_pm1 in
props_eval_gate_mlb_dist.py are NOT reused for scoring -- see the memo's amendment
mapping). A residual tail mass >= 1e-9 beyond support 60 is a counted abstention,
never a silently-truncated distribution.

The starter manifest + opponent/league K-rate pools live in
mlb_pitcher_k_distribution_manifest.py (split out under the 300 LOC rail).

Construct/fixture module only -- no network, no data/ read, no real corpus.
Run the per-file test (full pytest freezes the box):
  python -m pytest tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution.py -q
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import pandas as pd

from domains.mlb.prop_engine_mlb import prop_distribution
from domains.soccer.prop_engine import _make_p_over

SUPPORT_MAX = 60
RESIDUAL_EPS = 1e-9
LOG_FLOOR = 1e-9
K_LINES = (3.5, 4.5, 5.5, 6.5, 7.5, 8.5)
# Predeclared grids (FIT corpus only, per AMENDMENT 1(e)). 8.0 is the served,
# never-fit prior (props_eval_gate_mlb_constants.dispersion_for("sp_strikeouts")).
R_GRID = (4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 24.0)
BETA_GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)
MIN_FOLD_N = 30
_STAT = "Pitcher Strikeouts"


# ---------------------------------------------------------------- PMF adapter

def pmf_from_exceedance(p_over, support: int = SUPPORT_MAX) -> Dict[str, object]:
    """Build a PMF over k=0..support from an exceedance callable p_over(line).

    Returns {"status": "ok", "pmf": [p0..p_support], "residual": r} or
    {"status": "abstain", "reason": <str>}. Never raises -- a callable that
    misbehaves (non-finite, out of [0,1], non-monotone, or residual mass >=
    RESIDUAL_EPS past ``support``) is an abstention, counted, not clamped.
    """
    if not callable(p_over):
        return {"status": "abstain", "reason": "p_over_not_callable"}
    prev = 1.0
    pmf: List[float] = []
    for k in range(support + 1):
        try:
            cur = p_over(float(k))
        except Exception:
            return {"status": "abstain", "reason": "p_over_raised"}
        if not isinstance(cur, float) or not math.isfinite(cur):
            return {"status": "abstain", "reason": "non_finite_p_over"}
        if cur < -RESIDUAL_EPS or cur > 1.0 + RESIDUAL_EPS:
            return {"status": "abstain", "reason": "p_over_out_of_range"}
        cur = min(max(cur, 0.0), 1.0)
        mass = prev - cur
        if mass < -RESIDUAL_EPS:
            return {"status": "abstain", "reason": "non_monotone_p_over"}
        pmf.append(max(mass, 0.0))
        prev = cur
    residual = prev
    if residual >= RESIDUAL_EPS:
        return {"status": "abstain", "reason": "residual_mass_exceeds_epsilon"}
    return {"status": "ok", "pmf": pmf, "residual": float(residual)}


# --------------------------------------------------------------- PMF scoring

def crps_from_pmf(pmf: List[float], y: int) -> float:
    """Discrete CRPS of ``pmf`` vs realized count y (Gneiting & Raftery form)."""
    cdf = 0.0
    total = 0.0
    for k in range(len(pmf)):
        cdf += pmf[k]
        indicator = 1.0 if k >= y else 0.0
        total += (cdf - indicator) ** 2
    return float(total)


def quantile_from_pmf(pmf: List[float], q: float) -> float:
    """Smallest k with CDF(k) >= q (standard discrete quantile)."""
    cdf = 0.0
    for k, mass in enumerate(pmf):
        cdf += mass
        if cdf >= q - 1e-12:
            return float(k)
    return float(len(pmf) - 1)


def pinball_from_pmf(pmf: List[float], y: int, q: float) -> float:
    q_pred = quantile_from_pmf(pmf, q)
    diff = float(y) - q_pred
    return float(max(q * diff, (q - 1.0) * diff))


def log_score_from_pmf(pmf: List[float], y: int, floor: float = LOG_FLOOR) -> float:
    p = pmf[y] if 0 <= y < len(pmf) else 0.0
    return float(-math.log(max(p, floor)))


def exceedance_prob_from_pmf(pmf: List[float], k_line: float) -> float:
    """P(X > k_line) recomputed from the PMF (not the original callable)."""
    k_max_included = int(math.floor(k_line))
    cdf = sum(pmf[: k_max_included + 1])
    return float(min(max(1.0 - cdf, 0.0), 1.0))


def brier_at_k_from_pmf(pmf: List[float], y: int, k_line: float) -> float:
    p = exceedance_prob_from_pmf(pmf, k_line)
    outcome = 1.0 if y > k_line else 0.0
    return float((p - outcome) ** 2)


# ------------------------------------------------------------------- arms

def arm_a_forecast(df: pd.DataFrame, player_id, as_of) -> Dict[str, object]:
    """Served law, byte-identical call shape to prop_edge_mlb.py:52."""
    return prop_distribution(df, player_id, _STAT, as_of, exposure=None)


def arm_b_forecast(df: pd.DataFrame, player_id, as_of, r: float) -> Dict[str, object]:
    """Arm A + a fit NB dispersion r (grid-fit on FIT corpus only)."""
    return prop_distribution(df, player_id, _STAT, as_of, exposure=None, dispersion=r)


def arm_c_forecast(df: pd.DataFrame, player_id, as_of, r: float, beta: float,
                   opp_rate: Optional[float], league_rate: Optional[float]) -> Dict[str, object]:
    """Arm B's lam scaled by 1 + beta*(opp_k_rate - league_k_rate), fed into the
    SAME shared pmf fn directly. beta=0.0 always reproduces Arm B exactly
    (AMENDMENT 1(f): the parity check must not depend on opponent-rate
    availability), independent of whether opp_rate/league_rate are known."""
    base = arm_b_forecast(df, player_id, as_of, r)
    if base.get("status") != "ok":
        return dict(base)
    lam_b = base["lam"]
    beta_f = float(beta)
    if beta_f == 0.0:
        scale = 1.0
    else:
        if opp_rate is None or league_rate is None:
            out = dict(base)
            out.update(status="unknown", p_over=None, lam=None,
                       reason="opp_rate_unavailable")
            return out
        try:
            scale = 1.0 + beta_f * (float(opp_rate) - float(league_rate))
        except (TypeError, ValueError):
            out = dict(base)
            out.update(status="unknown", p_over=None, lam=None)
            return out
    lam_c = lam_b * scale
    if not math.isfinite(lam_c) or lam_c < 0.0:
        out = dict(base)
        out.update(status="unknown", p_over=None, lam=None)
        return out
    return {
        "lam": float(lam_c), "model": "negbin",
        "p_over": _make_p_over(lam_c, "negbin", float(r)),
        "status": "ok", "rate": base.get("rate"), "exposure": base.get("exposure"),
        "n": base.get("n", 0),
    }
