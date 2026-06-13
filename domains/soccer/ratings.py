"""domains.soccer.ratings — leak-free walk-forward Poisson goals ratings for soccer.

Replay a chronologically-sorted sequence of matches and emit per-match PRE-match
team goals rates (the leak-free prediction features).  Rates are updated AFTER the
pre-match snapshot is recorded — so future results can never contaminate features.

Model: exponentially-weighted (EW) goals-for / goals-against rates per team, used
to form Poisson lambda estimates for the O/U 2.5 goals market.

PRIVATE: outputs are price-bearing or license-restricted when combined with odds;
``data/domains/soccer/`` is never tracked.  No src.* / kernel.* / domains.nba.*
imports (falsifier F5 compliance).

football-data.co.uk data is free for personal/research use only; nothing derived
is published on the public repo.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import pandas as pd

from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA, RATE_CLIP

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GoalsState:
    """Snapshot of exponentially-weighted team goals rates at a point in time.

    ``gf_ew``          : team_name → EW goals-for rate
    ``ga_ew``          : team_name → EW goals-against rate
    ``counts``         : team_name → number of matches processed
    ``league_mu_home`` : EW mean of home goals scored across all matches
    ``league_mu_away`` : EW mean of away goals scored across all matches
    ``last_date``      : date of the last processed match (None if empty)
    ``n_processed``    : total matches processed
    """

    gf_ew: Dict[str, float] = field(default_factory=dict)
    ga_ew: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    league_mu_home: float = PRIOR_GF
    league_mu_away: float = PRIOR_GA
    last_date: Optional[dt.date] = None
    n_processed: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Return ``df`` sorted by the §3.1 pinned chronological order.

    Key: (date, div, home_team, away_team) — mergesort-stable so ties within
    the same match-day retain their original relative order, and both replay()
    and walk_forward_goals() traverse rows in identical sequence.
    """
    sort_df = pd.DataFrame(
        {
            "k0": df["date"].astype(str).values,
            "k1": df["div"].astype(str).values if "div" in df.columns else [""] * len(df),
            "k2": df["home_team"].astype(str).values,
            "k3": df["away_team"].astype(str).values,
        },
        index=df.index,
    )
    sorted_idx = sort_df.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[sorted_idx].reset_index(drop=True)


def _lambdas(state: GoalsState, home: str, away: str) -> Tuple[float, float]:
    """Return (lam_home, lam_away) — Poisson rate estimates STRICTLY PRE-MATCH.

    Uses the snapshot rates from ``state`` (caller must not have folded this
    match in yet).  Unseen teams receive PRIOR_GF / PRIOR_GA defaults.

    Formula (pinned)::

        mu_all   = max((league_mu_home + league_mu_away) / 2.0, 0.25)
        lam_home = clip(gf_ew[home]) * clip(ga_ew[away]) / mu_all
        lam_away = clip(gf_ew[away]) * clip(ga_ew[home]) / mu_all

    where clip(x) = min(max(x, RATE_CLIP[0]), RATE_CLIP[1]).
    """
    lo, hi = RATE_CLIP

    def clip(x: float) -> float:
        return min(max(x, lo), hi)

    gf_h = clip(state.gf_ew.get(home, PRIOR_GF))
    ga_a = clip(state.ga_ew.get(away, PRIOR_GA))
    gf_a = clip(state.gf_ew.get(away, PRIOR_GF))
    ga_h = clip(state.ga_ew.get(home, PRIOR_GA))

    mu_all = max((state.league_mu_home + state.league_mu_away) / 2.0, 0.25)

    lam_home = gf_h * ga_a / mu_all
    lam_away = gf_a * ga_h / mu_all
    return lam_home, lam_away


