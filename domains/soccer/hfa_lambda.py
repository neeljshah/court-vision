"""domains.soccer.hfa_lambda — Home-field advantage (HFA) correction for Poisson goal lambdas.

Wraps domains.soccer.ratings.walk_forward_goals and applies a mass-preserving
home-advantage multiplier derived strictly from prior matches (no future leak).

The unadjusted Poisson lambdas are symmetric w.r.t. home/away advantage.  In
practice home teams score more (empirically ~1.511 vs ~1.213 away goals/game).
This module estimates the league home multiplier h from prior matches and
rescales:

    lam_home_adj = lam_home_base * sqrt(h)
    lam_away_adj = lam_away_base / sqrt(h)

so that lam_home_adj * lam_away_adj == lam_home_base * lam_away_base (mass-
preserving — total expected goals are conserved).

Walk-forward contract (leak-free):
  For match i, h is computed from the EW state BEFORE match i is folded in.
  Match 0 → h = 1.0 (no prior data; symmetric).

HONEST: value = improved 1X2 / home / away calibration from correcting a known
systematic bias in the symmetric Poisson baseline.  NO edge claimed; gate decides
signal merit.

INVARIANTS:
- Does NOT modify src/, kernel/, api/, or any existing domains/soccer/*.py.
- Imports domains.soccer.ratings and domains.soccer.config read-only.
- <=300 physical lines.
"""
from __future__ import annotations

import math
from typing import List

import pandas as pd

from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA
from domains.soccer.ratings import walk_forward_goals

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_forward_hfa(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Compute leak-free per-match HFA-adjusted Poisson lambdas.

    For each match in chronological order:
      1. Snapshot the CURRENT expanding h (computed from all PRIOR matches).
      2. Record lam_home_base / lam_away_base from walk_forward_goals.
      3. Apply mass-preserving HFA correction:
             lam_home_adj = lam_home_base * sqrt(h)
             lam_away_adj = lam_away_base / sqrt(h)
      4. Update the expanding h estimate with this match's result.

    Parameters
    ----------
    matches_df:
        DataFrame passed directly to walk_forward_goals; must have columns:
        date, div, home_team, away_team, fthg, ftag, and optionally event_id.

    Returns
    -------
    pd.DataFrame
        One row per match (same order as walk_forward_goals) with columns:

        event_id       — from input (if present), else positional index string
        date           — match date
        h              — EW home multiplier STRICTLY BEFORE this match
                         (= 1.0 for the first match; > 1.0 once home teams
                          consistently outscore away teams in the history)
        lam_home_base  — unadjusted home Poisson lambda (from ratings.py)
        lam_away_base  — unadjusted away Poisson lambda (from ratings.py)
        lam_home_adj   — HFA-adjusted home lambda = lam_home_base * sqrt(h)
        lam_away_adj   — HFA-adjusted away lambda = lam_away_base / sqrt(h)
    """
    # Step 1: get the base (symmetric) walk-forward lambdas.
    wf = walk_forward_goals(matches_df)

    # Step 2: walk forward the home-multiplier h in a SEPARATE pass so that
    # update is strictly post-match (snapshot-before-update contract).
    # We maintain two running EW means (same ALPHA as the goals model):
    #   ew_home  = EW mean of home goals scored
    #   ew_away  = EW mean of away goals scored
    # h = ew_home / ew_away (prior to each match)
    #
    # Initial state mirrors GoalsState defaults so the multiplier is coherent
    # with the team-level model's universe.
    ew_home: float = PRIOR_GF
    ew_away: float = PRIOR_GA

    h_vals: List[float] = []
    lam_home_adj_vals: List[float] = []
    lam_away_adj_vals: List[float] = []

    for i, row in wf.iterrows():
        # --- SNAPSHOT h BEFORE this match ---
        # Guard against division-by-zero (ew_away is initialised to PRIOR_GA>0
        # and ALPHA<1 so it can only approach 0 if all observed ftag == 0,
        # which is practically impossible; guard for mathematical completeness).
        if ew_away > 0.0:
            h = ew_home / ew_away
        else:
            h = 1.0

        h_vals.append(h)

        # --- APPLY mass-preserving correction ---
        lam_h_base = float(row["lam_home"])
        lam_a_base = float(row["lam_away"])
        sqrt_h = math.sqrt(max(h, 1e-12))   # clamp against degenerate h<=0
        lam_home_adj_vals.append(lam_h_base * sqrt_h)
        lam_away_adj_vals.append(lam_a_base / sqrt_h)

        # --- UPDATE EW means AFTER snapshot (post-match) ---
        fthg = float(row["fthg"])
        ftag = float(row["ftag"])
        if math.isfinite(fthg) and math.isfinite(ftag):
            ew_home += ALPHA * (fthg - ew_home)
            ew_away += ALPHA * (ftag - ew_away)
        # NaN/inf results: skip update (same guard as ratings.py)

    # Step 3: build output DataFrame
    out = pd.DataFrame(
        {
            "event_id": (
                wf["event_id"].values
                if "event_id" in wf.columns
                else [str(j) for j in range(len(wf))]
            ),
            "date": wf["date"].values,
            "h": h_vals,
            "lam_home_base": wf["lam_home"].values,
            "lam_away_base": wf["lam_away"].values,
            "lam_home_adj": lam_home_adj_vals,
            "lam_away_adj": lam_away_adj_vals,
        }
    )
    return out.reset_index(drop=True)
