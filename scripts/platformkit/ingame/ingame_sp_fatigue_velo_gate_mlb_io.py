"""scripts.platformkit.ingame.ingame_sp_fatigue_velo_gate_mlb_io -- IO + leak-free
tercile banding for the REDESIGNED MLB SP within-start fatigue in-game gate (wave-30
lane 4). Companion to ingame_sp_fatigue_velo_gate_mlb.py; mirrors the wave-29
sp_fatigue_gate_mlb_io.py split (keep the gate file itself <=300 LOC).

CORPUS: data/domains/mlb/sp_velo_states.parquet (domains/mlb/sp_velo_materialize.py's
output) -- one row per as-of PITCH-STATE for a REAL-Statcast-identified starting
pitcher's own outing, joined onto the proven ESPN win-prob state
(state_diff/frac_elapsed/p0/outcome). Unlike wave-29's corpus, `proxy_pitcher` here is
a REAL per-pitcher Statcast id (int), not a (game_id, side) staff-block proxy -- so DM
clustering and the planted-null shuffle are keyed to the actual pitcher, a strictly
TIGHTER identity than wave-29's substitute.

velo_decline: mean(release_speed, last 15 pitches as-of) minus mean(release_speed,
first 15 pitches of the start). NEGATIVE = slower late = more fatigued (see
domains/mlb/sp_velo_materialize.py's _velo_decline_series docstring for the exact
as-of formula and leak-freeness argument).

LEAK-FREENESS: the fatigue tercile EDGES (quantile cut points of velo_decline) are fit
on the TRAIN fold ONLY and applied unchanged to the TEST fold.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CORPUS = os.path.join(_REPO, "data", "domains", "mlb", "sp_velo_states.parquet")
OUT = os.path.join(_REPO, "data", "domains", "mlb", "sp_velo_fatigue_gate_verdict.json")

TERCILES = ("fresh", "declining", "fatigued")
_REQUIRED = ("game_id", "state_diff", "frac_elapsed", "p0", "outcome",
             "proxy_pitcher", "velo_decline", "date")


def find_corpus(path: str = CORPUS) -> Optional[str]:
    """The consolidated velo-decline states parquet, or None if not on disk."""
    return path if os.path.exists(path) else None


def load_states_df(path: str = CORPUS) -> pd.DataFrame:
    """Load + validate the consolidated corpus."""
    df = pd.read_parquet(path)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")
    return df.copy()


def fit_tercile_edges(train_df: pd.DataFrame) -> Tuple[float, float]:
    """Quantile cut points (1/3, 2/3) of velo_decline on TRAIN rows only.

    NaN velo_decline rows (not enough pitches yet for either window) are excluded from
    the edge fit but still banded downstream (they fall to 'fresh' by convention --
    not enough pitches to show real decline, never fabricated as fatigued).
    """
    v = train_df["velo_decline"].dropna().to_numpy(dtype=float)
    if v.size == 0:
        return (0.0, 0.0)
    lo, hi = np.quantile(v, [1.0 / 3.0, 2.0 / 3.0])
    return float(lo), float(hi)


def band_tercile(velo_decline: np.ndarray, edges: Tuple[float, float]) -> List[str]:
    """Band raw velo_decline into {fresh,declining,fatigued} via TRAIN edges.

    velo_decline is NEGATIVE when slower (fatigued): LOWER (more negative) values are
    MORE fatigued. NaN (no baseline yet) -> 'fresh' (honest default, never fabricated).
    """
    lo, hi = edges
    out = []
    for v in velo_decline:
        if not np.isfinite(v):
            out.append("fresh")
        elif v < lo:
            out.append("fatigued")
        elif v < hi:
            out.append("declining")
        else:
            out.append("fresh")
    return out


def to_states(df: pd.DataFrame, edges: Optional[Tuple[float, float]] = None) -> List[dict]:
    """Row-wise state dicts with tercile (TRAIN edges if given, else fit on df itself)."""
    if edges is None:
        edges = fit_tercile_edges(df)
    vd = df["velo_decline"].to_numpy(dtype=float)
    tercile = band_tercile(vd, edges)
    states: List[dict] = []
    for i, r in enumerate(df.itertuples(index=False)):
        fe = max(0.0, min(1.0, float(r.frac_elapsed)))
        states.append({
            "game_id": str(r.game_id), "proxy_pitcher": int(r.proxy_pitcher),
            "state_diff": float(r.state_diff), "frac_elapsed": fe,
            "p0": float(r.p0), "outcome": int(r.outcome),
            "tercile": tercile[i],
        })
    return states


def shuffle_tercile_planted_null(states: List[dict], seed: int) -> List[dict]:
    """PLANTED NULL (spec, mandatory): shuffle the tercile assignment ACROSS pitchers,
    holding each state's own (time-bucket, margin-bucket) cell fixed.

    Deterministic (hash-seeded). A within-cell shuffle across REAL pitchers preserves
    the tercile MARGINAL distribution and the (time,margin) structure the real gate
    conditions on, but destroys any true pitcher-fatigue -> outcome link -- exactly the
    control the spec requires. If this ALSO passes the ship bar, verdict = NOT_TESTABLE
    (per wave-29 precedent) and the hypothesis class closes.
    """
    from scripts.platformkit.eval_gate.ingame_blend import margin_bucket, time_bucket
    out = [dict(s) for s in states]
    cells: Dict[Tuple[int, int], List[int]] = {}
    for i, s in enumerate(out):
        secs_left = (1.0 - s["frac_elapsed"]) * 2880.0
        key = (time_bucket(secs_left, total=2880.0), margin_bucket(s["state_diff"]))
        cells.setdefault(key, []).append(i)
    h = hashlib.sha256(",".join(sorted({str(s["game_id"]) for s in states})).encode("ascii"))
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


__all__ = ["find_corpus", "load_states_df", "fit_tercile_edges", "band_tercile",
           "to_states", "shuffle_tercile_planted_null", "TERCILES", "CORPUS", "OUT"]
