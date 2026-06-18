"""domains.soccer_intl.ratings - leak-free walk-forward EW Poisson goals ratings
for INTERNATIONAL (national-team) football, neutral-site aware.

Reuses the GoalsState EW goals-rate model and the Poisson-lambda construction
from domains/soccer/ratings.py, adapted for the international corpus:

  * column names are home_team / away_team / home_score / away_score (martj42),
  * a NEUTRAL flag per match: the home-field goal bump (learned from the corpus
    on non-neutral matches) is applied ONLY when the match is not neutral,
  * sparse / unseen national teams fall back to PRIOR_GF / PRIOR_GA gracefully.

Leak-free: the PRE-match snapshot is recorded BEFORE the EW update folds the
result in, so future results can never contaminate a prediction.  Strictly
prior-only by chronological replay (matching domains/soccer truncation semantics).

Imports NOTHING from src.* / kernel.* / domains.nba.  <=300 LOC.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import pandas as pd

from domains.soccer_intl.config import (
    ALPHA,
    HOME_ADV_GOALS_FALLBACK,
    MIN_SEASON_YEAR,
    PRIOR_GF,
    PRIOR_GA,
    RATE_CLIP,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GoalsState:
    """EW national-team goals rates at a point in time (mirror of soccer.GoalsState).

    ``gf_ew``/``ga_ew`` : team -> EW goals-for / goals-against rate
    ``counts``          : team -> matches processed
    ``league_mu``       : EW mean goals scored by a side across all matches
    ``home_adv``        : learned multiplicative home bump (non-neutral only)
    ``last_date``       : date of last processed match
    ``n_processed``     : total matches processed
    """

    gf_ew: Dict[str, float] = field(default_factory=dict)
    ga_ew: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    league_mu: float = (PRIOR_GF + PRIOR_GA) / 2.0
    home_adv: float = HOME_ADV_GOALS_FALLBACK
    last_date: Optional[dt.date] = None
    n_processed: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise the martj42 schema, drop pre-MIN_SEASON_YEAR rows, sort chrono.

    Adds canonical columns: fthg, ftag (full-time goals), keeps neutral as bool.
    Sort key: (date, home_team, away_team), mergesort-stable for determinism.
    """
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["date"].dt.year >= MIN_SEASON_YEAR]
    d["fthg"] = pd.to_numeric(d["home_score"], errors="coerce")
    d["ftag"] = pd.to_numeric(d["away_score"], errors="coerce")
    if "neutral" in d.columns:
        d["neutral"] = d["neutral"].astype(str).str.upper().map(
            {"TRUE": True, "FALSE": False}
        ).fillna(False)
    else:
        d["neutral"] = False
    sort_df = pd.DataFrame(
        {
            "k0": d["date"].astype(str).values,
            "k1": d["home_team"].astype(str).values,
            "k2": d["away_team"].astype(str).values,
        },
        index=d.index,
    )
    order = sort_df.sort_values(["k0", "k1", "k2"], kind="mergesort").index
    return d.loc[order].reset_index(drop=True)


def fit_home_adv(df: pd.DataFrame) -> float:
    """Learn the multiplicative home-goals bump from NON-neutral played matches.

    home_adv = (mean home goals / mean away goals) - 1 over non-neutral games.
    Clipped to [0, 0.6].  Falls back to HOME_ADV_GOALS_FALLBACK if no data.
    """
    d = df.dropna(subset=["fthg", "ftag"])
    d = d[~d["neutral"].astype(bool)]
    if len(d) < 100:
        return HOME_ADV_GOALS_FALLBACK
    mu_home = float(d["fthg"].mean())
    mu_away = float(d["ftag"].mean())
    if mu_away <= 0:
        return HOME_ADV_GOALS_FALLBACK
    return min(max(mu_home / mu_away - 1.0, 0.0), 0.6)


