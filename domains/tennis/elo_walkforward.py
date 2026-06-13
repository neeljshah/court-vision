"""domains.tennis.elo_walkforward — walk-forward Elo layer for tennis.

Contains the heavier walk-forward functions that consume the core replay/prob
primitives from ``domains.tennis.elo_core``.  Split from elo.py for LOC-discipline
(≤300 LOC/file rule); elo.py re-exports everything so existing callers are unaffected.

PRIVATE: outputs are price-bearing or license-restricted when combined with odds.
F5-clean: stdlib + numpy/pandas + domains.tennis.* only.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from domains.tennis.elo_core import (
    BASE_RATING,
    EloState,
    SURFACE_BLEND,
    _expected,
    _is_walkover,
    _k,
    _sorted,
)

# ---------------------------------------------------------------------------
# Walk-forward Elo
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
    from domains.tennis.elo_core import replay
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
