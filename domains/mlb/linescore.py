"""domains.mlb.linescore — Robust parser for MLB per-inning run strings.

Parses comma-delimited 9-inning line-score strings stored in
data/domains/mlb/pitchers.parquet (home_innings / away_innings).
Each token is an integer run count OR:
  - 'x'  : home half of 9th (or earlier) not played (walk-off win)
  - '-'  : suspended/incomplete inning — treated as 0
  - '-1' / '-1.0' : data artifact for unplayed innings — treated as 0
  - float strings like '2.0' : rounded to int

HONEST: DESCRIPTIVE only. These are realized outcomes, not predictions.
No edge claimed; postmortem.py documents the leak tier explicitly.

Public API
----------
parse_innings(s) -> tuple[list[int], int]
    Returns (runs_per_inning, n_played) where 'x' and sentinel values
    contribute 0 runs and n_played counts non-'x' frames.

innings_shape(s) -> dict
    Returns the full shape descriptor dict used by postmortem.py.

INVARIANTS: <=300 LOC; no file I/O; no external state.
"""
from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Token parser
# ---------------------------------------------------------------------------

def _token_to_int(tok: str) -> Optional[int]:
    """Convert a single innings token to an integer run count.

    Returns None for 'x' (home half not played).
    Returns 0 for '-', '-1', '-1.0' and similar sentinels.
    Returns the integer value for digits and float strings like '2.0'.
    """
    tok = tok.strip()
    if not tok:
        return 0  # blank token treated as scoreless
    if tok.lower() == "x":
        return None  # unplayed half-inning
    # Handle negative or known sentinel values
    try:
        val = float(tok)
        if val < 0:
            return 0  # -1, -1.0 → data artifact, treat as 0
        return int(round(val))
    except ValueError:
        # '-' or other non-numeric junk → treat as 0
        return 0


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_innings(s: Optional[str]) -> tuple[list[int], int]:
    """Parse a comma-delimited innings string into a run array.

    Parameters
    ----------
    s:
        Raw innings string, e.g. "0,1,0,2,0,0,0,0,x" or
        "1.0,0.0,2,0,1,0,0,1,x".  May be None or empty.

    Returns
    -------
    runs : list[int]
        Per-inning run count, length == number of tokens (max 9).
        Tokens of 'x' contribute 0 runs.
    n_played : int
        Number of innings actually played (i.e. non-'x' tokens).
    """
    if not isinstance(s, str) or not s.strip():
        return [], 0

    parts = s.split(",")
    runs: list[int] = []
    n_played = 0

    for tok in parts:
        val = _token_to_int(tok)
        if val is None:
            # 'x' → inning not played; contribute 0 to array, don't count
            runs.append(0)
        else:
            runs.append(val)
            n_played += 1

    return runs, n_played


# ---------------------------------------------------------------------------
# Shape descriptor
# ---------------------------------------------------------------------------

def innings_shape(s: Optional[str]) -> dict:
    """Compute SHAPE fields from a raw innings string.

    Parameters
    ----------
    s:
        Raw innings string from pitchers.parquet.

    Returns
    -------
    dict with keys:
        runs_array          : list[int] of length up to 9
        total_runs          : int   (sum of all played innings)
        biggest_inning_runs : int   (max in any single played inning)
        biggest_inning_idx  : int | None  (1-indexed; None if no played innings)
        big_inning_share    : float (biggest / total; 0.0 if total == 0)
        scoreless_frame_rate: float (fraction of played innings with 0 runs)
        runs_1_3            : int   (innings 1-3, early / SP)
        runs_4_6            : int   (innings 4-6, mid / SP fatigue)
        runs_7_9            : int   (innings 7-9, late / bullpen)
    """
    runs, n_played = parse_innings(s)

    if n_played == 0:
        return {
            "runs_array": runs,
            "total_runs": 0,
            "biggest_inning_runs": 0,
            "biggest_inning_idx": None,
            "big_inning_share": 0.0,
            "scoreless_frame_rate": 0.0,
            "runs_1_3": 0,
            "runs_4_6": 0,
            "runs_7_9": 0,
        }

    total = sum(runs)

    # biggest inning: only among PLAYED frames; 'x' tokens map to runs[i]=0
    # but we shouldn't reward a zero from an unplayed inning as "biggest"
    # Re-parse to track which positions are 'x'
    played_mask = _played_mask(s, len(runs))

    # Identify max among played innings
    played_runs = [runs[i] for i in range(len(runs)) if played_mask[i]]
    biggest = max(played_runs) if played_runs else 0

    # First occurrence of max (1-indexed, among played innings)
    biggest_idx: Optional[int] = None
    for i in range(len(runs)):
        if played_mask[i] and runs[i] == biggest:
            biggest_idx = i + 1
            break

    big_share = (biggest / total) if total > 0 else 0.0

    scoreless = sum(1 for i in range(len(runs)) if played_mask[i] and runs[i] == 0)
    scoreless_rate = scoreless / n_played if n_played > 0 else 0.0

    # Segment sums (pad to 9 with zeros for short innings)
    padded = (runs + [0] * 9)[:9]
    runs_1_3 = sum(padded[0:3])
    runs_4_6 = sum(padded[3:6])
    runs_7_9 = sum(padded[6:9])

    return {
        "runs_array": runs,
        "total_runs": total,
        "biggest_inning_runs": biggest,
        "biggest_inning_idx": biggest_idx,
        "big_inning_share": big_share,
        "scoreless_frame_rate": scoreless_rate,
        "runs_1_3": runs_1_3,
        "runs_4_6": runs_4_6,
        "runs_7_9": runs_7_9,
    }


def _played_mask(s: Optional[str], n: int) -> list[bool]:
    """Return a boolean mask of length n: True if inning was played."""
    if not isinstance(s, str) or not s.strip():
        return [True] * n
    parts = s.split(",")
    mask: list[bool] = []
    for tok in parts[:n]:
        mask.append(tok.strip().lower() != "x")
    # Pad if needed
    while len(mask) < n:
        mask.append(True)
    return mask
