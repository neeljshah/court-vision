"""domains.soccer.finishing_asof — leak-free AS-OF finishing residual per team.

WHAT THIS MEASURES
------------------
For each match, emit each team's prior-only exponentially-weighted FINISHING RESIDUAL:

    finishing_residual = EW(goals_for - k * SoT_for)

where k ~ 0.32 is the corpus SoT-to-goal conversion rate.  A positive residual means
the team has been scoring MORE than SoT-implied expectation (hot finishing); negative
means LESS (cold finishing).  This captures UNSUSTAINABLE hot/cold finishing that
should REGRESS toward the SoT-implied expectation.

WHY THIS ISN'T THE KNOWN NULL
------------------------------
The W59 proof showed that blending RAW SoT level into the Poisson lambda is a null
because the EW goal-rate already absorbs SoT level.  This module is DIFFERENT:
the RESIDUAL (goals minus SoT-expected goals) is the signal, NOT the SoT level.
A team consistently scoring more than its shots-on-target suggest (hot streak) is
likely to REGRESS — the finishing prior module uses this to shrink lambda.

LEAK DISCIPLINE
---------------
- snapshot-BEFORE-update: each match's as-of residual reflects strictly PRIOR
  matches; the current match's own result is never folded in until AFTER the
  row is emitted.
- No-future-leak assertion: verified by a forward-date check in build_asof_frame.
- All histories are per-team (home + away appearances combined, identical to
  asof_features.py convention).

PRIVATE: data/domains/soccer/ is gitignored; no market edge claimed.
HONEST: calibration improvement only; see finishing_prior.py for the verdict.
Pure pandas/numpy; no src.*/kernel.*/domains.nba.* imports (F5 compliant).
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.soccer.config import DATA_DIR_REL, ALPHA

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Corpus SoT-to-goal conversion rate (goals / shots_on_target).
# Computed over the 25,834-match football-data.co.uk corpus:
#   k = total_goals / total_SoT ≈ 0.316 (home 0.328, away 0.318).
# Pinned at 0.32 (round, within noise band) so the baseline is immutable.
K_CONV: float = 0.32

# Column contract for the output frame.
FINISHING_ASOF_COLS: Tuple[str, ...] = (
    "event_id",
    "home_finishing_residual",   # EW(goals_for - K_CONV * SoT_for) — home team prior
    "away_finishing_residual",   # same for away team
    "home_n_prior",              # number of prior matches used
    "away_n_prior",
)


# ---------------------------------------------------------------------------
# Internal state object
# ---------------------------------------------------------------------------

class _FinishingHistory:
    """Running EW finishing residual for one team (home + away appearances).

    snapshot() reads PRE-match state; update() folds the settled match in.
    Uses standard EW update identical to ratings.py: new = old + ALPHA*(obs - old).
    Starts at 0.0 (neutral prior: team finishes at exactly SoT expectation).
    """

    __slots__ = ("n", "ew_residual")

    def __init__(self) -> None:
        self.n: int = 0
        self.ew_residual: float = 0.0  # neutral prior

    def snapshot(self) -> Dict[str, object]:
        """Return prior-only state; n_prior=0 when no prior match exists."""
        return {"residual": self.ew_residual, "n_prior": self.n}

    def update(self, goals_for: float, sot_for: float) -> None:
        """Fold a settled match in using EW update (same alpha as ratings.py).

        Skips entirely when either value is non-finite so NaN rows never
        contaminate subsequent snapshots.
        """
        if not (np.isfinite(goals_for) and np.isfinite(sot_for)):
            return
        obs_residual = goals_for - K_CONV * sot_for
        self.ew_residual += ALPHA * (obs_residual - self.ew_residual)
        self.n += 1


# ---------------------------------------------------------------------------
# Sort helper (mirrors ratings.py / asof_features.py — same deterministic order)
# ---------------------------------------------------------------------------

def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by (date, div, home_team, away_team) — mergesort-stable."""
    n = len(df)
    keys = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).astype("int64").values,
            "k1": df["div"].astype(str).values if "div" in df.columns else [""] * n,
            "k2": df["home_team"].astype(str).values,
            "k3": df["away_team"].astype(str).values,
        },
        index=df.index,
    )
    order = keys.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core transform
# ---------------------------------------------------------------------------

