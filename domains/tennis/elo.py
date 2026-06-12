"""domains.tennis.elo — leak-free walk-forward Elo for tennis matches.

Replay a chronologically-sorted sequence of matches and emit per-match PRE-match
Elo ratings (the leak-free prediction features). Ratings are updated AFTER the
pre-match snapshot is recorded — so future results can never contaminate features.

Surface blending: overall + per-surface ratings.  Walkovers (W/O) are skipped
(no tennis played → no rating update).  Retirements receive a normal update.

PRIVATE: outputs are price-bearing or license-restricted when combined with odds;
``data/domains/tennis/`` is never tracked.  No src.* / kernel.* / domains.nba.*
imports (falsifier F5 compliance).

Sackmann data is CC BY-NC-SA — private research use only; nothing derived is published.
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
    Unknown rounds map to the mid-value (6) so they slot between Q rounds and
    later-stage matches rather than silently floating to the top or bottom.
    """
    ROUND_ORDER: dict[str, int] = {
        "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
        "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
        "QF": 10, "SF": 11, "BR": 12, "F": 13,
    }
    round_col = df["round"].map(ROUND_ORDER).fillna(6).astype(int)
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def walk_forward_elo(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Compute leak-free per-match pre-match Elo ratings and win probability.

    For each match IN DATE ORDER:
      1. Record the PRE-match Elo ratings (computed from only prior matches).
      2. Then update ratings from the result.

    Parameters
    ----------
    matches_df:
        DataFrame with columns: ``date``, ``p1_id``, ``p2_id``, ``winner``
        (1 or 2), ``surface``, ``score``.  Extra columns are preserved.

    Returns
    -------
    pd.DataFrame
        Input rows in chronological order with added columns:
        ``p1_elo``, ``p2_elo`` (pre-match overall ratings),
        ``p1_surface_elo``, ``p2_surface_elo`` (pre-match surface ratings),
        ``win_prob_p1`` (P(p1 wins), blended, strictly pre-match).
    """
    df = _sorted(matches_df)
    dates = pd.to_datetime(df["date"]).dt.date

    state = EloState()

    p1_elos: list[float] = []
    p2_elos: list[float] = []
    p1_surface_elos: list[float] = []
    p2_surface_elos: list[float] = []
    win_probs: list[float] = []

    for i in range(len(df)):
        row_date = dates.iloc[i]
        p1_id = int(df["p1_id"].iloc[i])
        p2_id = int(df["p2_id"].iloc[i])
        winner = int(df["winner"].iloc[i])
        surface = str(df["surface"].iloc[i]) if pd.notna(df["surface"].iloc[i]) else "Unknown"
        score = df["score"].iloc[i] if "score" in df.columns else ""

        # ---- RECORD PRE-MATCH RATINGS (leak-free snapshot) ----
        r1 = state.ratings.get(p1_id, BASE_RATING)
        r2 = state.ratings.get(p2_id, BASE_RATING)
        s1 = state.surface.get((p1_id, surface), r1)
        s2 = state.surface.get((p2_id, surface), r2)

        p1_elos.append(r1)
        p2_elos.append(r2)
        p1_surface_elos.append(s1)
        p2_surface_elos.append(s2)

        # Blended win probability (pre-match)
        diff = (1.0 - SURFACE_BLEND) * (r1 - r2) + SURFACE_BLEND * (s1 - s2)
        win_probs.append(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))

        # ---- UPDATE RATINGS (post-match) ----
        if _is_walkover(score):
            state.last_date = row_date
            continue

        c1 = state.counts.get(p1_id, 0)
        c2 = state.counts.get(p2_id, 0)
        sc1 = state.surface_counts.get((p1_id, surface), 0)
        sc2 = state.surface_counts.get((p2_id, surface), 0)

        actual1 = 1.0 if winner == 1 else 0.0
        actual2 = 1.0 - actual1

        exp1 = _expected(r1, r2)
        exp2 = 1.0 - exp1
        k1 = _k(c1)
        k2 = _k(c2)
        sk1 = _k(sc1)
        sk2 = _k(sc2)

        state.ratings[p1_id] = r1 + k1 * (actual1 - exp1)
        state.ratings[p2_id] = r2 + k2 * (actual2 - exp2)

        exp_s1 = _expected(s1, s2)
        exp_s2 = 1.0 - exp_s1
        state.surface[(p1_id, surface)] = s1 + sk1 * (actual1 - exp_s1)
        state.surface[(p2_id, surface)] = s2 + sk2 * (actual2 - exp_s2)

        state.counts[p1_id] = c1 + 1
        state.counts[p2_id] = c2 + 1
        state.surface_counts[(p1_id, surface)] = sc1 + 1
        state.surface_counts[(p2_id, surface)] = sc2 + 1

        state.last_date = row_date
        state.n_processed += 1

    out = df.copy()
    out["p1_elo"] = p1_elos
    out["p2_elo"] = p2_elos
    out["p1_surface_elo"] = p1_surface_elos
    out["p2_surface_elo"] = p2_surface_elos
    out["win_prob_p1"] = win_probs
    return out


def elo_state_asof(matches_df: pd.DataFrame, date: dt.date) -> EloState:
    """Return the Elo rating table using only matches strictly before ``date``.

    Equivalent to ``replay(matches_df, until=date)`` — alias kept for the
    adapter API contract described in SECOND_DOMAIN_PROOF.md §3.2.

    Truncation-invariance guarantee:
        ``elo_state_asof(full_df, D)`` is **bitwise-identical** to the EloState
        you would obtain by replaying only the subset of rows with ``date < D``
        through a fresh ``replay()`` call.  Both paths execute the same sorted
        iteration in the same order — identical float operations ⇒ identical bits.
    """
    return replay(matches_df, until=date)


def replay_with_snapshots(
    matches: pd.DataFrame,
    snapshot_dates: list[dt.date],
) -> dict[dt.date, EloState]:
    """Replay matches once and capture EloState snapshots at each requested date.

    Each snapshot is taken at the moment the cursor first encounters a match
    with ``date >= snapshot_date`` — i.e. the state built from all strictly-prior
    matches, which is exactly ``replay(matches, until=snapshot_date)``.

    Parameters
    ----------
    matches:
        Input match DataFrame (same schema as ``walk_forward_elo``).
    snapshot_dates:
        List of dates at which to capture state.

    Returns
    -------
    dict mapping each requested date → EloState snapshot at that date.
    """
    df = _sorted(matches)
    dates_col = pd.to_datetime(df["date"]).dt.date

    remaining = sorted(snapshot_dates)
    snapshots: dict[dt.date, EloState] = {}
    state = EloState()

    def _copy_state(s: EloState) -> EloState:
        return EloState(
            ratings=dict(s.ratings),
            surface=dict(s.surface),
            counts=dict(s.counts),
            surface_counts=dict(s.surface_counts),
            last_date=s.last_date,
            n_processed=s.n_processed,
        )

    for i in range(len(df)):
        row_date = dates_col.iloc[i]

        # Capture snapshots for all requested dates that have been reached
        while remaining and row_date >= remaining[0]:
            snap_date = remaining.pop(0)
            snapshots[snap_date] = _copy_state(state)

        if not remaining:
            # Process remaining rows to ensure all snapshots are captured;
            # but since there are no more snapshots needed, we can break.
            break

        p1_id = int(df["p1_id"].iloc[i])
        p2_id = int(df["p2_id"].iloc[i])
        winner = int(df["winner"].iloc[i])
        surface = str(df["surface"].iloc[i]) if pd.notna(df["surface"].iloc[i]) else "Unknown"
        score = df["score"].iloc[i] if "score" in df.columns else ""

        if _is_walkover(score):
            state.last_date = row_date
            continue

        r1 = state.ratings.get(p1_id, BASE_RATING)
        r2 = state.ratings.get(p2_id, BASE_RATING)
        s1 = state.surface.get((p1_id, surface), r1)
        s2 = state.surface.get((p2_id, surface), r2)
        c1 = state.counts.get(p1_id, 0)
        c2 = state.counts.get(p2_id, 0)
        sc1 = state.surface_counts.get((p1_id, surface), 0)
        sc2 = state.surface_counts.get((p2_id, surface), 0)

        actual1 = 1.0 if winner == 1 else 0.0
        actual2 = 1.0 - actual1
        exp1 = _expected(r1, r2)
        exp2 = 1.0 - exp1
        k1 = _k(c1)
        k2 = _k(c2)
        sk1 = _k(sc1)
        sk2 = _k(sc2)

        state.ratings[p1_id] = r1 + k1 * (actual1 - exp1)
        state.ratings[p2_id] = r2 + k2 * (actual2 - exp2)

        exp_s1 = _expected(s1, s2)
        exp_s2 = 1.0 - exp_s1
        state.surface[(p1_id, surface)] = s1 + sk1 * (actual1 - exp_s1)
        state.surface[(p2_id, surface)] = s2 + sk2 * (actual2 - exp_s2)

        state.counts[p1_id] = c1 + 1
        state.counts[p2_id] = c2 + 1
        state.surface_counts[(p1_id, surface)] = sc1 + 1
        state.surface_counts[(p2_id, surface)] = sc2 + 1

        state.last_date = row_date
        state.n_processed += 1

    # Capture any remaining snapshots that fall after all matches
    for snap_date in remaining:
        snapshots[snap_date] = _copy_state(state)

    return snapshots
