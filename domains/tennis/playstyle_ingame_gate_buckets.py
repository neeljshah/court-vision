"""domains.tennis.playstyle_ingame_gate_buckets -- archetype-bucket assignment +
per-fold scoring helper for playstyle_ingame_gate.py (H3), split out so the gate
module stays <=300 LOC.

Serve-orientation bucket derived from the SAME threshold constants
atlas_playstyle_specs.py defines (CLAY/GRASS/HARD_SPECIALIST_DELTA, HEIGHT_BIG_SERVER)
-- no new thresholds invented here. See playstyle_ingame_gate.py's module docstring
for the full H3 design rationale, AS-OF caveat, and ATP-only dependency constraint.

fit_score_detail is the SAME fit-BASE/fit-blend-surface/score-held-out routine
surface_hold_ingame_gate.py inlines, factored here (no new scoring math) purely to
keep playstyle_ingame_gate.py under the LOC cap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.detail_layer_gate import (
    _detail_leaks_outcome,
    _squash_to_unit,
)
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate,
    base_predict,
    fit_base,
    fit_prior_surface,
    prior_predict,
)
from domains.tennis.atlas_playstyle_specs import (
    CLAY_SPECIALIST_DELTA,
    GRASS_SPECIALIST_DELTA,
    HARD_SPECIALIST_DELTA,
    HEIGHT_BIG_SERVER,
)

ATLAS_CORPUS_ID = "sackmann_atp_matches_parquet"  # atlas_playstyles.parquet provenance


def _ok(v: object) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def serve_bucket(row: pd.Series) -> str:
    """Serve-orientation bucket. OPEN mapping choice (spec names only the "big-serve
    vs elite-returner" example, not a full bucket table): Fast_Court_Big_Server /
    Grass_Court_Specialist -> 'serve'; Clay_Court_Specialist -> 'return'; everything
    else (Journeyman, All_Court_Baseliner, Left_Handed_Specialist, Grand_Slam_Performer,
    or unclassified) -> 'neutral'.
    """
    ov = row.get("ov_wr")
    hw, cw, gw = row.get("hard_wr"), row.get("clay_wr"), row.get("grass_wr")
    ht = row.get("height")

    if _ok(cw) and _ok(ov) and float(cw) - float(ov) >= CLAY_SPECIALIST_DELTA:
        return "return"
    if _ok(ht) and float(ht) >= HEIGHT_BIG_SERVER:
        if (_ok(hw) and _ok(ov) and float(hw) - float(ov) >= HARD_SPECIALIST_DELTA) or (
                _ok(gw) and _ok(cw) and float(gw) > float(cw)):
            return "serve"
    if _ok(gw) and _ok(ov) and float(gw) - float(ov) >= GRASS_SPECIALIST_DELTA:
        return "serve"
    return "neutral"


def load_player_buckets(atlas_path: Path) -> pd.DataFrame:
    """Load atlas_playstyles.parquet, assert ATP-only provenance, return
    {player_id, bucket}. Fails honest (not silent) if provenance is not the
    expected single-corpus ATP snapshot."""
    ap = pd.read_parquet(atlas_path)
    corpora = set(ap["corpus_id"].unique())
    if corpora != {ATLAS_CORPUS_ID}:
        raise ValueError(
            f"{atlas_path}: expected single corpus_id={ATLAS_CORPUS_ID!r}, found {corpora}")
    ap = ap.copy()
    ap["bucket"] = ap.apply(serve_bucket, axis=1)
    return ap[["player_id", "bucket"]]


MIN_PAIR_TYPE_CELL = 20  # below this, fall back to the pooled global tercile (too thin)


def _tercile_gate(train: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """TRAIN-only tercile edges of hold_diff_blind PER pair_type -- the spec's exact
    gating condition: 'archetype-pair being in a top-vs-bottom tercile of historical
    hold-rate differential FOR THAT PAIRING TYPE' (TENNIS_TRUTH_SPEC_2026-07-04.md,
    H3). Returns {pair_type: (lo, hi)} plus a '__pooled__' fallback entry (global
    tercile) used whenever a pair_type has fewer than MIN_PAIR_TYPE_CELL train rows
    -- the OPEN, conservative simplification stated in playstyle_ingame_gate.py's
    module docstring, applied only to thin cells, not universally."""
    edges: Dict[str, Tuple[float, float]] = {}
    vals_all = train["hold_diff_blind"].dropna().to_numpy(dtype=float)
    if len(vals_all) < 3:
        edges["__pooled__"] = (0.0, 0.0)
        return edges
    lo_all, hi_all = np.quantile(vals_all, [1.0 / 3.0, 2.0 / 3.0])
    edges["__pooled__"] = (float(lo_all), float(hi_all))
    for pt, grp in train.groupby("pair_type"):
        vals = grp["hold_diff_blind"].dropna().to_numpy(dtype=float)
        if len(vals) < MIN_PAIR_TYPE_CELL:
            continue  # thin cell -- falls back to __pooled__ at lookup time
        lo, hi = np.quantile(vals, [1.0 / 3.0, 2.0 / 3.0])
        edges[str(pt)] = (float(lo), float(hi))
    return edges


def _pairing_detail_raw(df: pd.DataFrame, edges: Dict[str, Tuple[float, float]]) -> pd.Series:
    """Detail term: hold_diff_blind gated to 0 UNLESS the row's OWN pair_type's
    historical hold-rate-differential tercile (per spec: 'for that pairing type') is
    extreme for this row -- i.e. archetype buckets/pair_type are load-bearing in the
    numeric term, not just a coverage filter (the bug this replaced: a single pooled
    global tercile made pair_type/buckets mathematically inert). Falls back to the
    pooled '__pooled__' edges for any pair_type too thin to have its own tercile."""
    d = df["hold_diff_blind"].to_numpy(dtype=float)
    pair_types = df["pair_type"].astype(str).to_numpy()
    pooled = edges.get("__pooled__", (0.0, 0.0))
    lo = np.array([edges.get(pt, pooled)[0] for pt in pair_types], dtype=float)
    hi = np.array([edges.get(pt, pooled)[1] for pt in pair_types], dtype=float)
    extreme = (d <= lo) | (d >= hi)
    out = np.where(extreme, d, 0.0)
    return pd.Series(out, index=df.index)


def fit_score_detail(train: pd.DataFrame, test: pd.DataFrame, detail_col: str,
                     min_cell: int) -> Dict:
    """Fit BASE+detail-as-p0 on TRAIN, score held-out TEST (identical routine to
    surface_hold_ingame_gate._fit_score_detail -- no new scoring math)."""
    def _states(d: pd.DataFrame, raw_col: str) -> List[dict]:
        p0 = _squash_to_unit(list(d[raw_col].astype(float)))
        return [
            {"game_id": gid, "state_diff": float(sd), "frac_elapsed": float(fe),
             "p0": float(p), "outcome": int(y)}
            for gid, sd, fe, p, y in zip(
                d["game_id"], d["state_diff"], d["frac_elapsed"], p0, d["outcome"])
        ]

    tr = _states(train, detail_col)
    te = _states(test, detail_col)
    if _detail_leaks_outcome([s["p0"] for s in tr], [s["outcome"] for s in tr]):
        raise ValueError(f"LEAK GUARD: {detail_col} (near-)perfectly encodes outcome on train")

    ab = fit_base(tr)
    base_tr = base_predict(tr, ab)
    surf = fit_prior_surface(tr, base_tr, min_cell=min_cell)
    y_te = np.array([s["outcome"] for s in te], float)
    base_te = base_predict(te, ab)
    detail_te = prior_predict(te, base_te, surf)
    br_base = float(np.mean((base_te - y_te) ** 2))
    br_detail = float(np.mean((detail_te - y_te) ** 2))
    degen = base_is_degenerate(ab, tr, base_te, y_te)
    return {
        "brier_base": br_base, "brier_detail": br_detail,
        "loss_base": (base_te - y_te) ** 2, "loss_detail": (detail_te - y_te) ** 2,
        "game_ids": [s["game_id"] for s in te], "base_degenerate": degen["degenerate"],
        "p_variant": detail_te.tolist(), "p_base": base_te.tolist(),
        "outcome": y_te.tolist(),
    }
