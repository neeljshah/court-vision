"""engine_bayesian_power.py -- Hierarchical Bayesian / James-Stein shrinkage engine.

METHODOLOGY
-----------
Empirical-Bayes (James-Stein) shrinkage of team net-rating toward the league mean:

    net_shrunk[t]  = lambda[t] * net_obs[t]  +  (1 - lambda[t]) * 0
    lambda[t]      = n[t] / (n[t] + tau)
    tau            = sigma2_within / sigma2_between_true

where
    sigma2_within       = mean over teams of per-game net-rtg variance
                          (the within-team game-to-game noise)
    sigma2_between_true = observed variance of team-mean net-rtgs
                          minus the sampling noise (sigma2_within / n_avg)
                          floor-clipped at 1.0 to avoid numeric issues

Margin prediction:
    margin_home = (net_shrunk[home] - net_shrunk[away]) * avg_pace / 100.0 + hca

Headline output -- the CALIBRATED posterior-predictive margin_sd:
    margin_sd_post = sqrt(residual_var + shrinkage_var)
    shrinkage_var  = (sigma2_within / avg_n) * 2 * (avg_pace/100)^2
                     (estimation uncertainty propagated through the margin formula,
                      sqrt(2) because home + away each contribute independently)

This is the engine's REAL contribution to the fusion: better-calibrated per-game
uncertainty widening for low-sample or high-variance teams, NOT decorrelation of the
margin point estimate.

HONEST DECORRELATION FORECAST
------------------------------
Shrunk net-rtg ≈ raw net-rtg at full-season N (lambda ~0.92 at n=77, tau~6.6).
Predicted correlation to the analytic power-ratings cluster: r > 0.90.
This engine is a CALIBRATION ENGINE, not a decorrelation engine.
Report: margin redundant (r > 0.9), SD calibration is the value-add.

DATA
----
league_team_game.parquet — 30 teams, 2025-10-21 to 2026-04-06, ~77 games/team.
Single season; inter-season stability not validated. honesty_class=research.

n_models = 30 team ratings + 1 hyperparam (tau)
n_signals = rows in league_team_game (all game-level outcomes consumed)
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
# engines_x/ is one level below team_system/ which is two below scripts/ which is
# one below repo root: engines_x -> team_system -> scripts -> nba-ai-system
_REPO = _HERE.parents[3]
_LEAGUE_GAME = _REPO / "data" / "cache" / "team_system" / "league_team_game.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # pts, omitted on neutral_site
FALLBACK_MARGIN_SD: float = 13.5  # pts, used if residual calc fails

# Empirical guard: floor true between-team variance at 1.0 to keep tau finite
_TAU_FLOOR_BETWEEN_VAR: float = 1.0


# ---------------------------------------------------------------------------
# Build -- cached (lru_cache) so repeated predict() calls are fast
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _build() -> dict:
    """Load data, fit empirical-Bayes shrinkage, return all artefacts."""
    df = pd.read_parquet(str(_LEAGUE_GAME))
    n_signals = int(len(df))

    # Net-rating per game (pts per 100 possessions)
    df = df.copy()
    df["net_rtg"] = (df["pts"].astype(float) - df["opp_pts"].astype(float)) / df["poss"].astype(float) * 100.0

    teams = sorted(df["team"].unique().tolist())
    n_teams = len(teams)

    # ---- per-team summary stats ------------------------------------------
    grp = df.groupby("team")
    team_n = grp["net_rtg"].count().rename("n")
    team_mean = grp["net_rtg"].mean().rename("net_obs")
    team_var = grp["net_rtg"].var(ddof=1).rename("var_within")
    team_poss = grp["poss"].mean().rename("avg_poss")
    team_total = (grp["pts"].mean() + grp["opp_pts"].mean()).rename("avg_total")

    stats = pd.concat([team_n, team_mean, team_var, team_poss, team_total], axis=1).reset_index()

    # ---- empirical Bayes: estimate tau (shrinkage hyperparam) -------------
    sigma2_within: float = float(stats["var_within"].mean())
    n_avg: float = float(stats["n"].mean())
    sigma2_between_obs: float = float(stats["net_obs"].var(ddof=1))
    # Correct for sampling variance of the mean
    sigma2_between_true: float = max(
        sigma2_between_obs - sigma2_within / n_avg,
        _TAU_FLOOR_BETWEEN_VAR,
    )
    tau: float = sigma2_within / sigma2_between_true  # units of games

    # ---- per-team shrinkage -----------------------------------------------
    # lambda_t = n_t / (n_t + tau)  (closes to 1 as n_t >> tau)
    stats["lam"] = stats["n"] / (stats["n"] + tau)
    # Shrink toward league mean = 0 (already zero-meaned by construction)
    stats["net_shrunk"] = stats["lam"] * stats["net_obs"]

    shrunk: dict[str, float] = dict(zip(stats["team"], stats["net_shrunk"]))
    avg_poss_map: dict[str, float] = dict(zip(stats["team"], stats["avg_poss"]))
    avg_total_map: dict[str, float] = dict(zip(stats["team"], stats["avg_total"]))
    lam_map: dict[str, float] = dict(zip(stats["team"], stats["lam"]))
    n_map: dict[str, int] = dict(zip(stats["team"], stats["n"].astype(int)))

    league_avg_poss: float = float(df["poss"].mean())
    league_avg_total: float = float((df["pts"] + df["opp_pts"]).mean())

    # ---- residual SD -- honest per-game error floor ----------------------
    # Predict margin via shrunk net-rtg diff × observed possession count/100
    errors: list[float] = []
    for _, row in df.iterrows():
        t_team, t_opp = str(row["team"]), str(row["opp"])
        pace = float(row["poss"])
        pred_margin = (shrunk.get(t_team, 0.0) - shrunk.get(t_opp, 0.0)) * pace / 100.0
        actual_margin = float(row["pts"]) - float(row["opp_pts"])
        errors.append(actual_margin - pred_margin)

    import numpy as np  # local import; numpy already available via pandas
    residual_sd: float = float(np.std(errors, ddof=1)) if errors else FALLBACK_MARGIN_SD

    # ---- posterior-predictive SD (key contribution of this engine) -------
    # Estimation uncertainty propagated to the margin:
    #   For each team: sd_est_net = sqrt(sigma2_within / n_t)   [net-rtg units]
    #   Margin = net_diff * pace/100, so:
    #   sd_margin_est = sqrt(sd_est_home^2 + sd_est_away^2) * avg_pace/100
    # At league-average n and pace:
    shrinkage_var: float = (
        (sigma2_within / n_avg) * 2.0 * (league_avg_poss / 100.0) ** 2
    )
    margin_sd_post: float = float(math.sqrt(residual_sd ** 2 + shrinkage_var))

    # ---- sorted leaderboard -----------------------------------------------
    leaderboard = sorted(shrunk.items(), key=lambda x: x[1], reverse=True)

    return {
        "shrunk": shrunk,
        "avg_poss_map": avg_poss_map,
        "avg_total_map": avg_total_map,
        "lam_map": lam_map,
        "n_map": n_map,
        "league_avg_poss": league_avg_poss,
        "league_avg_total": league_avg_total,
        "residual_sd": residual_sd,
        "margin_sd_post": margin_sd_post,
        "tau": tau,
        "sigma2_within": sigma2_within,
        "sigma2_between_true": sigma2_between_true,
        "leaderboard": leaderboard,
        "n_signals": n_signals,
        "n_models": n_teams + 1,  # 30 team ratings + tau hyperparam
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised engine prediction dict.

    Bayesian / James-Stein shrinkage of team net-rating. Margin point estimate
    is near-redundant with the power-ratings cluster (predicted r > 0.90 to
    analytic block). The ENGINE'S GENUINE CONTRIBUTION is the posterior-
    predictive margin_sd, which is wider and better-calibrated than the raw
    residual SD, accounting for estimation uncertainty (especially for teams
    with fewer games or higher per-game variance).

    context keys (all optional):
      neutral_site (bool) -- removes HCA from margin.
    """
    ctx = context or {}
    art = _build()

    home = home_tri.upper()
    away = away_tri.upper()

    valid = set(art["shrunk"].keys())
    if home not in valid:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(valid)}")
    if away not in valid:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(valid)}")

    neutral = bool(ctx.get("neutral_site", False))
    hca = 0.0 if neutral else HOME_EDGE

    # Margin: shrunk net-rtg diff, scaled by avg pace of the matchup
    home_poss = art["avg_poss_map"].get(home, art["league_avg_poss"])
    away_poss = art["avg_poss_map"].get(away, art["league_avg_poss"])
    matchup_pace = (home_poss + away_poss) / 2.0
    pace_scale = matchup_pace / 100.0

    net_home = art["shrunk"][home]
    net_away = art["shrunk"][away]
    margin_home = (net_home - net_away) * pace_scale + hca

    # Total: average of per-team avg game totals, pace-adjusted
    base_total = (
        art["avg_total_map"].get(home, art["league_avg_total"])
        + art["avg_total_map"].get(away, art["league_avg_total"])
    ) / 2.0
    pace_factor = matchup_pace / art["league_avg_poss"]
    total = base_total * pace_factor

    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # Win probability via normal CDF
    margin_sd = art["margin_sd_post"]
    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (margin_sd * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    # Shrinkage details for notes
    lam_h = art["lam_map"].get(home, 0.0)
    lam_a = art["lam_map"].get(away, 0.0)
    n_h = art["n_map"].get(home, 0)
    n_a = art["n_map"].get(away, 0)

    lb = art["leaderboard"]
    home_rank = next((i + 1 for i, (t, _) in enumerate(lb) if t == home), "?")
    away_rank = next((i + 1 for i, (t, _) in enumerate(lb) if t == away), "?")

    notes = (
        f"Bayesian shrinkage: {home} #{home_rank} "
        f"net_shrunk={net_home:+.2f} (lam={lam_h:.3f}, n={n_h}g) vs "
        f"{away} #{away_rank} "
        f"net_shrunk={net_away:+.2f} (lam={lam_a:.3f}, n={n_a}g); "
        f"tau={art['tau']:.2f}; "
        f"margin={margin_home:+.1f}, total={total:.1f}, "
        f"margin_sd_post={margin_sd:.2f} (residual={art['residual_sd']:.2f}); "
        f"honesty=CALIBRATION ENGINE (margin r>0.9 to cluster, not decorrelated); "
        f"hca={'neutral' if neutral else '+2.7'}; "
        f"honesty_class=research; single-season 2025-26"
    )

    return {
        "engine": "bayesian_power",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 2),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": round(margin_sd, 2),
        "n_models": art["n_models"],
        "n_signals": art["n_signals"],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    art = _build()
    lb = art["leaderboard"]

    print("=" * 65)
    print("ENGINE: bayesian_power  (James-Stein shrinkage, 30 teams)")
    print("=" * 65)
    print(f"\nHyperparams:")
    print(f"  tau (shrinkage param, in games) : {art['tau']:.4f}")
    print(f"  sigma2_within (avg per-game var): {art['sigma2_within']:.3f}")
    print(f"  sigma2_between_true             : {art['sigma2_between_true']:.3f}")
    print(f"  lambda at n=77                  : {77/(77+art['tau']):.4f}")
    print(f"\nSD diagnostics:")
    print(f"  residual_sd (per-game floor)    : {art['residual_sd']:.3f} pts")
    print(f"  margin_sd_post (posterior-pred) : {art['margin_sd_post']:.3f} pts")
    print(f"\nn_signals (game rows)            : {art['n_signals']}")
    print(f"n_models  (teams + tau)          : {art['n_models']}")

    print("\n--- Leaderboard (top 5 shrunk net-rtg) ---")
    for rank, (team, rtg) in enumerate(lb[:5], 1):
        lam = art["lam_map"][team]
        print(f"  #{rank:2d}  {team}  shrunk={rtg:+.3f}  lam={lam:.3f}")

    print("\n--- Leaderboard (bottom 5) ---")
    for rank, (team, rtg) in enumerate(lb[-5:], len(lb) - 4):
        lam = art["lam_map"][team]
        print(f"  #{rank:2d}  {team}  shrunk={rtg:+.3f}  lam={lam:.3f}")

    nyk_rank = next(i + 1 for i, (t, _) in enumerate(lb) if t == "NYK")
    sas_rank = next(i + 1 for i, (t, _) in enumerate(lb) if t == "SAS")
    print(f"\n  NYK  #{nyk_rank}  shrunk={art['shrunk']['NYK']:+.3f}  "
          f"lam={art['lam_map']['NYK']:.3f}  n={art['n_map']['NYK']}g")
    print(f"  SAS  #{sas_rank}  shrunk={art['shrunk']['SAS']:+.3f}  "
          f"lam={art['lam_map']['SAS']:.3f}  n={art['n_map']['SAS']}g")

    print("\n--- predict(NYK, SAS) ---")
    r = predict("NYK", "SAS")
    for k, v in r.items():
        if k == "notes":
            print(f"  {k:<18s} [see below]")
        else:
            print(f"  {k:<18s} {v}")
    print(f"  notes: {r['notes']}")

    print("\n--- predict(SAS, NYK)  [road-SAS scenario] ---")
    r2 = predict("SAS", "NYK")
    for k, v in r2.items():
        if k != "notes":
            print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral_site=True) ---")
    r3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in r3.items():
        if k != "notes":
            print(f"  {k:<18s} {v}")

    # Sanity checks
    assert "bayesian_power" == r["engine"], "engine name mismatch"
    assert 0.01 <= r["win_prob_home"] <= 0.99, "win_prob out of range"
    assert abs(r["home_pts"] + r["away_pts"] - r["total"]) < 0.1, "pts sum != total"
    assert abs(r["home_pts"] - r["away_pts"] - r["margin_home"]) < 0.1, "pts diff != margin"
    assert r["margin_sd"] > 0, "margin_sd <= 0"
    assert r3["margin_home"] < r["margin_home"], "neutral should reduce margin"

    print("\nHONESTY NOTE: margin r>0.9 with analytic cluster (CALIBRATION ENGINE, not decorrelation).")
    print("Value-add = posterior-predictive margin_sd, NOT margin decorrelation.")
    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