def _p_over(lam_t: float) -> float:
    """P(Poisson(lam_t) >= 3) = 1 - exp(-lam_t) * (1 + lam_t + lam_t^2 / 2).

    Corresponds to the O/U 2.5 goals Over probability (3 or more goals).
    Uses stdlib ``math`` only — no scipy dependency.
    """
    return 1.0 - math.exp(-lam_t) * (1.0 + lam_t + lam_t * lam_t / 2.0)


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def replay(matches: pd.DataFrame, until: Optional[dt.date] = None) -> GoalsState:
    """Replay matches in chronological order and return the resulting GoalsState.

    Parameters
    ----------
    matches:
        DataFrame with at minimum columns: ``date`` (date-like), ``div`` (str),
        ``home_team`` (str), ``away_team`` (str), ``fthg`` (numeric),
        ``ftag`` (numeric).
    until:
        If provided, process only matches with ``date < until`` (strictly before).
        This is the ``AsOfContext.decision_time`` contract: the date D itself is
        excluded so that ratings are leak-free for predicting matches ON date D.

    Returns
    -------
    GoalsState
        Snapshot of ratings AFTER processing all qualifying matches.
    """
    df = _sorted(matches)
    dates = pd.to_datetime(df["date"]).dt.date

    state = GoalsState()

    for i in range(len(df)):
        row_date = dates.iloc[i]

        # Strict-before filter
        if until is not None and row_date >= until:
            continue

        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        fthg = float(df["fthg"].iloc[i])
        ftag = float(df["ftag"].iloc[i])

        # --- INITIALISE unseen teams to priors BEFORE first update ---
        if home not in state.gf_ew:
            state.gf_ew[home] = PRIOR_GF
            state.ga_ew[home] = PRIOR_GA
        if away not in state.gf_ew:
            state.gf_ew[away] = PRIOR_GF
            state.ga_ew[away] = PRIOR_GA

        # --- UPDATE EW rates (snapshot is implicit — caller of _lambdas reads
        #     the state before this block runs) ---
        # Guard: skip the EW update when either score is non-finite (NaN/inf).
        # The PRE-MATCH snapshot (computed BEFORE this block) is still emitted
        # for the NaN row — it is prior-based and always finite.  Skipping keeps
        # subsequent rows uncontaminated.  Finite inputs are unaffected (no-op).
        if math.isfinite(fthg) and math.isfinite(ftag):
            state.gf_ew[home] += ALPHA * (fthg - state.gf_ew[home])
            state.ga_ew[home] += ALPHA * (ftag - state.ga_ew[home])
            state.gf_ew[away] += ALPHA * (ftag - state.gf_ew[away])
            state.ga_ew[away] += ALPHA * (fthg - state.ga_ew[away])

            state.counts[home] = state.counts.get(home, 0) + 1
            state.counts[away] = state.counts.get(away, 0) + 1

            # EW-update league means
            state.league_mu_home += ALPHA * (fthg - state.league_mu_home)
            state.league_mu_away += ALPHA * (ftag - state.league_mu_away)

        state.last_date = row_date
        state.n_processed += 1

    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_forward_goals(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Compute leak-free per-match pre-match Poisson lambdas and O/U probability.

    For each match IN DATE ORDER:
      1. Record the PRE-match lambdas (computed from only prior matches — snapshot).
      2. Then update EW rates from the result.

    Parameters
    ----------
    matches_df:
        DataFrame with columns: ``date``, ``div``, ``home_team``, ``away_team``,
        ``fthg``, ``ftag``.  Extra columns are preserved.

    Returns
    -------
    pd.DataFrame
        Input rows in chronological order with added columns (all STRICTLY
        pre-match):
        ``lam_home``  — Poisson lambda for home goals
        ``lam_away``  — Poisson lambda for away goals
        ``lam_total`` — lam_home + lam_away
        ``p_over25``  — P(total goals >= 3) = P(Poisson(lam_total) >= 3)
    """
    df = _sorted(matches_df)
    dates = pd.to_datetime(df["date"]).dt.date

    state = GoalsState()

    lam_homes: list[float] = []
    lam_aways: list[float] = []
    lam_totals: list[float] = []
    p_overs: list[float] = []

    for i in range(len(df)):
        row_date = dates.iloc[i]
        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        fthg = float(df["fthg"].iloc[i])
        ftag = float(df["ftag"].iloc[i])

        # --- INITIALISE unseen teams to priors BEFORE snapshot/update ---
        if home not in state.gf_ew:
            state.gf_ew[home] = PRIOR_GF
            state.ga_ew[home] = PRIOR_GA
        if away not in state.gf_ew:
            state.gf_ew[away] = PRIOR_GF
            state.ga_ew[away] = PRIOR_GA

        # ---- RECORD PRE-MATCH LAMBDAS (leak-free snapshot) ----
        lam_h, lam_a = _lambdas(state, home, away)
        lam_t = lam_h + lam_a
        lam_homes.append(lam_h)
        lam_aways.append(lam_a)
        lam_totals.append(lam_t)
        p_overs.append(_p_over(lam_t))

        # ---- UPDATE EW RATES (post-match) ----
        # Guard: skip update when either score is non-finite (NaN/inf) so that
        # poison from a missing result does NOT propagate to later rows.
        # The snapshot already recorded above is prior-based and always finite.
        if math.isfinite(fthg) and math.isfinite(ftag):
            state.gf_ew[home] += ALPHA * (fthg - state.gf_ew[home])
            state.ga_ew[home] += ALPHA * (ftag - state.ga_ew[home])
            state.gf_ew[away] += ALPHA * (ftag - state.gf_ew[away])
            state.ga_ew[away] += ALPHA * (fthg - state.ga_ew[away])

            state.counts[home] = state.counts.get(home, 0) + 1
            state.counts[away] = state.counts.get(away, 0) + 1

            state.league_mu_home += ALPHA * (fthg - state.league_mu_home)
            state.league_mu_away += ALPHA * (ftag - state.league_mu_away)

        state.last_date = row_date
        state.n_processed += 1

    out = df.copy()
    out["lam_home"] = lam_homes
    out["lam_away"] = lam_aways
    out["lam_total"] = lam_totals
    out["p_over25"] = p_overs
    return out


def goals_state_asof(matches_df: pd.DataFrame, date: dt.date) -> GoalsState:
    """Return the GoalsState using only matches strictly before ``date``.

    Equivalent to ``replay(matches_df, until=date)`` — alias kept for the
    adapter API contract.

    Truncation-invariance guarantee:
        ``goals_state_asof(full_df, D)`` is **bitwise-identical** to the
        GoalsState you would obtain by replaying only the subset of rows with
        ``date < D`` through a fresh ``replay()`` call.  Both paths execute the
        same sorted iteration in the same order — identical float operations
        ⇒ identical bits.
    """
    return replay(matches_df, until=date)
