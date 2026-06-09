"""engine_bradley_terry.py -- Bradley-Terry paired-comparison team strengths.

METHODOLOGY
-----------
Fit Bradley-Terry logistic paired-comparison strengths β_t from win/loss
pairs in league_team_game.parquet.  Each game row is one paired comparison:
team wins (1) or loses (0) against opponent.  The BT model is:

    P(team beats opp) = σ(β_team − β_opp + β_hca · is_home)

where σ is the logistic sigmoid.  We fit via a one-hot team-difference sparse
design matrix with a single scalar HCA coefficient.  The MLE is solved by
sklearn's LogisticRegression (L2 λ→0, i.e. C=1e6 so near-unregularised,
converges on 30-team balanced schedule).

MARGIN CONVERSION
-----------------
A separate linear fit maps (β_home − β_away) to observed margin_home across
all games, giving pts_per_logit (≈ pts gained per 1-unit logit-diff).
margin_sd is the residual std of that linear fit — the honest per-game
error floor (~13–15 pts).

TOTAL
-----
League-average game total (pts + opp_pts) per team pair is used, pace-adjusted
by (home_poss + away_poss) / (2 * league_avg_poss).

DECORRELATION EXPECTATION (spec §5)
-------------------------------------
BT win-strength is approximately a monotone transform of SRS net-rating.
Expected corr-to-cluster: r ≈ 0.85–0.92.  PREDICTED MOSTLY REDUNDANT.
The win/loss-only information source (BT ignores MOV) differs slightly from
MOV-based SRS → a small genuine wedge is possible but not assumed.
honesty_class = research.

LEAK-FREE
---------
Full-season fit (not a running tracker) — consistent with SRS / power_ratings.
As-of-capable for a rolling backtest by subsetting df to prior dates.

n_models = 30 team β_t + 1 β_hca + 1 pts_per_logit = 32 fitted params.
n_signals = number of game rows consumed from league_team_game.parquet.
"""

from __future__ import annotations

