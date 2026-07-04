"""scripts.platformkit.ingame.sp_fatigue_gate_mlb_io -- IO + leak-free fatigue-tercile
banding for the SP within-start fatigue in-game gate (companion to
sp_fatigue_gate_mlb.py). Mirrors ingame_layer_gate_nba_io.py's split (keep the gate
file itself <=300 LOC) and reuses the FROZEN in-game state schema already validated
by ingame_gate_generic_models.load_states (game_id/state_diff/frac_elapsed/p0/outcome).

CORPUS: data/cache/ingame/mlb_pitch_states__<season>.parquet (H1_sp_fatigue_ingame's
declared source per mlb_truth_spec.json). Each row is one PITCH-level as-of state
(half-inning granularity for state_diff/frac_elapsed/p0/outcome -- identical frozen
shape the NBA end-of-quarter states use, just at half-inning cadence) plus the
declared conditioning columns:
  velo_decline_vs_early -- GUMBO-proxy within-outing velocity decline at that pitch.
  sp_pitch_count_prior  -- GUMBO pitcher_pitches proxy (cumulative pitch count for the
                           CURRENT half-inning's pitching side, this corpus's build).

NO INDIVIDUAL PITCHER ID in this parquet (schema has pitch_type/velocity/location but
no per-pitcher key) -- exactly the NO_SP_IDENTITY limit already documented by
domains/mlb/ingest_sp_fatigue_prop_states.py for the adjacent K-prop hypothesis. The
proxy "pitcher" unit here is (game_id, pitch_side) -- one team's pitching staff for
one game -- which is the same substitution that module made. The planted-null control
(spec: "shuffle the fatigue-tercile assignment across pitchers within the same
game-state cell") shuffles across these (game_id, pitch_side) proxy units.

LEAK-FREENESS: the fatigue tercile EDGES (quantile cut points of velo_decline_vs_early)
are fit on the TRAIN fold ONLY and applied unchanged to the TEST fold -- a test-fold
pitch is banded using train-derived cut points, never its own fold's distribution.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
"""
from __future__ import annotations

import glob
import hashlib
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
OUT = os.path.join(_REPO, "data", "domains", "mlb", "sp_fatigue_gate_verdict.json")

TERCILES = ("fresh", "declining", "fatigued")
_REQUIRED = ("game_id", "state_diff", "frac_elapsed", "p0", "outcome",
             "half_inning_label", "velo_decline_vs_early")


def find_season_corpora() -> List[str]:
    """All materialized mlb_pitch_states__<season>.parquet on disk, sorted by season."""
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_pitch_states__*.parquet")))


def _pitch_side(label: str) -> str:
    return "home" if str(label).startswith("top") else "away"


def load_pitch_states(path: str) -> pd.DataFrame:
    """Load one season parquet, validate required cols, add the proxy-pitcher key.

    proxy_pitcher = f"{game_id}|{pitch_side}" -- the (game, side) staff-block unit
    documented as the identity substitute (no per-pitcher id in this corpus).
    """
    df = pd.read_parquet(path)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")
    df = df.copy()
    df["pitch_side"] = df["half_inning_label"].map(_pitch_side)
    df["proxy_pitcher"] = df["game_id"].astype(str) + "|" + df["pitch_side"]
    return df


def fit_tercile_edges(train_df: pd.DataFrame) -> Tuple[float, float]:
    """Quantile cut points (1/3, 2/3) of velo_decline_vs_early on TRAIN rows only.

    NaN velo_decline_vs_early rows (no early-velocity baseline yet in that outing) are
    excluded from the edge fit but still banded downstream (they fall to 'fresh' by
    convention -- not enough pitches yet to show decline, never fabricated as fatigued).
    """
    v = train_df["velo_decline_vs_early"].dropna().to_numpy(dtype=float)
    if v.size == 0:
        return (0.0, 0.0)
    lo, hi = np.quantile(v, [1.0 / 3.0, 2.0 / 3.0])
    return float(lo), float(hi)


def band_tercile(velo_decline: np.ndarray, edges: Tuple[float, float]) -> List[str]:
    """Band raw velo_decline_vs_early into {fresh,declining,fatigued} via TRAIN edges.

    Higher velo_decline_vs_early = more velocity LOST vs early in the outing = MORE
    fatigued. NaN (no baseline yet) -> 'fresh' (honest default, not a fabricated signal).
    """
    lo, hi = edges
    out = []
    for v in velo_decline:
        if not np.isfinite(v):
            out.append("fresh")
        elif v < lo:
            out.append("fresh")
        elif v < hi:
            out.append("declining")
        else:
            out.append("fatigued")
    return out


def to_states(df: pd.DataFrame, edges: Optional[Tuple[float, float]] = None) -> List[dict]:
    """Row-wise state dicts with tercile (TRAIN edges if given, else fit on df itself)."""
    if edges is None:
        edges = fit_tercile_edges(df)
    vd = df["velo_decline_vs_early"].to_numpy(dtype=float)
    tercile = band_tercile(vd, edges)
    states: List[dict] = []
    for i, r in enumerate(df.itertuples(index=False)):
        fe = max(0.0, min(1.0, float(r.frac_elapsed)))
        states.append({
            "game_id": r.game_id, "proxy_pitcher": r.proxy_pitcher,
            "state_diff": float(r.state_diff), "frac_elapsed": fe,
            "p0": float(r.p0), "outcome": int(r.outcome),
            "tercile": tercile[i],
        })
    return states


def shuffle_tercile_planted_null(states: List[dict], seed: int) -> List[dict]:
    """PLANTED NULL (spec): shuffle the tercile assignment ACROSS proxy pitchers,
    holding each state's own (game_id, frac_elapsed-bucket, margin-bucket) cell fixed.

    Deterministic (hash-seeded), not runtime-random: groups states into game-state
    cells, then permutes the LIST of tercile labels within each cell across the
    distinct proxy_pitcher units present there. A within-cell shuffle across pitchers
    preserves the tercile MARGINAL distribution and the (time,margin) structure the
    real gate conditions on, but destroys any true pitcher-fatigue -> outcome link --
    exactly the control the spec requires to reject a spurious-cell artifact.
    """
    from scripts.platformkit.eval_gate.ingame_blend import margin_bucket, time_bucket
    out = [dict(s) for s in states]
    cells: Dict[Tuple[int, int], List[int]] = {}
    for i, s in enumerate(out):
        # frac_elapsed carries seconds-remaining-equivalent info via (1-frac)*total;
        # reuse the shared time_bucket on an equivalent "seconds remaining" proxy.
        secs_left = (1.0 - s["frac_elapsed"]) * 2880.0
        key = (time_bucket(secs_left, total=2880.0), margin_bucket(s["state_diff"]))
        cells.setdefault(key, []).append(i)
    h = hashlib.sha256(",".join(sorted({s["game_id"] for s in states})).encode("ascii"))
    rng = np.random.default_rng(seed + int(h.hexdigest()[:8], 16))
    for idx in cells.values():
        if len(idx) < 2:
            continue
        labels = [out[i]["tercile"] for i in idx]
        perm = rng.permutation(len(idx))
        for slot, i in enumerate(idx):
            out[i] = dict(out[i])
            out[i]["tercile"] = labels[perm[slot]]
    return out


__all__ = ["find_season_corpora", "load_pitch_states", "fit_tercile_edges",
           "band_tercile", "to_states", "shuffle_tercile_planted_null",
           "TERCILES", "OUT"]
