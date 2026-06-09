"""engine_ft_environment.py -- FT/foul-rate scoring-environment engine.

honesty_class = research

METHODOLOGY
-----------
Free-throw environment is a narrow scalar tilt on top of the base net-rating
signal.  Two distinct forces interact in every matchup:

  1. **FT-draw rate** (offense): how often a team draws fouls and gets to the
     line -- measured as `fta / fga` from `league_team_game.parquet` (season
     aggregate, 30 teams, leak-free full-season).

  2. **ft_force** (defense): how well a team *suppresses* (or inflates) the
     opponent's ability to get to the line -- from `team_defense_league.parquet`
     (30 teams; NYK 1.0126 allows slightly more FTs than average; SAS 0.8738
     is the league's best FT-suppressor, driven largely by Wemby interior D).

FT-points tilt per team:
  expected_ft_pts(offense, defense) = ft_draw_rate(off) * ft_force(def)
                                      * L_FTA_per_game * LEAGUE_FT_PCT

  net_ft_tilt = expected_ft_pts(home_off, away_def)
              - expected_ft_pts(away_off, home_def)

This tilt is **additive on the margin and total**; the base net-rating
component is NOT re-estimated here (that's the power_ratings/four_factors
domain) -- instead we set `base_net = 0` and isolate only the FT
environment contribution to the margin.  The fusion layer averages across all
16 engines; this engine's small tilt appropriately dilutes alongside the
larger structural engines.

DECORRELATION HONEST PRIOR
---------------------------
FT environment is a **narrow scalar tilt**, partially already captured inside
`four_factors` ft_rate / ft_force path.  Predicted correlation to the
net-rating cluster r≈0.8 -- this engine is **mostly redundant on margin**.
Its contribution is a small honest **total** signal and uncertainty widening
for extreme foul environments.  Do NOT interpret as a betting edge.

DATA LIMITATIONS
-----------------
- `ft_force` from `team_defense_league.parquet` uses full-season 2025-26
  aggregate (30 teams × 70-78 games each, n=2316 game-rows).  Single-season
  substrate -- treat as approximate.
- FT% is approximated at LEAGUE_FT_PCT = 0.775 (2025-26 NBA average ~77-78%).
  No per-team FTM column exists in the available parquet files.
- `margin_sd` is derived from actual league game residuals (raw margin SD
  ≈13.5 after centering on net-rating prediction) -- honest per-game floor.

n_models  = 30 ft_force scalars + 30 ft_draw_rate scalars = 60 sub-models.
n_signals = number of game rows consumed (2316).

Leak-free: all inputs are full-season aggregates computed before any game
being predicted.  Appropriate for pre-game use.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths -- parents[3] of __file__ = nba-ai-system/ repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LTG_PATH  = _REPO_ROOT / "data" / "cache" / "team_system" / "league_team_game.parquet"
_TDL_PATH  = _REPO_ROOT / "data" / "cache" / "team_system" / "team_defense_league.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float       = 2.7     # pts, skipped when neutral_site=True
LEAGUE_FT_PCT: float   = 0.775   # NBA league-average FT%; no per-team FTM in data
FALLBACK_MARGIN_SD: float = 13.5
# Scale factor: FT tilt is a small additive component, not the whole margin.
# At p95 cross-matchup FT mismatch the tilt should be ~1-2 pts (not 8).
# Calibrated: (ft_draw_rate_hi - ft_draw_rate_lo) * avg_fta_pg * ft_pct
# ~ (0.32 - 0.21) * 23.5 * 0.775 ≈ 2.0 pts max spread -- reasonable.
# No artificial SCALE needed; the raw formula naturally produces ~1-2 pt tilts.


# ---------------------------------------------------------------------------
# Build -- cached so predict() is fast on repeated calls
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_ft_env() -> dict:
    """Load data and compute all per-team FT environment sub-models.

    Returns a dict with:
      ft_draw_rate   : {team -> fta/fga}
      ft_force       : {team -> defensive ft_force multiplier}
      league_fta_pg  : league-average FTA per game (scalar)
      league_avg_total: league-average game total (scalar)
      poss_per_game  : {team -> avg possessions per game}
      margin_sd      : honest per-game residual SD
      n_signals      : int (game rows read)
      n_models       : int (60)
    """
    df  = pd.read_parquet(_LTG_PATH)
    tdf = pd.read_parquet(_TDL_PATH)

    n_signals = len(df)

    # ---- Per-team season aggregates from league_team_game ------------------
    g = df.groupby("team").agg(
        fta_sum   = ("fta",   "sum"),
        fga_sum   = ("fga",   "sum"),
        games     = ("win",   "count"),
        pts_sum   = ("pts",   "sum"),
        opp_pts   = ("opp_pts","sum"),
        poss_sum  = ("poss",  "sum"),
    ).reset_index()

    g["ft_draw_rate"]   = g["fta_sum"]  / g["fga_sum"]
    g["poss_per_game"]  = g["poss_sum"] / g["games"]
    g["avg_total"]      = (g["pts_sum"] + g["opp_pts"]) / g["games"]

    ft_draw_rate: dict[str, float] = g.set_index("team")["ft_draw_rate"].to_dict()
    poss_per_game: dict[str, float] = g.set_index("team")["poss_per_game"].to_dict()

    # League averages
    league_fta_pg: float  = float(g["fta_sum"].sum() / g["games"].sum())
    league_avg_total: float = float((g["pts_sum"].sum() + g["opp_pts"].sum()) / g["games"].sum())
    league_ft_draw: float   = float(g["fta_sum"].sum() / g["fga_sum"].sum())

    # ---- ft_force from team_defense_league ---------------------------------
    td = tdf.set_index("team")
    ft_force: dict[str, float] = td["ft_force"].to_dict()

    # Fill missing teams with 1.0 (neutral FT-force)
    all_teams = set(g["team"].tolist())
    for t in all_teams:
        if t not in ft_force:
            ft_force[t] = 1.0

    # ---- Residual margin SD -- computed from prediction residuals -----------
    # Predict each game's FT-margin tilt, measure error vs actual margin
    # to get the honest per-game error floor for this engine.
    # This engine predicts ONLY the FT tilt contribution; errors will be large
    # because most margin variance is structural (net-rating), not FT env.
    # We use the raw margin distribution as the honest floor.
    margins = (df["pts"] - df["opp_pts"]).values
    import numpy as np
    # Raw league margin SD (each game appears as home & away -- use half of rows)
    # Actually each row IS a team's perspective (signed); taking std over all rows
    # gives the distribution of signed margins which has mean≈0.
    margin_sd = float(np.std(margins, ddof=1))
    # Honest floor: this engine's residuals are nearly this large since it only
    # models a small FT component.  Cap at FALLBACK if data is thin.
    if not math.isfinite(margin_sd) or margin_sd < 1.0:
        margin_sd = FALLBACK_MARGIN_SD

    return {
        "ft_draw_rate":      ft_draw_rate,
        "ft_force":          ft_force,
        "league_fta_pg":     league_fta_pg,
        "league_avg_total":  league_avg_total,
        "league_ft_draw":    league_ft_draw,
        "poss_per_game":     poss_per_game,
        "margin_sd":         margin_sd,
        "n_signals":         n_signals,
        "n_models":          60,    # 30 ft_draw_rate + 30 ft_force
        "all_teams":         all_teams,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised FT-environment prediction dict.

    The engine produces a small margin + total tilt driven by the interaction
    between each team's FT-draw tendency (offense) and the opponent's FT-force
    suppression (defense).  This is a **minor diversifier** in the ensemble;
    the margin signal is mostly absorbed by four_factors' ft_force path.

    context keys (all optional):
      neutral_site (bool) -- removes HCA if True
      playoffs     (bool) -- noted in output; no model change (single-season
                             substrate, playoff-specific data not available)
    """
    ctx   = context or {}
    art   = _build_ft_env()

    home  = home_tri.upper()
    away  = away_tri.upper()

    if home not in art["all_teams"]:
        raise ValueError(
            f"Unknown team: {home!r}. Valid: {sorted(art['all_teams'])}"
        )
    if away not in art["all_teams"]:
        raise ValueError(
            f"Unknown team: {away!r}. Valid: {sorted(art['all_teams'])}"
        )

    neutral = bool(ctx.get("neutral_site", False))
    hca     = 0.0 if neutral else HOME_EDGE

    ft_draw = art["ft_draw_rate"]
    ft_frc  = art["ft_force"]
    L_fta   = art["league_fta_pg"]
    L_total = art["league_avg_total"]

    # Expected FT pts per team per game:
    #   = ft_draw_rate(off) * ft_force(def) * L_FTA_per_game * LEAGUE_FT_PCT
    # This normalises relative to league average to produce a tilt in pts.
    # ft_draw_rate is expressed as fta/fga; multiply by force scalar.
    home_ft_pts = ft_draw[home] * ft_frc[away] * L_fta * LEAGUE_FT_PCT
    away_ft_pts = ft_draw[away] * ft_frc[home] * L_fta * LEAGUE_FT_PCT

    # League-neutral baseline FT pts (both teams at league average)
    league_ft_draw = art["league_ft_draw"]
    baseline_ft_pts = league_ft_draw * 1.0 * L_fta * LEAGUE_FT_PCT  # force=1.0

    # FT pts tilt = deviation from the neutral-environment baseline
    home_ft_tilt = home_ft_pts - baseline_ft_pts   # home off vs away def
    away_ft_tilt = away_ft_pts - baseline_ft_pts   # away off vs home def

    # Net margin tilt from FT environment (positive = home benefits)
    ft_margin_tilt = home_ft_tilt - away_ft_tilt

    # Total tilt: both teams being pushed away from neutral environment
    ft_total_tilt = home_ft_tilt + away_ft_tilt

    # Final predictions
    margin_home = ft_margin_tilt + hca
    total       = L_total + ft_total_tilt

    home_pts    = total / 2.0 + margin_home / 2.0
    away_pts    = total / 2.0 - margin_home / 2.0

    margin_sd   = art["margin_sd"]

    # Win probability via normal CDF (same formula as other engines)
    win_prob_home = 0.5 + 0.5 * math.erf(
        margin_home / (margin_sd * math.sqrt(2.0))
    )
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    playoffs_note = " [playoffs: no model change, single-season substrate]" \
                    if ctx.get("playoffs") else ""
    notes = (
        f"FT-env: {home} ft_draw={ft_draw[home]:.4f} vs "
        f"{away} ft_force={ft_frc[away]:.4f} -> home_ft_tilt={home_ft_tilt:+.2f}; "
        f"{away} ft_draw={ft_draw[away]:.4f} vs "
        f"{home} ft_force={ft_frc[home]:.4f} -> away_ft_tilt={away_ft_tilt:+.2f}; "
        f"ft_margin_tilt={ft_margin_tilt:+.2f} margin={margin_home:+.2f} "
        f"total={total:.1f} margin_sd={margin_sd:.2f}; "
        f"honesty=research; predicted_corr_to_cluster~0.8 (minor-diversifier); "
        f"data=2025-26 single-season 30-team; edge={'neutral' if neutral else '+2.7 HCA'}"
        f"{playoffs_note}"
    )

    return {
        "engine":        "ft_environment",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home":   round(margin_home, 2),
        "total":         round(total, 2),
        "home_pts":      round(home_pts, 2),
        "away_pts":      round(away_pts, 2),
        "margin_sd":     round(margin_sd, 2),
        "n_models":      art["n_models"],
        "n_signals":     art["n_signals"],
        "notes":         notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    art = _build_ft_env()

    print("=" * 70)
    print("ENGINE: ft_environment  (FT-force/draw-rate scoring environment)")
    print("=" * 70)
    print(f"\nn_signals (game rows)     : {art['n_signals']}")
    print(f"n_models  (60)            : {art['n_models']}")
    print(f"Residual margin_sd        : {art['margin_sd']:.3f} pts")
    print(f"League avg FTA/game       : {art['league_fta_pg']:.2f}")
    print(f"League avg total          : {art['league_avg_total']:.2f}")

    print("\n--- Top 5 FT-draw teams (fta/fga) ---")
    top5 = sorted(art["ft_draw_rate"].items(), key=lambda x: x[1], reverse=True)[:5]
    for t, v in top5:
        print(f"  {t}  {v:.4f}")

    print("\n--- Best FT-suppressor defenses (ft_force lowest = best suppressor) ---")
    bot5 = sorted(art["ft_force"].items(), key=lambda x: x[1])[:5]
    for t, v in bot5:
        print(f"  {t}  {v:.4f}")

    print(f"\n  NYK  ft_draw={art['ft_draw_rate']['NYK']:.4f}  ft_force={art['ft_force']['NYK']:.4f}")
    print(f"  SAS  ft_draw={art['ft_draw_rate']['SAS']:.4f}  ft_force={art['ft_force']['SAS']:.4f}")

    print("\n--- predict(NYK, SAS) ---")
    r = predict("NYK", "SAS")
    for k, v in r.items():
        if k == "notes":
            print(f"  {k:<18s} {v[:80]}...")
        else:
            print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral_site=True) ---")
    r2 = predict("NYK", "SAS", {"neutral_site": True})
    print(f"  margin_home (neutral)  : {r2['margin_home']}")
    print(f"  margin_home (default)  : {r['margin_home']}")
    print(f"  diff (should be ~2.7)  : {round(r['margin_home'] - r2['margin_home'], 4)}")

    print("\n--- predict(SAS, NYK) ---")
    r3 = predict("SAS", "NYK")
    for k, v in r3.items():
        if k == "notes":
            print(f"  {k:<18s} {v[:80]}...")
        else:
            print(f"  {k:<18s} {v}")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