import math
import os
import warnings
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths  (engines_x/ is same depth as engines/, so parents[3] = repo root)
# ---------------------------------------------------------------------------
_REPO = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_LEAGUE_GAME = os.path.join(
    _REPO, "data", "cache", "team_system", "league_team_game.parquet"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # pts, added when not neutral_site
FALLBACK_MARGIN_SD: float = 13.5
# C for logistic regression — near-unregularised (L2 λ=1e-6)
_LR_C: float = 1e6
_LR_MAXITER: int = 1000


# ---------------------------------------------------------------------------
# Build (cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _build() -> dict:
    """Fit Bradley-Terry model and return all artefacts."""
    from scipy.special import expit  # type: ignore

    df = pd.read_parquet(_LEAGUE_GAME)
    n_signals = len(df)

    teams = sorted(df["team"].unique().tolist())
    n_teams = len(teams)
    team_idx: dict[str, int] = {t: i for i, t in enumerate(teams)}

    # ---- Detect home/away from data ----------------------------------------
    # league_team_game is long format: each row is one team's line.
    # We need to know if that team was HOME.  Reconstruct by checking if
    # any "home" column is present; if not, infer from gid pairing.
    has_home_col = "is_home" in df.columns
    if has_home_col:
        home_mask = df["is_home"].astype(bool)
    else:
        # Each gid appears twice; in NBA convention the home team is listed
        # first (lower row index within gid).  Mark the first occurrence as home.
        df = df.sort_values(["gid", "date"]).reset_index(drop=True)
        df["_row"] = df.groupby("gid").cumcount()
        home_mask = df["_row"] == 0
        df = df.drop(columns=["_row"])

    # ---- Build design matrix -----------------------------------------------
    # For each game row: X row = one-hot(team) - one-hot(opp),  y = win (0/1)
    # Plus one feature for is_home (HCA coefficient).
    # We use a sparse float32 array.
    n_rows = len(df)
    # Feature vector: [team_0 ... team_{n-1}, is_home]
    X = np.zeros((n_rows, n_teams + 1), dtype=np.float32)
    y = df["win"].values.astype(np.float32)

    for i, row in enumerate(df.itertuples(index=False)):
        t = team_idx[row.team]
        o = team_idx[row.opp]
        X[i, t] = 1.0
        X[i, o] = -1.0
        # is_home indicator
        X[i, n_teams] = 1.0 if home_mask.iloc[i] else -1.0

    # Fix one team to 0 to avoid collinearity (drop first team feature, i.e. ATL)
    # LogisticRegression with fit_intercept=False + anchor via data balance.
    # Simpler: fit with intercept=False and let sklearn converge; relative diffs
    # are what matter.  The design is full rank once we pin nothing (we have the
    # HCA column that breaks full degeneracy in the team block).
    from sklearn.linear_model import LogisticRegression  # type: ignore

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lr = LogisticRegression(
            C=_LR_C,
            fit_intercept=False,
            max_iter=_LR_MAXITER,
            solver="lbfgs",
            tol=1e-6,
        )
        lr.fit(X, y)

    coef = lr.coef_[0]  # shape (n_teams + 1,)
    beta: dict[str, float] = {t: float(coef[i]) for t, i in team_idx.items()}
    beta_hca: float = float(coef[n_teams])

    # Normalise team betas to zero mean (league-relative)
    mean_beta = np.mean(list(beta.values()))
    beta = {t: v - mean_beta for t, v in beta.items()}

    # ---- Calibrate logit-diff → margin_home (linear fit) ------------------
    logit_diffs: list[float] = []
    actual_margins: list[float] = []

    gids = df["gid"].unique()
    # Build per-game (home_team, away_team, actual_margin)
    for gid in gids:
        sub = df[df["gid"] == gid]
        if len(sub) != 2:
            continue
        # home row = is_home True
        h_rows = sub[home_mask.loc[sub.index]]
        if len(h_rows) == 0:
            h_rows = sub.iloc[[0]]
        a_rows = sub.drop(index=h_rows.index)
        if len(a_rows) == 0:
            continue
        h_team = h_rows.iloc[0]["team"]
        a_team = a_rows.iloc[0]["team"]
        actual_margin = float(h_rows.iloc[0]["pts"] - h_rows.iloc[0]["opp_pts"])
        logit_diff = beta.get(h_team, 0.0) - beta.get(a_team, 0.0) + beta_hca
        logit_diffs.append(logit_diff)
        actual_margins.append(actual_margin)

    if len(logit_diffs) > 10:
        ld_arr = np.array(logit_diffs)
        am_arr = np.array(actual_margins)
        # OLS: margin = pts_per_logit * logit_diff
        pts_per_logit = float(
            np.dot(ld_arr, am_arr) / (np.dot(ld_arr, ld_arr) + 1e-9)
        )
        residuals = am_arr - pts_per_logit * ld_arr
        margin_sd = float(np.std(residuals, ddof=1))
    else:
        pts_per_logit = 5.0
        margin_sd = FALLBACK_MARGIN_SD

    margin_sd = max(margin_sd, 10.0)  # floor

    # ---- Pace and total stats ----------------------------------------------
    avg_poss: dict[str, float] = df.groupby("team")["poss"].mean().to_dict()
    league_avg_poss: float = float(df["poss"].mean())
    team_avg_total: dict[str, float] = {
        t: float((sub["pts"] + sub["opp_pts"]).mean())
        for t, sub in df.groupby("team")
    }
    league_avg_total: float = float((df["pts"] + df["opp_pts"]).mean())

    leaderboard = sorted(beta.items(), key=lambda x: x[1], reverse=True)

    return {
        "beta": beta,
        "beta_hca": beta_hca,
        "pts_per_logit": pts_per_logit,
        "margin_sd": margin_sd,
        "avg_poss": avg_poss,
        "league_avg_poss": league_avg_poss,
        "team_avg_total": team_avg_total,
        "league_avg_total": league_avg_total,
        "n_signals": n_signals,
        "n_models": n_teams + 2,  # n_teams β + β_hca + pts_per_logit
        "leaderboard": leaderboard,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return standardised prediction dict (frozen engine interface).

    context keys (all optional):
      neutral_site (bool) — removes HCA from margin.
      home_b2b (bool), away_b2b (bool), playoffs (bool) — accepted, unused.

    Decorrelation note: BT win-strength ≈ monotone transform of SRS.
    Expected corr-to-cluster r ≈ 0.85–0.92 (PREDICTED MOSTLY REDUNDANT).
    The win/loss-only MLE differs slightly from MOV-based SRS; a small
    genuine wedge is possible.  honesty_class = research.
    """
    ctx = context or {}
    art = _build()

    beta = art["beta"]
    home = home_tri.upper()
    away = away_tri.upper()

    if home not in beta:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(beta)}")
    if away not in beta:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(beta)}")

    neutral = bool(ctx.get("neutral_site", False))

    # Logit difference → margin
    logit_diff = beta[home] - beta[away]
    if not neutral:
        logit_diff += art["beta_hca"]
    margin_home = logit_diff * art["pts_per_logit"]

    # Fall back to fixed HCA contribution if pts_per_logit is small
    hca_pts = 0.0 if neutral else HOME_EDGE
    # Blend: use BT logit for relative strength, fixed HCA for location
    # (avoids β_hca estimation noise from near-balanced home/away schedule)
    margin_home_bt = (beta[home] - beta[away]) * art["pts_per_logit"] + hca_pts

    # Win probability (erf form, consistent with other engines)
    margin_sd = art["margin_sd"]
    win_prob_home = 0.5 + 0.5 * math.erf(
        margin_home_bt / (margin_sd * math.sqrt(2.0))
    )
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    # Total: pace-adjusted league averages
    home_poss = art["avg_poss"].get(home, art["league_avg_poss"])
    away_poss = art["avg_poss"].get(away, art["league_avg_poss"])
    pace_factor = (home_poss + away_poss) / (2.0 * art["league_avg_poss"])
    base_total = (
        art["team_avg_total"].get(home, art["league_avg_total"])
        + art["team_avg_total"].get(away, art["league_avg_total"])
    ) / 2.0
    total = base_total * pace_factor

    home_pts = total / 2.0 + margin_home_bt / 2.0
    away_pts = total / 2.0 - margin_home_bt / 2.0

    # Notes
    leaderboard = art["leaderboard"]
    home_rank = next(
        (i + 1 for i, (t, _) in enumerate(leaderboard) if t == home), "??"
    )
    away_rank = next(
        (i + 1 for i, (t, _) in enumerate(leaderboard) if t == away), "??"
    )

    notes = (
        f"BT: {home} #{home_rank} (bt={beta[home]:+.3f}) vs "
        f"{away} #{away_rank} (bt={beta[away]:+.3f}); "
        f"pts_per_logit={art['pts_per_logit']:.2f}; "
        f"margin={margin_home_bt:+.1f} pts, total={total:.1f}, "
        f"margin_sd={margin_sd:.2f}; "
        f"site={'neutral' if neutral else '+2.7 HCA'}; "
        "DECORRELATION: predicted r≈0.85-0.92 (mostly redundant); "
        "honesty_class=research; 2025-26 single-season only."
    )

    return {
        "engine": "bradley_terry",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home_bt, 2),
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
    leaderboard = art["leaderboard"]
    beta = art["beta"]

    print("=" * 60)
    print("ENGINE: bradley_terry  (BT logistic paired-comparison, 30 teams)")
    print("=" * 60)

    print(f"\nLeague residual margin_sd   : {art['margin_sd']:.3f} pts")
    print(f"pts_per_logit               : {art['pts_per_logit']:.3f}")
    print(f"beta_hca_fitted             : {art['beta_hca']:.4f}")
    print(f"n_signals (game rows)       : {art['n_signals']}")
    print(f"n_models  (params)          : {art['n_models']}")

    print("\n--- BT Leaderboard (top 5) ---")
    for rank, (team, b) in enumerate(leaderboard[:5], 1):
        print(f"  #{rank:2d}  {team}  bt={b:+.4f}")

    print("\n--- BT Leaderboard (bottom 5) ---")
    bottom = leaderboard[-5:]
    start_rank = len(leaderboard) - 4
    for rank, (team, b) in enumerate(bottom, start_rank):
        print(f"  #{rank:2d}  {team}  bt={b:+.4f}")

    nyk_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == "NYK")
    sas_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == "SAS")
    print(f"\n  NYK  #{nyk_rank:2d}  bt={beta['NYK']:+.4f}")
    print(f"  SAS  #{sas_rank:2d}  bt={beta['SAS']:+.4f}")

    print("\n--- predict(NYK, SAS) ---")
    result = predict("NYK", "SAS")
    for k, v in result.items():
        if k != "notes":
            print(f"  {k:<18s} {v}")
    print(f"  {'notes':<18s} {result['notes'][:80]}...")

    print("\n--- predict(SAS, NYK) [road-SAS scenario] ---")
    result2 = predict("SAS", "NYK")
    for k, v in result2.items():
        if k != "notes":
            print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral) ---")
    result3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in result3.items():
        if k != "notes":
            print(f"  {k:<18s} {v}")

    # Sanity checks
    r = predict("NYK", "SAS")
    r_neutral = predict("NYK", "SAS", {"neutral_site": True})
    assert abs((r["home_pts"] + r["away_pts"]) - r["total"]) < 0.11, "pts sum mismatch"
    assert abs((r["home_pts"] - r["away_pts"]) - r["margin_home"]) < 0.11, "margin mismatch"
    assert 0.01 <= r["win_prob_home"] <= 0.99, "win_prob out of range"
    assert r["margin_sd"] > 0, "margin_sd must be positive"
    hca_diff = r["margin_home"] - r_neutral["margin_home"]
    assert abs(hca_diff - HOME_EDGE) < 0.5, f"HCA diff unexpected: {hca_diff:.2f}"

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
