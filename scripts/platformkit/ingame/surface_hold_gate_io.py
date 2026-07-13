"""scripts.platformkit.ingame.surface_hold_gate_io -- IO + prior-derivation helpers
for the tennis SURFACE-HOLD in-game DETAIL-LAYER gate (companion to
surface_hold_gate.py). Mirrors ingame_layer_gate_nba_io.py's split so each file
stays <=300 LOC.

THE TWO PRIORS being compared (both derived from data/domains/tennis/asof_hold*.parquet,
never re-fit here -- pure as-of lookups, already leak-free by construction upstream):
  BASE prior    = surface-BLIND  p1/p2_hold_pct_asof            (pools all surfaces)
  CANDIDATE     = surface-SPECIFIC p1/p2_hold_pct_{surface}_asof (Hard/Clay/Grass only;
                  Carpet/Unknown rows have no specific column -> excluded, not imputed)

Both priors are converted hold_pct_diff -> a probability via the SAME fixed logistic
squash (a hold-pct differential is not itself a 0..1 win prob), so the ONLY thing that
differs between BASE and CANDIDATE is which hold-pct column feeds the squash. This
isolates the surface-specificity question cleanly (H1's stated conditioning variable).

Reads (read-only, never mutated):
  data/cache/ingame/tennis_states__{atp,wta}.parquet  -- leak-free in-game states
  data/domains/tennis/asof_hold.parquet                -- ATP hold% (surface-blind + split)
  data/domains/tennis/asof_hold_wta.parquet            -- WTA hold% (surface-blind + split)

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

STATES = {
    "atp": os.path.join(_REPO, "data", "cache", "ingame", "tennis_states__atp.parquet"),
    "wta": os.path.join(_REPO, "data", "cache", "ingame", "tennis_states__wta.parquet"),
}
ASOF_HOLD = {
    "atp": os.path.join(_REPO, "data", "domains", "tennis", "asof_hold.parquet"),
    "wta": os.path.join(_REPO, "data", "domains", "tennis", "asof_hold_wta.parquet"),
}
OUT = os.path.join(_REPO, "data", "domains", "tennis", "surface_hold_gate_verdict.json")

_SURF_COL = {"Hard": "hard", "Clay": "clay", "Grass": "grass"}
MIN_STATES_PER_SURFACE_CELL = 100  # spec floor; Grass (3228 matches) is tightest

# The shared fit_weight_surface/WeightSurface (eval_gate.ingame_blend) hardcodes NBA
# scales: time_bucket assumes seconds_remaining in [0, 2880]; margin_bucket assumes
# score_diff edges (-12,-4,4,12) (NBA point-margins). Tennis state_diff (games/sets
# differential) only spans roughly [-2.8, 2.8], so passed through unscaled it would
# collapse into a single bucket (verified: real corpus run before this rescale put
# 100% of ATP states in one (time,margin) cell). Rescale onto the SAME NBA-shaped
# axes the shared bucketing code expects, rather than editing that shared, reused
# module. Both arms (blind/surface) see the identically-rescaled axes, so this is a
# units fix, not a hidden thumb on the scale.
_MARGIN_SCALE = 4.0     # state_diff * 4 spans roughly [-11, 11] -- inside NBA edges
_REG_SEC = 2880.0       # pseudo-regulation-seconds so frac_elapsed round-trips exactly


def _hold_diff_to_prob(diff: float, k: float = 4.0) -> float:
    """Fixed logistic squash: hold_pct differential (roughly [-1,1]) -> P(p1).

    k=4.0 is a fixed, never-fit constant (not tuned on outcomes) so this stays a
    genuine PRIOR, not a second model secretly fit on the test data.
    """
    return float(1.0 / (1.0 + np.exp(-k * float(diff))))


def load_hold(tour: str) -> pd.DataFrame:
    """Load the as-of hold% parquet for one tour ('atp' or 'wta')."""
    return pd.read_parquet(ASOF_HOLD[tour])


def load_states(tour: str) -> pd.DataFrame:
    """Load the leak-free in-game states parquet for one tour, date-sorted."""
    df = pd.read_parquet(STATES[tour])
    df = df.copy()
    df["_date"] = pd.to_datetime(df["game_id"].str[:8], format="%Y%m%d", errors="coerce")
    return df.sort_values(["_date", "game_id"]).reset_index(drop=True)


def build_priors(tour: str) -> pd.DataFrame:
    """Per-match (event_id) frame: p0_blind (surface-blind hold prior), p0_surface
    (surface-specific hold prior), and a coverage flag `_cov` (both players have a
    non-null column for the row's own surface AND that surface is one of
    Hard/Clay/Grass -- Carpet/Unknown rows are excluded, never imputed).
    """
    h = load_hold(tour)
    out = h[["event_id", "surface", "p1_hold_pct_asof", "p2_hold_pct_asof"]].copy()
    blind_diff = out["p1_hold_pct_asof"] - out["p2_hold_pct_asof"]
    out["p0_blind"] = blind_diff.apply(
        lambda d: _hold_diff_to_prob(d) if pd.notna(d) else np.nan)

    p1_spec = np.full(len(out), np.nan)
    p2_spec = np.full(len(out), np.nan)
    for surf, col in _SURF_COL.items():
        m = (h["surface"] == surf).to_numpy()
        p1_spec[m] = h.loc[m, f"p1_hold_pct_{col}_asof"].to_numpy()
        p2_spec[m] = h.loc[m, f"p2_hold_pct_{col}_asof"].to_numpy()
    spec_diff = p1_spec - p2_spec
    out["p0_surface"] = [
        _hold_diff_to_prob(d) if not np.isnan(d) else np.nan for d in spec_diff
    ]
    out["_cov"] = (
        out["surface"].isin(list(_SURF_COL.keys()))
        & out["p0_blind"].notna()
        & out["p0_surface"].notna()
    )
    return out[["event_id", "surface", "p0_blind", "p0_surface", "_cov"]]


def states_with_priors(tour: str) -> List[dict]:
    """Merge leak-free in-game states with both priors; keep covered rows only.

    Each output dict carries the keys the shared blend/gate machinery expects
    (p0, p_live, seconds_remaining, score_diff, outcome, game_id) TWICE -- once
    under the *_blind suffix (BASE arm) and once under *_surface (CANDIDATE arm)
    -- so the caller can run the identical fit/predict pipeline on each arm.
    """
    states = load_states(tour)
    priors = build_priors(tour).drop(columns=["surface"])
    merged = states.merge(priors, left_on="game_id", right_on="event_id", how="inner")
    merged = merged[merged["_cov"]].reset_index(drop=True)

    out: List[dict] = []
    for _, r in merged.iterrows():
        frac = float(r["frac_elapsed"])
        diff = float(r["state_diff"])
        p_live = _p_live(diff, frac)  # BASE model uses the TRUE (unscaled) state_diff
        out.append({
            "game_id": r["game_id"], "surface": r["surface"],
            # rescaled onto NBA-shaped axes for the shared bucketing code ONLY
            # (see _MARGIN_SCALE/_REG_SEC note above); p_live/outcome are unaffected.
            "seconds_remaining": (1.0 - frac) * _REG_SEC,
            "score_diff": diff * _MARGIN_SCALE,
            "outcome": int(r["outcome"]), "p_live": p_live,
            "p0_blind": float(r["p0_blind"]), "p0_surface": float(r["p0_surface"]),
        })
    return out


# base_slope from data/cache/ingame/models/tennis_ingame.json (a=0, b=2.71985692);
# frozen constant, not re-fit here -- the gate compares PRIORS, not the base model.
_BASE_A, _BASE_B = 0.0, 2.71985692


def _p_live(state_diff: float, frac_elapsed: float) -> float:
    """BASE in-game model: sigmoid((a+b*frac_elapsed)*state_diff). Mirrors the
    frozen tennis_ingame.json base_model -- no team/surface prior."""
    z = (_BASE_A + _BASE_B * frac_elapsed) * state_diff
    return float(1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0))))


def chronological_game_order(states: List[dict]) -> List[str]:
    """Distinct game_ids in first-appearance order (states list is already
    date-sorted upstream by load_states)."""
    seen: Dict[str, None] = {}
    for s in states:
        seen.setdefault(s["game_id"], None)
    return list(seen.keys())