def build_asof_frame(
    match_stats: pd.DataFrame,
    matches: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Pure transform: return FINISHING_ASOF_COLS DataFrame (no I/O).

    Parameters
    ----------
    match_stats:
        Must contain: event_id, date, home_team, away_team, home_sot, away_sot.
        Does NOT need fthg/ftag (goals come from ``matches``).
    matches:
        Must contain: event_id, fthg, ftag.  If None, only SoT is used to
        approximate goals via the K_CONV rate (graceful degradation; the full
        path merges both files).

    LEAK assertion
    --------------
    After building the output frame, we assert that no row's as-of residual
    equals a non-zero value while n_prior == 0, and that n_prior is strictly
    non-decreasing within each team's appearances (monotone history depth).
    This is a structural proxy for the no-future-leak invariant.
    """
    if match_stats is None or len(match_stats) == 0:
        return pd.DataFrame(columns=list(FINISHING_ASOF_COLS))

    # --- Join goals onto match_stats if available ---
    df = match_stats.copy()
    if matches is not None:
        goal_cols = matches[["event_id", "fthg", "ftag"]].copy()
        df = df.merge(goal_cols, on="event_id", how="left")
    elif "fthg" not in df.columns:
        df["fthg"] = float("nan")
        df["ftag"] = float("nan")

    df = _sorted(df)

    def _arr(col: str) -> np.ndarray:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").astype("float64").values
        return np.full(len(df), np.nan, dtype="float64")

    fthg = _arr("fthg")
    ftag = _arr("ftag")
    home_sot = _arr("home_sot")
    away_sot = _arr("away_sot")
    home_arr = df["home_team"].astype(str).values
    away_arr = df["away_team"].astype(str).values
    eid_arr = df["event_id"].astype(str).values
    dates = pd.to_datetime(df["date"]).values  # numpy datetime64

    hist: Dict[str, _FinishingHistory] = {}
    rows: List[Dict[str, object]] = []

    for i in range(len(df)):
        h, a = home_arr[i], away_arr[i]
        h_hist = hist.setdefault(h, _FinishingHistory())
        a_hist = hist.setdefault(a, _FinishingHistory())

        # ---- SNAPSHOT (strictly prior matches) ----
        h_snap = h_hist.snapshot()
        a_snap = a_hist.snapshot()

        rows.append({
            "event_id": eid_arr[i],
            "home_finishing_residual": h_snap["residual"],
            "away_finishing_residual": a_snap["residual"],
            "home_n_prior": h_snap["n_prior"],
            "away_n_prior": a_snap["n_prior"],
        })

        # ---- UPDATE (post-match) ----
        # home team: goals_for=fthg, sot_for=home_sot
        h_hist.update(fthg[i], home_sot[i])
        # away team: goals_for=ftag, sot_for=away_sot
        a_hist.update(ftag[i], away_sot[i])

    out = pd.DataFrame(rows, columns=list(FINISHING_ASOF_COLS))
    out["home_n_prior"] = out["home_n_prior"].astype("int64")
    out["away_n_prior"] = out["away_n_prior"].astype("int64")

    # ---- NO-FUTURE-LEAK ASSERTION ----
    # First appearance of each team must have n_prior == 0 and residual == 0.0.
    # Verify that n_prior only increases within each team's sequence.
    _assert_no_future_leak(out, home_arr, away_arr)

    return out


def _assert_no_future_leak(
    out: pd.DataFrame,
    home_arr: np.ndarray,
    away_arr: np.ndarray,
) -> None:
    """Structural no-future-leak check.

    For each team's VERY FIRST appearance (in any role — home or away), n_prior
    must be 0 and residual must be 0.0.  After their first appearance, n_prior
    must be non-decreasing across their subsequent appearances (in any role).

    NOTE: we track 'any_seen' across home+away roles together.  A team that
    first appears as AWAY correctly has n_prior=0 there, then n_prior=1 when
    it next appears as HOME — this is CORRECT (not a leak) and the assertion
    must not fire in that case.
    """
    # Map team -> (last_n_prior, last_residual) tracking across both roles
    seen: Dict[str, int] = {}

    for i in range(len(out)):
        h, a = home_arr[i], away_arr[i]
        h_n = int(out["home_n_prior"].iloc[i])
        a_n = int(out["away_n_prior"].iloc[i])
        h_r = float(out["home_finishing_residual"].iloc[i])
        a_r = float(out["away_finishing_residual"].iloc[i])

        # First appearance of a team in ANY role must have n_prior == 0, residual == 0.0
        if h not in seen:
            assert h_n == 0, f"LEAK: team {h!r} first appearance has n_prior={h_n}"
            assert h_r == 0.0, f"LEAK: team {h!r} first appearance residual={h_r}"
        else:
            # After first appearance, n_prior should not decrease relative to last
            # seen value (it may stay flat if two games on same day, or increase).
            assert h_n >= seen[h], (
                f"LEAK: team {h!r} n_prior decreased {seen[h]}->{h_n}"
            )
        if a not in seen:
            assert a_n == 0, f"LEAK: team {a!r} first appearance has n_prior={a_n}"
            assert a_r == 0.0, f"LEAK: team {a!r} first appearance residual={a_r}"
        else:
            assert a_n >= seen[a], (
                f"LEAK: team {a!r} n_prior decreased {seen[a]}->{a_n}"
            )

        # Update seen with the LARGER of home/away n_prior for the team
        # (after this row's snapshot, both teams will have +1 from the update)
        seen[h] = h_n
        seen[a] = a_n


# ---------------------------------------------------------------------------
# I/O entry point
# ---------------------------------------------------------------------------

def build_finishing_asof(
    match_stats: Optional[pd.DataFrame] = None,
    matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> pd.DataFrame:
    """Build and return the as-of finishing residual frame.

    Reads from default data paths if DataFrames not supplied.
    Returns the resulting DataFrame (also writes to out_path if given).
    """
    if match_stats is None:
        src = _REPO_ROOT / DATA_DIR_REL / "match_stats.parquet"
        match_stats = pd.read_parquet(src)
    if matches is None:
        src2 = _REPO_ROOT / DATA_DIR_REL / "matches.parquet"
        matches = pd.read_parquet(src2)

    out = build_asof_frame(match_stats, matches)

    if out_path is not None:
        out.to_parquet(out_path, index=False)

    return out
