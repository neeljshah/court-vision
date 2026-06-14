"""domains.soccer.finishing_prior — finishing-residual shrinkage on Poisson lambdas.

APPROACH: The EW goals-for rate already absorbs SoT level (blending raw SoT = null,
W59 proof).  INSTEAD we shrink the lambda by the FINISHING RESIDUAL:
    residual = EW(goals_for - K_CONV * SoT_for)   (hot/cold finishing streak)
    lam_adj  = lam_baseline - SHRINK_MASS * residual
Hot teams (residual>0) regress down; cold teams (residual<0) regress up.
SHRINK_MASS=0.25 is pinned, never auto-tuned (artifact risk).

NO-EDGE DISCIPLINE: calibration/accuracy only; gate decides signal merit; NO edge.
PRIVATE: data/domains/soccer/ gitignored; F5-compliant (no src.*/kernel.* imports).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.soccer.config import DATA_DIR_REL, ALPHA, PRIOR_GF, PRIOR_GA, RATE_CLIP
from domains.soccer.ratings import walk_forward_goals, _p_over
from domains.soccer.scoreline_engine import scoreline_matrix, markets_from_matrix
from domains.soccer.finishing_asof import build_asof_frame, K_CONV

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Shrinkage mass: fraction of the finishing residual subtracted from (or added to)
# the raw team Poisson lambda.
# Rationale: 0.25 = conservative 25% regression toward SoT expectation.
# Never auto-tuned; documented here as a pinned design constant.
SHRINK_MASS: float = 0.25

# Minimum prior matches before applying the shrinkage (avoid noisy early estimates).
MIN_PRIOR_MATCHES: int = 3

# Maximum absolute lambda adjustment (safety clip).
MAX_LAMBDA_ADJUST: float = 0.30


# ---------------------------------------------------------------------------
# Core adjust function
# ---------------------------------------------------------------------------

def _adjust_lambda(
    lam: float,
    finishing_residual: float,
    n_prior: int,
    *,
    shrink_mass: float = SHRINK_MASS,
    min_prior: int = MIN_PRIOR_MATCHES,
    max_adjust: float = MAX_LAMBDA_ADJUST,
) -> float:
    """Return finishing-regressed lambda (unchanged if n_prior < min_prior or residual NaN)."""
    if n_prior < min_prior or not np.isfinite(finishing_residual):
        return lam
    adjust = shrink_mass * finishing_residual
    # Safety clip on the adjustment itself
    adjust = max(-max_adjust, min(max_adjust, adjust))
    lo, hi = RATE_CLIP
    return float(min(max(lam - adjust, lo), hi))


# ---------------------------------------------------------------------------
# Walk-forward with finishing prior
# ---------------------------------------------------------------------------

def walk_forward_finishing_prior(
    matches_df: pd.DataFrame,
    match_stats_df: pd.DataFrame,
    *,
    rho: float = 0.0,
    shrink_mass: float = SHRINK_MASS,
    min_prior: int = MIN_PRIOR_MATCHES,
) -> pd.DataFrame:
    """Walk-forward: baseline lambdas + finishing shrinkage; returns augmented DataFrame."""
    # Baseline lambdas (strictly pre-match)
    wf = walk_forward_goals(matches_df)
    # As-of finishing residuals (strictly pre-match)
    asof = build_asof_frame(match_stats_df, matches_df[["event_id", "fthg", "ftag"]])
    wf = wf.merge(
        asof[["event_id", "home_finishing_residual", "away_finishing_residual",
              "home_n_prior", "away_n_prior"]],
        on="event_id",
        how="left",
    )

    # Step 3: compute adjusted lambdas + market probabilities row-by-row.
    lam_home_adj_list: List[float] = []
    lam_away_adj_list: List[float] = []
    p_over_base_list: List[float] = []
    p_over_adj_list: List[float] = []
    home_base_list: List[float] = []
    draw_base_list: List[float] = []
    away_base_list: List[float] = []
    home_adj_list: List[float] = []
    draw_adj_list: List[float] = []
    away_adj_list: List[float] = []

    lam_h_arr = wf["lam_home"].values.astype(float)
    lam_a_arr = wf["lam_away"].values.astype(float)
    h_res_arr = wf["home_finishing_residual"].values.astype(float)
    a_res_arr = wf["away_finishing_residual"].values.astype(float)
    h_n_arr = wf["home_n_prior"].fillna(0).values.astype(int)
    a_n_arr = wf["away_n_prior"].fillna(0).values.astype(int)

    for i in range(len(wf)):
        lh = lam_h_arr[i]
        la = lam_a_arr[i]
        h_res = h_res_arr[i]
        a_res = a_res_arr[i]
        h_n = h_n_arr[i]
        a_n = a_n_arr[i]

        # Baseline O/U
        p_base = _p_over(lh + la)
        p_over_base_list.append(p_base)

        # Baseline 1X2 via scoreline matrix
        P_base = scoreline_matrix(lh, la, rho=rho)
        m_base = markets_from_matrix(P_base, top_n=0)
        home_base_list.append(m_base["1X2_home"])
        draw_base_list.append(m_base["1X2_draw"])
        away_base_list.append(m_base["1X2_away"])

        # Adjusted lambdas
        lh_adj = _adjust_lambda(lh, h_res, h_n,
                                 shrink_mass=shrink_mass, min_prior=min_prior)
        la_adj = _adjust_lambda(la, a_res, a_n,
                                 shrink_mass=shrink_mass, min_prior=min_prior)
        lam_home_adj_list.append(lh_adj)
        lam_away_adj_list.append(la_adj)

        # Adjusted O/U
        p_adj = _p_over(lh_adj + la_adj)
        p_over_adj_list.append(p_adj)

        # Adjusted 1X2
        P_adj = scoreline_matrix(lh_adj, la_adj, rho=rho)
        m_adj = markets_from_matrix(P_adj, top_n=0)
        home_adj_list.append(m_adj["1X2_home"])
        draw_adj_list.append(m_adj["1X2_draw"])
        away_adj_list.append(m_adj["1X2_away"])

    wf = wf.copy()
    wf["lam_home_adj"] = lam_home_adj_list
    wf["lam_away_adj"] = lam_away_adj_list
    wf["p_over25_base"] = p_over_base_list
    wf["p_over25_adj"] = p_over_adj_list
    wf["1x2_home_base"] = home_base_list
    wf["1x2_draw_base"] = draw_base_list
    wf["1x2_away_base"] = away_base_list
    wf["1x2_home_adj"] = home_adj_list
    wf["1x2_draw_adj"] = draw_adj_list
    wf["1x2_away_adj"] = away_adj_list
    return wf


# ---------------------------------------------------------------------------
# Validation harness
# ---------------------------------------------------------------------------

def score_finishing_prior(
    matches_df: Optional[pd.DataFrame] = None,
    match_stats_df: Optional[pd.DataFrame] = None,
    *,
    rho: float = 0.0,
) -> Dict:
    """Score baseline vs finishing-adjusted predictions; returns metrics dict."""
    from scripts.platformkit.scoreboard import score_forecaster

    if matches_df is None:
        matches_df = pd.read_parquet(
            _REPO_ROOT / DATA_DIR_REL / "matches.parquet"
        )
    if match_stats_df is None:
        match_stats_df = pd.read_parquet(
            _REPO_ROOT / DATA_DIR_REL / "match_stats.parquet"
        )

    wf = walk_forward_finishing_prior(matches_df, match_stats_df, rho=rho)

    # Derive target_over25 if not present (total goals >= 3)
    if "target_over25" not in wf.columns:
        if "fthg" in wf.columns and "ftag" in wf.columns:
            wf = wf.copy()
            wf["target_over25"] = ((wf["fthg"] + wf["ftag"]) >= 3).astype(float)
        else:
            wf = wf.copy()
            wf["target_over25"] = float("nan")

    # Filter to rows with valid targets
    valid = wf[wf["target_over25"].notna()].copy()
    targets_ou25 = valid["target_over25"].astype(float).tolist()

    # 1X2: target is 1 if home win, 0 otherwise (draws/away = 0)
    if "ftr" in valid.columns:
        targets_1x2 = (valid["ftr"] == "H").astype(float).tolist()
    else:
        targets_1x2 = None

    ou_base_s = score_forecaster(
        valid["p_over25_base"].tolist(), targets_ou25
    )
    ou_adj_s = score_forecaster(
        valid["p_over25_adj"].tolist(), targets_ou25
    )

    d_brier_ou = ou_adj_s["brier"] - ou_base_s["brier"]

    def _verdict(d: float, tol: float = 0.0003) -> str:
        if d < -tol:
            return "IMPROVES"
        if d > tol:
            return "HARMS"
        return "NULL/REDISTRIBUTES"

    result: Dict = {
        "n": ou_base_s["n"],
        "shrink_mass": SHRINK_MASS,
        "min_prior_matches": MIN_PRIOR_MATCHES,
        "k_conv": K_CONV,
        "ou25_baseline":  {k: ou_base_s[k] for k in ("brier", "ece", "log_loss")},
        "ou25_finishing": {k: ou_adj_s[k]  for k in ("brier", "ece", "log_loss")},
        "d_brier_ou25": d_brier_ou,
        "d_ece_ou25": ou_adj_s["ece"] - ou_base_s["ece"],
        "ou25_verdict": _verdict(d_brier_ou),
    }

    if targets_1x2 is not None:
        x2_base_s = score_forecaster(valid["1x2_home_base"].tolist(), targets_1x2)
        x2_adj_s  = score_forecaster(valid["1x2_home_adj"].tolist(),  targets_1x2)
        d_brier_1x2 = x2_adj_s["brier"] - x2_base_s["brier"]
        result["1x2_baseline"]  = {k: x2_base_s[k] for k in ("brier", "ece", "log_loss")}
        result["1x2_finishing"] = {k: x2_adj_s[k]  for k in ("brier", "ece", "log_loss")}
        result["d_brier_1x2"]   = d_brier_1x2
        result["d_ece_1x2"]     = x2_adj_s["ece"] - x2_base_s["ece"]
        result["1x2_verdict"]   = _verdict(d_brier_1x2)

    verdicts = [result["ou25_verdict"]]
    if "1x2_verdict" in result:
        verdicts.append(result["1x2_verdict"])

    n_improves = sum(1 for v in verdicts if v == "IMPROVES")
    if n_improves == len(verdicts):
        overall = "IMPROVES (both markets)"
    elif n_improves > 0:
        overall = f"MIXED ({n_improves}/{len(verdicts)} improve)"
    else:
        overall = "NULL/REDISTRIBUTES — honest null OK; gate rejects for edge"

    result["overall_verdict"] = overall
    result["note"] = (
        "HONEST: accuracy/calibration only.  Null redistribution is the expected "
        "outcome (mirrors HFA/rho waves).  NO edge claimed; gate decides signal "
        "merit.  SHRINK_MASS=0.25 pinned, never auto-tuned (artifact risk)."
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    import json
    result = score_finishing_prior()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
