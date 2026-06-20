"""domains.mlb.statcast_sp_fatigue_adapter -- re-key the leak-free SP-fatigue/velo
PROFILE -> NEXT-START K-prop frame onto the REAL Statcast starter_table (which now
carries a true per-start pitcher_id + an SP-isolated per-start K LABEL), unblocking
the two INSUFFICIENT_DATA reasons of ingest_sp_fatigue_prop_states:
  NO_SEASON_OVERLAP  (the old K source player_gamelogs.parquet was 2026-only), and
  NO_SP_IDENTITY     (the ESPN pitch parquet had no pitcher id / no SP boundary).

INPUT  : data/cache/statcast/starter_table__<season>.parquet -- one row per
         (game_id, pitch_side, STARTER) with: pitcher (real id), label_k (SP-isolated
         per-start strikeout total, target ONLY), and per-start WITHIN-outing shape
         columns (n_pitches, mean_early_velo, velo_decline_slope, mean_spin,
         pitch_mix_entropy, frac_breaking) built from that outing's pitches only.

OUTPUT : a gate-ready frame with, per start (leak-free, keyed by the REAL pitcher):
  - prof_<col> : prior-N (shift1) rolling mean of the pitcher's PRIOR starts' shape
                 columns -- start N's OWN outing is shifted out, so start N never sees
                 itself. Rows with <1 prior get NaN (NOT 0-filled).
  - base_recent_k_rate : prior-N (shift1) rolling mean of label_k -- the honest BASE
                 to beat; excludes start N's own K. NaN on debut (never a 0-fill win).
  - label_k    : the per-start K total (TARGET only, never a feature).
  - prof_planted_null : pure-noise column (the gate MUST reject it).
  - cluster keys: pitcher (the DM cluster), date/game_id (walk-forward order),
                 pitch_team/pitch_side (carried for back-compat with the existing gate's
                 clustered_dm; the K-prop wrapper clusters by PITCHER per the spec).

LEAK-FREENESS: profile + base are shift1 prior-N over the pitcher's earlier starts;
the K LABEL is target-only; no season-final aggregate is merged onto a per-start row;
the close is never a feature. Two INDEPENDENT seasons (2022, 2023) are loaded
separately as the cross-corpus pair.

PROPOSAL-ONLY: reads only data/cache/ (the data store); writes NOTHING to
data/registry/, flips NO flag, no $/ROI/edge field. ASCII only. <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_STATCAST_DIR = _REPO / "data" / "cache" / "statcast"

# Per-start WITHIN-outing shape columns present in the starter_table; the prior-N
# profile is the shift1 rolling mean of these over the pitcher's earlier starts.
_SHAPE_COLS = ("mean_early_velo", "velo_decline_slope", "pitch_mix_entropy",
               "frac_breaking", "n_pitches", "mean_spin")
_PROFILE_FEATS = tuple(f"prof_{c}" for c in _SHAPE_COLS)
_NULL_FEAT = "prof_planted_null"
_LABEL_COL = "label_k"
_BASE_COL = "base_recent_k_rate"
_PRIOR_N = 3
_SEASONS = (2022, 2023)


def starter_table_path(season: int) -> Path:
    return _STATCAST_DIR / f"starter_table__{season}.parquet"


def _prior_n_by_pitcher(df: pd.DataFrame, cols: Tuple[str, ...],
                        prior_n: int = _PRIOR_N) -> pd.DataFrame:
    """shift1 rolling-mean of `cols` over each PITCHER's PRIOR `prior_n` starts.

    Sorted by (pitcher, date, game_id) so a start sees ONLY that pitcher's earlier
    starts; the current start's own values are shifted out (leak-free). Debut rows
    (no prior) become NaN -- never 0-filled.
    """
    d = df.sort_values(["pitcher", "date", "game_id"]).copy()
    g = d.groupby("pitcher", sort=False)
    out = {}
    for c in cols:
        out[c] = g[c].apply(
            lambda s: s.shift(1).rolling(prior_n, min_periods=1).mean()
        ).reset_index(level=0, drop=True)
    for c in cols:
        d[c if c == _LABEL_COL else f"prof_{c}"] = out[c]
    d["prof_n_prior"] = g.cumcount().clip(upper=prior_n)
    return d


def build_frame(season: int, prior_n: int = _PRIOR_N, seed: int = 0,
                path: Optional[Path] = None) -> pd.DataFrame:
    """Load one season's starter_table -> leak-free gate-ready frame (empty if absent)."""
    fp = Path(path) if path else starter_table_path(season)
    if not fp.exists():
        return pd.DataFrame()
    st = pd.read_parquet(fp)
    if st.empty:
        return pd.DataFrame()
    # Build the prior-N profile (shape cols) keyed by the REAL pitcher.
    prof = _prior_n_by_pitcher(st, _SHAPE_COLS, prior_n=prior_n)
    # Recent-K-rate BASE: shift1 prior-N rolling mean of the K LABEL, by pitcher.
    bg = prof.sort_values(["pitcher", "date", "game_id"]).groupby("pitcher", sort=False)
    prof[_BASE_COL] = bg[_LABEL_COL].apply(
        lambda s: s.shift(1).rolling(prior_n, min_periods=1).mean()
    ).reset_index(level=0, drop=True)
    # Planted null: pure noise, outcome-independent -> the gate MUST reject it.
    rng = np.random.default_rng(seed + season)
    prof[_NULL_FEAT] = rng.standard_normal(len(prof))
    keep = (["season", "game_id", "date", "pitcher", "pitch_team", "pitch_side",
             _LABEL_COL, _BASE_COL, _NULL_FEAT, "prof_n_prior"]
            + list(_PROFILE_FEATS))
    keep = [c for c in keep if c in prof.columns]
    return prof[keep].sort_values(["date", "game_id"]).reset_index(drop=True)