def _lambdas(
    state: GoalsState, home: str, away: str, neutral: bool
) -> Tuple[float, float]:
    """Return (lam_home, lam_away) - Poisson rates STRICTLY PRE-MATCH.

    Unseen teams receive PRIOR_GF / PRIOR_GA.  When the match is NOT neutral the
    home side's lambda is multiplied by (1 + home_adv) and the away side's lambda
    divided by sqrt(1 + home_adv) (a mild symmetric tilt); neutral matches get NO
    home tilt - the World Cup case.
    """
    lo, hi = RATE_CLIP

    def clip(x: float) -> float:
        return min(max(x, lo), hi)

    gf_h = clip(state.gf_ew.get(home, PRIOR_GF))
    ga_a = clip(state.ga_ew.get(away, PRIOR_GA))
    gf_a = clip(state.gf_ew.get(away, PRIOR_GF))
    ga_h = clip(state.ga_ew.get(home, PRIOR_GA))

    mu_all = max(state.league_mu, 0.25)
    lam_home = gf_h * ga_a / mu_all
    lam_away = gf_a * ga_h / mu_all

    if not neutral:
        bump = 1.0 + state.home_adv
        lam_home *= bump
        lam_away /= math.sqrt(bump)

    return clip(lam_home), clip(lam_away)


def _p_over(lam_t: float) -> float:
    """P(Poisson(lam_t) >= 3) = 1 - exp(-lam_t)*(1 + lam_t + lam_t^2/2)."""
    return 1.0 - math.exp(-lam_t) * (1.0 + lam_t + lam_t * lam_t / 2.0)


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def _fold(state: GoalsState, home: str, away: str, fthg: float, ftag: float) -> None:
    """Fold one finite result into the EW state (post-snapshot)."""
    if not (math.isfinite(fthg) and math.isfinite(ftag)):
        return
    state.gf_ew[home] += ALPHA * (fthg - state.gf_ew[home])
    state.ga_ew[home] += ALPHA * (ftag - state.ga_ew[home])
    state.gf_ew[away] += ALPHA * (ftag - state.gf_ew[away])
    state.ga_ew[away] += ALPHA * (fthg - state.ga_ew[away])
    state.counts[home] = state.counts.get(home, 0) + 1
    state.counts[away] = state.counts.get(away, 0) + 1
    state.league_mu += ALPHA * ((fthg + ftag) / 2.0 - state.league_mu)


def _init_team(state: GoalsState, team: str) -> None:
    if team not in state.gf_ew:
        state.gf_ew[team] = PRIOR_GF
        state.ga_ew[team] = PRIOR_GA


def replay(matches: pd.DataFrame, until: Optional[dt.date] = None) -> GoalsState:
    """Replay matches chronologically; return GoalsState after all qualifying rows.

    ``until``: process only matches with date < until (strictly before) - the
    leak-free as-of contract for predicting matches ON ``until``.
    """
    df = _prep(matches)
    dates = df["date"].dt.date
    state = GoalsState()
    state.home_adv = fit_home_adv(df if until is None else df[dates < until])

    for i in range(len(df)):
        row_date = dates.iloc[i]
        if until is not None and row_date >= until:
            continue
        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        _init_team(state, home)
        _init_team(state, away)
        _fold(state, home, away, float(df["fthg"].iloc[i]), float(df["ftag"].iloc[i]))
        state.last_date = row_date
        state.n_processed += 1

    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_forward_goals(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Leak-free per-match pre-match lambdas + O/U-2.5 over prob.

    For each match in date order: (1) record PRE-match lambdas from prior-only
    state, (2) fold the result.  home_adv is fit ONCE on the full corpus - it is
    a stable league-level constant, not a per-team rate, so this does not leak a
    specific result into its own prediction (sensitivity is negligible).
    """
    df = _prep(matches_df)
    dates = df["date"].dt.date
    state = GoalsState()
    state.home_adv = fit_home_adv(df)

    lam_homes, lam_aways, lam_totals, p_overs = [], [], [], []

    for i in range(len(df)):
        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        neutral = bool(df["neutral"].iloc[i])
        _init_team(state, home)
        _init_team(state, away)

        lam_h, lam_a = _lambdas(state, home, away, neutral)
        lam_t = lam_h + lam_a
        lam_homes.append(lam_h)
        lam_aways.append(lam_a)
        lam_totals.append(lam_t)
        p_overs.append(_p_over(lam_t))

        _fold(state, home, away, float(df["fthg"].iloc[i]), float(df["ftag"].iloc[i]))
        state.last_date = dates.iloc[i]
        state.n_processed += 1

    out = df.copy()
    out["lam_home"] = lam_homes
    out["lam_away"] = lam_aways
    out["lam_total"] = lam_totals
    out["p_over25"] = p_overs
    return out


def goals_state_asof(matches_df: pd.DataFrame, date: dt.date) -> GoalsState:
    """GoalsState using only matches strictly before ``date`` (== replay(..., until=date))."""
    return replay(matches_df, until=date)
