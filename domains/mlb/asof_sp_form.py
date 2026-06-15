"""domains.mlb.asof_sp_form — leak-free EW first-6-innings SP form feature.

Improvement over asof_features.py (career-mean + full-game runs, proven zero OOS lift):
  * Exponential-weighted (alpha=0.35) trailing first-6-innings runs allowed — recency-
    weighted so in-season decline / hot streaks count more than season-one starts.
  * First-6 isolation strips bullpen innings, removing the biggest confound in the
    career-mean proxy.

Runs-allowed convention (mirrors asof_features.py):
  home SP pitches *to* the away lineup → home SP's runs allowed = first6(away_innings)
  away SP pitches *to* the home lineup → away SP's runs allowed = first6(home_innings)

Output columns (per event_id):
  home_sp_first6_ew       — EW trailing first-6 RA for home SP (NaN < 3 prior starts)
  away_sp_first6_ew       — EW trailing first-6 RA for away SP (NaN < 3 prior starts)
  sp_first6_diff_ew       — away_sp_first6_ew - home_sp_first6_ew
                            positive → home SP historically allowed fewer runs (home edge)
  home_sp_starts_prior    — count of prior starts used (int32)
  away_sp_starts_prior    — count of prior starts used (int32)
  home_sp_hand            — "R" / "L" / "" parsed from trailing -R/-L suffix
  away_sp_hand            — "R" / "L" / "" parsed from trailing -R/-L suffix

LEAK CONTRACT: snapshot-before-update. The current game's RA goes into history ONLY
after the pre-game feature is recorded. No future information contaminates any feature.
NaN emitted when a pitcher has fewer than MIN_PRIOR_STARTS (=3) prior starts, so the
logistic calibration only runs on games where we have real signal.

PURE pandas/numpy. No src.* / kernel.* / other-domain imports.
PRIVATE: never tracked on the public repo.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

EW_ALPHA: float = 0.35          # exponential weight decay per additional prior start
MIN_PRIOR_STARTS: int = 3       # min starts before we emit a non-NaN feature
MAX_FIRST6_INNINGS: int = 6     # number of innings to sum from the line-score string

# ---------------------------------------------------------------------------
# Column contracts
# ---------------------------------------------------------------------------

_PITCHER_COLS = (
    "event_id", "date", "home_sp_name", "away_sp_name",
    "home_sp_present", "away_sp_present",
    "home_innings", "away_innings",
)
OUT_COLS = (
    "event_id",
    "home_sp_first6_ew", "away_sp_first6_ew", "sp_first6_diff_ew",
    "home_sp_starts_prior", "away_sp_starts_prior",
    "home_sp_hand", "away_sp_hand",
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _parse_hand(sp_name: object) -> str:
    """Extract handedness suffix: 'R', 'L', or '' if absent/unknown."""
    if sp_name is None or (isinstance(sp_name, float) and math.isnan(sp_name)):
        return ""
    s = str(sp_name).strip()
    if s.endswith("-R"):
        return "R"
    if s.endswith("-L"):
        return "L"
    return ""


def _parse_first6(innings_str: object) -> Optional[float]:
    """Sum the first MAX_FIRST6_INNINGS numeric entries in a comma-joined line-score.

    'x' (home-team half-inning not played) and non-numeric tokens are skipped.
    Returns None if the string is missing/null or no numeric tokens were found.
    """
    if innings_str is None or (isinstance(innings_str, float) and math.isnan(innings_str)):
        return None
    tokens = str(innings_str).split(",")
    total = 0.0
    count = 0
    for t in tokens:
        t = t.strip()
        if t.lower() == "x" or t == "":
            continue
        try:
            total += float(t)
            count += 1
        except ValueError:
            continue
        if count >= MAX_FIRST6_INNINGS:
            break
    return total if count > 0 else None


# ---------------------------------------------------------------------------
# EW state: one dict per pitcher
# ---------------------------------------------------------------------------

class _EWState:
    """Exponential-weighted trailing first-6-innings runs-allowed tracker.

    Maintains the EW running mean using the online update rule:
      ew_new = (1 - alpha) * ew_old + alpha * new_value   (alpha nearest-first)
    which weights the most recent start most heavily.

    State: (ew_value, n_starts)
    """

    __slots__ = ("_ew", "_n")

    def __init__(self) -> None:
        self._ew: Optional[float] = None
        self._n: int = 0

    @property
    def n(self) -> int:
        return self._n

    def snapshot(self) -> Tuple[float, int]:
        """Return (ew_value_or_nan, n_starts) for the pre-game snapshot."""
        if self._n < MIN_PRIOR_STARTS or self._ew is None:
            return float("nan"), self._n
        return self._ew, self._n

    def update(self, ra: float) -> None:
        """Incorporate one new runs-allowed observation AFTER the snapshot."""
        if self._ew is None:
            self._ew = ra          # first observation: initialise exactly
        else:
            self._ew = (1.0 - EW_ALPHA) * self._ew + EW_ALPHA * ra
        self._n += 1


# ---------------------------------------------------------------------------
# Sort helper (mirrors asof_features._sorted)
# ---------------------------------------------------------------------------

def _sorted_df(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological (date, home_team, away_team, event_id) mergesort-stable order."""
    sort_df = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).values,
            "k1": df["home_team"].astype(str).values if "home_team" in df.columns else [""] * len(df),
            "k2": df["away_team"].astype(str).values if "away_team" in df.columns else [""] * len(df),
            "k3": df["event_id"].astype(str).values,
        },
        index=df.index,
    )
    order = sort_df.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_sp_form_features(
    pitchers: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Return a DataFrame of leak-free EW first-6-innings SP form, one row per event_id.

    Everything derives from the *pitchers* corpus alone: the per-inning line-score
    strings (home_innings / away_innings) carry all the first-6 runs-allowed signal,
    so no game-level final-score data is needed.

    Parameters
    ----------
    pitchers : optional DataFrame; falls back to the default pitchers.parquet corpus.
    games    : currently UNUSED. Retained only for backward-compatible call signatures
               (callers historically passed games=); it is accepted and ignored. No
               game-level columns are read or validated.

    Walk-forward, snapshot-before-update (see module docstring).

    Returns
    -------
    pd.DataFrame with columns OUT_COLS (see top of module).
    """
    pit_path = _REPO_ROOT / "data/domains/mlb/pitchers.parquet"

    pf = pitchers.copy() if isinstance(pitchers, pd.DataFrame) else pd.read_parquet(str(pit_path))

    # Validate columns (pitchers only — `games` is unused, so nothing is read from it).
    for col in _PITCHER_COLS:
        if col not in pf.columns:
            raise KeyError(f"pitchers DataFrame missing column: {col!r}")

    # All computation runs off the pitchers corpus: the per-inning line-score strings
    # (home_innings / away_innings) supply the first-6 runs-allowed signal.
    df = _sorted_df(pf)

    # Per-pitcher EW state
    states: Dict[str, _EWState] = {}

    eids: List[str] = []
    h_ew: List[float] = []
    a_ew: List[float] = []
    h_n: List[int] = []
    a_n: List[int] = []
    h_hand: List[str] = []
    a_hand: List[str] = []

    for i in range(len(df)):
        row = df.iloc[i]
        eid = row["event_id"]
        h_name = row["home_sp_name"]
        a_name = row["away_sp_name"]
        h_present = bool(row["home_sp_present"])
        a_present = bool(row["away_sp_present"])
        home_innings_str = row["home_innings"]
        away_innings_str = row["away_innings"]

        # Handedness (parsed from name suffix; not present-gated — stable even if SP absent)
        h_hand.append(_parse_hand(h_name))
        a_hand.append(_parse_hand(a_name))

        # Normalise pitcher name for history key (strip handedness suffix)
        def _key(name: object) -> Optional[str]:
            if name is None or (isinstance(name, float) and math.isnan(name)):
                return None
            return str(name).strip()

        h_key = _key(h_name) if h_present else None
        a_key = _key(a_name) if a_present else None

        # --- SNAPSHOT (pre-game) ---
        if h_key is not None:
            st = states.setdefault(h_key, _EWState())
            hv, hn = st.snapshot()
        else:
            hv, hn = float("nan"), 0

        if a_key is not None:
            st = states.setdefault(a_key, _EWState())
            av, an = st.snapshot()
        else:
            av, an = float("nan"), 0

        eids.append(str(eid))
        h_ew.append(hv)
        a_ew.append(av)
        h_n.append(hn)
        a_n.append(an)

        # --- UPDATE (post-snapshot) ---
        # home SP faces away batters → RA = first6(away_innings)
        # away SP faces home batters → RA = first6(home_innings)
        home_ra = _parse_first6(away_innings_str)
        away_ra = _parse_first6(home_innings_str)

        if h_key is not None and home_ra is not None:
            states[h_key].update(home_ra)

        if a_key is not None and away_ra is not None:
            states[a_key].update(away_ra)

    h_ew_arr = np.array(h_ew, dtype=float)
    a_ew_arr = np.array(a_ew, dtype=float)
    diff_arr = np.where(
        np.isnan(h_ew_arr) | np.isnan(a_ew_arr),
        float("nan"),
        a_ew_arr - h_ew_arr,
    )

    return pd.DataFrame(
        {
            "event_id": eids,
            "home_sp_first6_ew": h_ew_arr,
            "away_sp_first6_ew": a_ew_arr,
            "sp_first6_diff_ew": diff_arr,
            "home_sp_starts_prior": np.array(h_n, dtype="int32"),
            "away_sp_starts_prior": np.array(a_n, dtype="int32"),
            "home_sp_hand": h_hand,
            "away_sp_hand": a_hand,
        }
    )[list(OUT_COLS)]