def load_both(prior_n: int = _PRIOR_N, seed: int = 0
              ) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load the two INDEPENDENT corpora + a coverage dict. Empty frames if missing."""
    a = build_frame(_SEASONS[0], prior_n=prior_n, seed=seed)
    b = build_frame(_SEASONS[1], prior_n=prior_n, seed=seed)
    cov = {
        "seasons": list(_SEASONS),
        "n_starts": {_SEASONS[0]: int(len(a)), _SEASONS[1]: int(len(b))},
        "n_pitchers": {_SEASONS[0]: int(a["pitcher"].nunique()) if not a.empty else 0,
                       _SEASONS[1]: int(b["pitcher"].nunique()) if not b.empty else 0},
        "n_with_base": {
            _SEASONS[0]: int(a[_BASE_COL].notna().sum()) if not a.empty else 0,
            _SEASONS[1]: int(b[_BASE_COL].notna().sum()) if not b.empty else 0},
        "label_mean": {
            _SEASONS[0]: float(a[_LABEL_COL].mean()) if not a.empty else float("nan"),
            _SEASONS[1]: float(b[_LABEL_COL].mean()) if not b.empty else float("nan")},
    }
    return a, b, cov


def label_is_degenerate(df: pd.DataFrame) -> bool:
    """Guard: a near-constant K label cannot support a real over/under line."""
    if df.empty or _LABEL_COL not in df.columns:
        return True
    y = df[_LABEL_COL].to_numpy(dtype=float)
    y = y[np.isfinite(y)]
    return y.size < 20 or float(np.std(y)) < 1e-6 or len(np.unique(y)) < 3


__all__ = ["build_frame", "load_both", "label_is_degenerate", "starter_table_path",
           "_PROFILE_FEATS", "_NULL_FEAT", "_LABEL_COL", "_BASE_COL", "_SEASONS",
           "_SHAPE_COLS", "_PRIOR_N"]
