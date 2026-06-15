"""domains.tennis.elo_core — core Elo primitives for tennis.

Constants, EloState dataclass, internal helpers, and the ``replay`` / ``prob``
functions.  Split from elo.py for LOC-discipline (≤300 LOC/file rule); elo.py
re-exports everything so existing callers are unaffected.

PRIVATE: F5-clean — stdlib + numpy/pandas only; no src.* / kernel.* imports.
Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Module-level constants (tunable at T-B-004 via config; never via kernel edits)
# ---------------------------------------------------------------------------
BASE_RATING: float = 1500.0

# K-decay: K(m) = K_NUMERATOR / (m + K_OFFSET) ** K_EXPONENT
# Standard tennis Elo decay (Kovalchik 2016 parameterisation).
K_NUMERATOR: float = 250.0
K_OFFSET: float = 5.0
K_EXPONENT: float = 0.4

# Blend weight for surface-specific component (0 = overall-only, 1 = surface-only)
SURFACE_BLEND: float = 0.3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EloState:
    """Immutable snapshot of Elo ratings at a point in time.

    ``ratings``        : player_id → overall Elo
    ``surface``        : (player_id, surface) → surface-specific Elo
    ``counts``         : player_id → number of matches processed
    ``surface_counts`` : (player_id, surface) → surface matches processed
    ``last_date``      : date of the last processed match (None if empty)
    ``n_processed``    : total matches processed
    """

    ratings: dict[int, float] = field(default_factory=dict)
    surface: dict[tuple[int, str], float] = field(default_factory=dict)
    counts: dict[int, int] = field(default_factory=dict)
    surface_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    last_date: Optional[dt.date] = None
    n_processed: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _k(match_count: int) -> float:
    """K-factor for a player who has completed ``match_count`` prior matches."""
    return K_NUMERATOR / ((match_count + K_OFFSET) ** K_EXPONENT)


def _expected(r1: float, r2: float) -> float:
    """Standard Elo expected score for player 1 given ratings r1, r2."""
    return 1.0 / (1.0 + 10.0 ** ((r2 - r1) / 400.0))


def _blended_diff(state: EloState, p1_id: int, p2_id: int, surface: str) -> float:
    """Return the blended Elo difference used for win-probability calculation.

    ``d_blend = (1 - SURFACE_BLEND) * (r1 - r2) + SURFACE_BLEND * (s1 - s2)``

    Surface-specific rating defaults to the player's overall rating when no
    surface match has been processed yet for that player+surface combination.
    """
    r1 = state.ratings.get(p1_id, BASE_RATING)
    r2 = state.ratings.get(p2_id, BASE_RATING)
    s1 = state.surface.get((p1_id, surface), r1)
    s2 = state.surface.get((p2_id, surface), r2)
    return (1.0 - SURFACE_BLEND) * (r1 - r2) + SURFACE_BLEND * (s1 - s2)


def _is_walkover(score: object) -> bool:
    """Return True if the score string indicates a walkover (no match played)."""
    if not isinstance(score, str):
        return False
    sl = score.upper()
    return "W/O" in sl or "WALKOVER" in sl


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------

def _sort_key(df: pd.DataFrame) -> pd.Series:
    """Stable chronological sort key matching §3.1 pinned order.

    Primary: date.  Secondary: tour, tourney_id, round order, match_num.
    Unknown rounds map to a sentinel (99) so they sort AFTER all known rounds
    (F == 13) rather than colliding with R128 (== 6) in the intra-day tiebreak.
    Keys are zero-padded so the sentinel orders correctly as a string.
    """
    ROUND_ORDER: dict[str, int] = {
        "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
        "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
        "QF": 10, "SF": 11, "BR": 12, "F": 13,
    }
    round_col = df["round"].map(ROUND_ORDER).fillna(99).astype(int)
    tour_col = df["tour"] if "tour" in df.columns else pd.Series([""] * len(df), index=df.index)
    tourney_col = df["tourney_id"] if "tourney_id" in df.columns else pd.Series([""] * len(df), index=df.index)
    match_num_col = df["match_num"] if "match_num" in df.columns else pd.Series(0, index=df.index)
    # Compose a sortable tuple via a multi-column key
    return (
        df["date"].astype(str),
        tour_col.astype(str),
        tourney_col.astype(str),
        round_col.astype(str).str.zfill(2),
        match_num_col.astype(str).str.zfill(6),
    )


def _sorted(matches: pd.DataFrame) -> pd.DataFrame:
    """Return ``matches`` sorted by the §3.1 pinned chronological order."""
    keys = _sort_key(matches)
    sort_df = pd.DataFrame(
        {
            "k0": keys[0].values,
            "k1": keys[1].values,
            "k2": keys[2].values,
            "k3": keys[3].values,
            "k4": keys[4].values,
        },
        index=matches.index,
    )
    sorted_idx = sort_df.sort_values(
        ["k0", "k1", "k2", "k3", "k4"], kind="mergesort"
    ).index
    return matches.loc[sorted_idx].reset_index(drop=True)


def replay(matches: pd.DataFrame, until: Optional[dt.date] = None) -> EloState:
    """Replay matches in chronological order and return the resulting EloState.

    Parameters
    ----------
    matches:
        DataFrame with at minimum columns: ``date`` (date-like), ``p1_id`` (int),
        ``p2_id`` (int), ``winner`` (1 or 2), ``surface`` (str), ``score`` (str).
        Optional columns used for tiebreaking: ``tour``, ``tourney_id``, ``round``,
        ``match_num``.
    until:
        If provided, process only matches with ``date < until`` (strictly before).
        This is the ``AsOfContext.decision_time`` contract: the date D itself is
        excluded so that ratings are leak-free for predicting matches ON date D.

    Returns
    -------
    EloState
        Snapshot of ratings AFTER processing all qualifying matches.
    """
    df = _sorted(matches)

    # Normalise date column to dt.date objects for comparison
    dates = pd.to_datetime(df["date"]).dt.date

    state = EloState()

    for i in range(len(df)):
        row_date = dates.iloc[i]

        # Strict-before filter
        if until is not None and row_date >= until:
            continue

        p1_id = int(df["p1_id"].iloc[i])
        p2_id = int(df["p2_id"].iloc[i])
        winner = int(df["winner"].iloc[i])  # 1 → p1 won, 2 → p2 won
        surface = str(df["surface"].iloc[i]) if pd.notna(df["surface"].iloc[i]) else "Unknown"
        score = df["score"].iloc[i] if "score" in df.columns else ""

        # Walkovers: record the date progress but skip rating update
        if _is_walkover(score):
            state.last_date = row_date
            continue

        # Pre-match ratings (already in state from prior matches)
        r1 = state.ratings.get(p1_id, BASE_RATING)
        r2 = state.ratings.get(p2_id, BASE_RATING)
        s1 = state.surface.get((p1_id, surface), r1)
        s2 = state.surface.get((p2_id, surface), r2)

        c1 = state.counts.get(p1_id, 0)
        c2 = state.counts.get(p2_id, 0)
        sc1 = state.surface_counts.get((p1_id, surface), 0)
        sc2 = state.surface_counts.get((p2_id, surface), 0)

        # Actual scores (1 = win, 0 = loss)
        actual1 = 1.0 if winner == 1 else 0.0
        actual2 = 1.0 - actual1

        # Expected scores (using overall ratings for the update step)
        exp1 = _expected(r1, r2)
        exp2 = 1.0 - exp1

        k1 = _k(c1)
        k2 = _k(c2)
        sk1 = _k(sc1)
        sk2 = _k(sc2)

        # Update overall ratings
        state.ratings[p1_id] = r1 + k1 * (actual1 - exp1)
        state.ratings[p2_id] = r2 + k2 * (actual2 - exp2)

        # Update surface ratings (same Elo formula, independent track)
        exp_s1 = _expected(s1, s2)
        exp_s2 = 1.0 - exp_s1
        state.surface[(p1_id, surface)] = s1 + sk1 * (actual1 - exp_s1)
        state.surface[(p2_id, surface)] = s2 + sk2 * (actual2 - exp_s2)

        # Increment match counters
        state.counts[p1_id] = c1 + 1
        state.counts[p2_id] = c2 + 1
        state.surface_counts[(p1_id, surface)] = sc1 + 1
        state.surface_counts[(p2_id, surface)] = sc2 + 1

        state.last_date = row_date
        state.n_processed += 1

    return state


def prob(state: EloState, p1_id: int, p2_id: int, surface: str) -> float:
    """Return the blended Elo win probability P(p1 beats p2) on ``surface``.

    Uses ``SURFACE_BLEND`` to mix overall and surface-specific ratings.
    Falls back to BASE_RATING for unseen players/surfaces.
    """
    diff = _blended_diff(state, p1_id, p2_id, surface)
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
