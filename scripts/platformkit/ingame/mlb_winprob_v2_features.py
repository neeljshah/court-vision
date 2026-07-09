"""scripts.platformkit.ingame.mlb_winprob_v2_features -- feature build for mlb_winprob_v2.

LOC-cap split of mlb_winprob_v2.py (train+eval orchestration stayed <=300 LOC only by
extracting the two feature builders here; zero behavior change). See mlb_winprob_v2.py's
docstring for the full design (split/features/dropped-features/honesty).

Two independent builders that MUST emit the same 8 columns (FEATURE_NAMES) from two very
different sources, or the model trained on one can't be scored on the other:
  _train_xy         : mlb_pitch_states__<season>.parquet columns -> X, y.
  _parse_tick_state : a live captured tick's `state_summary` string -> the same 8 fields.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; never
writes data/registry/; never flips a flag; pitch_states parquets READ-ONLY.

Per-file test: covered by test_mlb_winprob_v2.py (imports this module directly).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PITCH_STATES_DIR = _REPO_ROOT / "data" / "cache" / "ingame"
FORBIDDEN_TRAIN_SEASONS = {2026}  # forward-only test corpus; never fit/validate on it

FEATURE_NAMES: Tuple[str, ...] = (
    "inning", "half_bottom", "outs", "base_state", "balls", "strikes",
    "score_margin", "frac_elapsed",
)


def load_training_seasons(seasons: Sequence[int],
                          data_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, List[int]]:
    """Concat mlb_pitch_states__<yr>.parquet for the given seasons. Hard guard: raises if
    any FORBIDDEN_TRAIN_SEASONS year is requested (2026 = the forward-only test corpus).
    Missing season files are skipped and returned in `missing`, never fabricated."""
    bad = FORBIDDEN_TRAIN_SEASONS & set(seasons)
    if bad:
        raise ValueError("load_training_seasons: forbidden season(s) %s (test-only, "
                          "forward-only)" % sorted(bad))
    d = Path(data_dir) if data_dir is not None else DEFAULT_PITCH_STATES_DIR
    frames, missing = [], []
    for yr in seasons:
        p = d / ("mlb_pitch_states__%d.parquet" % yr)
        if not p.exists():
            missing.append(yr)
            continue
        frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame(), missing
    return pd.concat(frames, ignore_index=True), missing


def train_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, int]:
    """8-feature matrix + label from the training schema. Rows with an unparseable
    half_inning_label are dropped, counted, never guessed."""
    if df.empty:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros(0), 0
    half = df["half_inning_label"].astype(str).str.extract(r"^(top|bottom)(\d+)$")
    ok = half[1].notna()
    n_dropped = int((~ok).sum())
    d = df.loc[ok]
    half_bottom = (half.loc[ok, 0] == "bottom").astype(float).to_numpy()
    inning = half.loc[ok, 1].astype(float).to_numpy()
    X = np.column_stack([
        inning, half_bottom,
        d["outs"].astype(float).to_numpy(),
        d["runners"].astype(float).to_numpy(),
        d["count_balls"].astype(float).to_numpy(),
        d["count_strikes"].astype(float).to_numpy(),
        d["state_diff"].astype(float).to_numpy(),      # score_margin = home - away
        d["frac_elapsed"].astype(float).to_numpy(),
    ])
    y = d["outcome"].astype(float).to_numpy()
    return X, y, n_dropped


def parse_tick_state(state_summary: Any) -> Optional[Dict[str, float]]:
    """Tick state_summary -> 8 model features + raw score. None (dropped, never
    guessed) if a required field is missing (pre-deep-state capture)."""
    toks: Dict[str, str] = {}
    for t in str(state_summary or "").split():
        if "=" in t:
            k, _, v = t.partition("=")
            toks[k] = v
    try:
        home_score = float(toks["home_score"])
        away_score = float(toks["away_score"])
        inning = int(float(toks["inning"]))
        half = toks.get("half", "").lower()
        if half not in ("top", "bottom"):
            return None
        half_bottom = 1.0 if half == "bottom" else 0.0
        outs = float(toks["outs"])
        base_state = float(toks["base"])
        balls_s, strikes_s = toks["count"].split("-")
        balls, strikes = float(balls_s), float(strikes_s)
    except (KeyError, ValueError):
        return None
    frac = max(0.0, min(1.0, (2 * (inning - 1) + half_bottom) / 18.0))
    return {"inning": float(inning), "half_bottom": half_bottom, "outs": outs,
            "base_state": base_state, "balls": balls, "strikes": strikes,
            "score_margin": home_score - away_score, "frac_elapsed": frac,
            "home_score": home_score, "away_score": away_score}


__all__ = [
    "DEFAULT_PITCH_STATES_DIR", "FORBIDDEN_TRAIN_SEASONS", "FEATURE_NAMES",
    "load_training_seasons", "train_xy", "parse_tick_state",
]
