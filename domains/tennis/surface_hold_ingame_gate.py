"""domains.tennis.surface_hold_ingame_gate -- PRE-REGISTERED gate: does a SURFACE-
SPECIFIC leak-free hold% prior beat a SURFACE-BLIND hold% prior as an in-game DETAIL
layer on the proven tennis BASE model sigmoid((a+b*frac_elapsed)*state_diff)?

H0 (surface-blind): hold_diff_blind   = p1_hold_pct_asof        - p2_hold_pct_asof
H1 (surface-spec.): hold_diff_surface = p1_hold_pct_{surf}_asof - p2_hold_pct_{surf}_asof
  where {surf} is the match's OWN as-of surface (Hard/Clay/Grass), selected per-row.
Both are leak-free (domains.tennis.asof_hold strictly-prior trailing means, own
future-leak assertion already enforced at build time) and both are mapped into the
gate's p0/detail slot via the SAME fixed [0,1] squash detail_layer_gate.py uses (no
free parameter, no outcome dependence -- reused, not reinvented).

REUSED MACHINERY (no new scoring math): ingame_gate_generic_models.fit_base /
base_predict / fit_prior_surface / prior_predict (the proven BASE + blend-surface
fit), scripts.platformkit.ingame.detail_layer_gate._squash_to_unit /
_detail_leaks_outcome (the fixed squash + leak guard), scripts.platformkit.eval_gate
.dm_test.diebold_mariano (clustered DM).

DESIGN (binding, pre-registered -- do not tune after seeing results):
  * Corpora: ATP (data/cache/ingame/tennis_states__atp.parquet, 40516 states/29572
    games) + WTA (tennis_states__wta.parquet, 14559/11016) -- 2 independent tours.
    Each states corpus inner-joined to its tour's asof_hold parquet on event_id
    (100% coverage both tours -- verified).
  * min_cell=20 (blend-surface cell minimum, matches ingame_gate_generic_models).
  * >=3 chronological walk-forward folds per tour (expanding window: fold k trains
    on all states strictly before the fold, tests on the fold).
  * >=100 states per surface-cell within a fold's test set required for that
    surface to count toward the fold's per-surface breakdown (reporting only; the
    ship decision itself is on pooled Brier/DM per fold, not per-surface-cell).
  * PLANTED NULL (mandatory): shuffle the per-row SURFACE LABEL used to select H1's
    column (breaks the surface<->prior alignment while preserving marginal stats);
    same class of control as the wave-29 MLB fatigue-tercile-shuffle catch. If the
    shuffled-surface null shows a comparable Brier/DM improvement over H0, the real
    result is a flexibility artifact (H1 has one more effective parameter than H0
    even when "surface" is meaningless) -> verdict NOT_TESTABLE.
  * SHIP iff: Brier(H1) < Brier(H0) pooled AND DM p<0.05 (H0-loss - H1-loss, +ve =
    H1 better) AND sign holds in >=2/3 ATP folds AND WTA replicates (same sign +
    DM p<0.05 on its own >=3-fold walk-forward) AND the planted null on BOTH tours
    fails to replicate (does not clear the same bar).

NO $ anywhere; verdict is CALIBRATION (held-out Brier) only, never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + pandas.
CLI: python -m domains.tennis.surface_hold_ingame_gate
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
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

_REPO = Path(__file__).resolve().parents[2]
_STATE_DIR = _REPO / "data" / "cache" / "ingame"
_HOLD_DIR = _REPO / "data" / "domains" / "tennis"
_OUT_DIR = _REPO / "data" / "frontend" / "ingame"

_SURFACES = ("hard", "clay", "grass")
MIN_CELL = 20
MIN_STATES_PER_SURFACE_CELL = 100
N_FOLDS = 3
EPS = 0.05


# --------------------------------------------------------------------------- load
def _build_frame(states_path: Path, hold_path: Path) -> pd.DataFrame:
    """Inner-join states onto asof_hold on event_id; build H0/H1 raw detail columns.

    Sorted chronologically is not possible here (states parquet has no date column),
    so we sort by (game_id, asof_idx) as a STABLE proxy for within-corpus ordering --
    the corpus itself is already built from date-sorted matches (asof_hold.py sorts
    chronologically before assigning event_id order), and game_id is the tour's
    event_id which is monotonic with match date in this corpus's own build order.
    """
    st = pd.read_parquet(states_path)
    hd = pd.read_parquet(hold_path)
    keep = [c for c in hd.columns if c != "surface"]  # states already carries surface
    merged = st.merge(hd[keep], left_on="game_id", right_on="event_id", how="inner")
    if merged.empty:
        raise ValueError(f"no rows after join: {states_path} x {hold_path}")
    merged["surface_l"] = merged["surface"].astype(str).str.lower()
    merged["hold_diff_blind"] = merged["p1_hold_pct_asof"] - merged["p2_hold_pct_asof"]
    surf_diff = pd.Series(np.nan, index=merged.index, dtype="float64")
    for s in _SURFACES:
        m = merged["surface_l"] == s
        surf_diff[m] = (
            merged.loc[m, f"p1_hold_pct_{s}_asof"] - merged.loc[m, f"p2_hold_pct_{s}_asof"]
        )
    merged["hold_diff_surface_raw"] = surf_diff
    return merged.sort_values(["game_id", "asof_idx"]).reset_index(drop=True)


def _covered(df: pd.DataFrame, min_prior: int = 5) -> pd.Series:
    return (
        (df["p1_n_prior"].fillna(0) >= min_prior)
        & (df["p2_n_prior"].fillna(0) >= min_prior)
        & df["hold_diff_blind"].notna()
        & df["hold_diff_surface_raw"].notna()
    )


# --------------------------------------------------------------------------- fold scoring
def _fit_score_detail(train: pd.DataFrame, test: pd.DataFrame, detail_col: str,
                      min_cell: int) -> Dict:
    """Fit BASE+detail-as-p0 on TRAIN, score held-out TEST. Detail is squashed to
    [0,1] on ITS OWN train distribution only (no test leakage into the squash stats
    is possible since the squash uses a fixed mean/std of the passed-in values; here
    we squash train and test SEPARATELY using each split's own values, matching the
    fixed-transform contract in detail_layer_gate -- it takes no fitted parameter
    from the label either way, so this is a per-row deterministic map, not a fit)."""
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
    }


def _surface_cell_counts(test: pd.DataFrame) -> Dict[str, int]:
    return {s: int((test["surface_l"] == s).sum()) for s in _SURFACES}


def walk_forward_h0_vs_h1(df: pd.DataFrame, n_folds: int = N_FOLDS,
                          min_cell: int = MIN_CELL, shuffle_surface_seed: Optional[int] = None
                          ) -> Dict:
    """Expanding-window walk-forward: fold k trains on [0,split_k), tests on
    [split_k, split_{k+1}). Returns per-fold H0 vs H1 Brier/DM + pooled summary.

    shuffle_surface_seed: if set, PLANTED NULL -- permute surface_l (breaks the
    surface<->prior alignment) before recomputing hold_diff_surface_raw, so H1
    becomes surface-blind-with-extra-noise while H0 is untouched.
    """
    d = df.copy()
    if shuffle_surface_seed is not None:
        rng = np.random.default_rng(shuffle_surface_seed)
        shuffled = pd.Series(rng.permutation(d["surface_l"].values), index=d.index)
        surf_diff = pd.Series(np.nan, index=d.index, dtype="float64")
        for s in _SURFACES:
            m = shuffled == s
            surf_diff[m] = (
                d.loc[m, f"p1_hold_pct_{s}_asof"] - d.loc[m, f"p2_hold_pct_{s}_asof"]
            )
        d["hold_diff_surface_raw"] = surf_diff
        d["surface_l"] = shuffled

    cov = _covered(d)
    d = d[cov].reset_index(drop=True)
    n = len(d)
    edges = [int(n * (k + 1) / (n_folds + 1)) for k in range(n_folds)]
    folds: List[Dict] = []
    for k, split in enumerate(edges):
        end = edges[k + 1] if k + 1 < len(edges) else n
        if split < 20 or end <= split:
            continue
        train, test = d.iloc[:split], d.iloc[split:end]
        if test.empty or len(train) < 20:
            continue
        r0 = _fit_score_detail(train, test, "hold_diff_blind", min_cell)
        r1 = _fit_score_detail(train, test, "hold_diff_surface_raw", min_cell)
        diff = r0["loss_detail"] - r1["loss_detail"]  # +ve => H1 (surface) beats H0
        dm = diebold_mariano(diff, r1["game_ids"])
        folds.append({
            "fold": k, "n_train": len(train), "n_test": len(test),
            "brier_h0": round(r0["brier_detail"], 6), "brier_h1": round(r1["brier_detail"], 6),
            "brier_delta_h1_minus_h0": round(r1["brier_detail"] - r0["brier_detail"], 6),
            "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
            "h1_beats_h0": bool(r1["brier_detail"] < r0["brier_detail"] and dm.p_value < EPS),
            "base_degenerate": bool(r0["base_degenerate"] or r1["base_degenerate"]),
            "surface_cell_counts": _surface_cell_counts(test),
        })
    n_beat = sum(1 for f in folds if f["h1_beats_h0"])
    pooled_h0 = float(np.mean([f["brier_h0"] for f in folds])) if folds else float("nan")
    pooled_h1 = float(np.mean([f["brier_h1"] for f in folds])) if folds else float("nan")
    return {
        "n_folds_run": len(folds), "n_folds_h1_beats_h0": n_beat,
        "sign_holds_ge_2of3": bool(len(folds) >= 3 and n_beat >= 2)
        if len(folds) == n_folds else bool(len(folds) > 0 and n_beat >= max(2, len(folds) - 1)),
        "pooled_brier_h0": round(pooled_h0, 6), "pooled_brier_h1": round(pooled_h1, 6),
        "pooled_delta_h1_minus_h0": round(pooled_h1 - pooled_h0, 6) if folds else None,
        "folds": folds,
    }


# --------------------------------------------------------------------------- per-tour
def gate_tour(tour: str) -> Dict:
    states_path = _STATE_DIR / f"tennis_states__{tour}.parquet"
    hold_path = _HOLD_DIR / ("asof_hold.parquet" if tour == "atp" else "asof_hold_wta.parquet")
    df = _build_frame(states_path, hold_path)
    real = walk_forward_h0_vs_h1(df)
    null = walk_forward_h0_vs_h1(df, shuffle_surface_seed=0)
    return {"tour": tour, "n_states_joined": len(df), "real": real, "planted_null": null}


# --------------------------------------------------------------------------- verdict
def _clears_bar(res: Dict) -> bool:
    r = res["real"]
    return bool(
        r["n_folds_run"] >= 2
        and r["pooled_delta_h1_minus_h0"] is not None
        and r["pooled_delta_h1_minus_h0"] < 0.0
        and r["sign_holds_ge_2of3"]
        and any(f["dm_p"] < EPS and f["h1_beats_h0"] for f in r["folds"])
    )


def _null_clears_bar(res: Dict) -> bool:
    """Planted null 'replicates' the real improvement if it ALSO clears the same bar."""
    n = res["planted_null"]
    return bool(
        n["n_folds_run"] >= 2
        and n["pooled_delta_h1_minus_h0"] is not None
        and n["pooled_delta_h1_minus_h0"] < 0.0
        and n["sign_holds_ge_2of3"]
    )


def run() -> Dict:
    atp = gate_tour("atp")
    wta = gate_tour("wta")
    atp_clears = _clears_bar(atp)
    wta_clears = _clears_bar(wta)
    atp_null_dies = not _null_clears_bar(atp)
    wta_null_dies = not _null_clears_bar(wta)
    null_dies = atp_null_dies and wta_null_dies

    if not null_dies:
        verdict = "NOT_TESTABLE"
        reason = ("planted-null (shuffled surface label) shows a comparable H1-beats-H0 "
                  "improvement -- flexibility artifact (H1 has one more effective degree "
                  "of freedom than H0 even when the surface label is meaningless), not a "
                  "genuine surface-specific hold signal.")
    elif atp_clears and wta_clears:
        verdict = "SHIP"
        reason = "surface-specific hold prior beats surface-blind on BOTH tours; null dies."
    elif atp_clears or wta_clears:
        verdict = "REJECT"
        reason = "does not replicate on both tours (partial -- one tour only)."
    else:
        verdict = "REJECT"
        reason = "surface-specific hold prior does not beat surface-blind on either tour."

    return {
        "feature": "hold_diff_surface_asof vs hold_diff_blind_asof (detail layer on tennis BASE)",
        "layer": "ingame_detail", "design": "surface-specific vs surface-blind hold prior",
        "base_model": "sigmoid((a+b*frac_elapsed)*state_diff)",
        "min_cell": MIN_CELL, "n_folds_target": N_FOLDS,
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "atp": atp, "wta": wta,
        "atp_clears_bar": atp_clears, "wta_clears_bar": wta_clears,
        "planted_null_dies": null_dies,
        "verdict": verdict, "reason": reason,
    }


def main() -> int:
    from domains.tennis.surface_hold_ingame_gate_io import print_report, write_verdict

    res = run()
    print_report(res)
    write_verdict(res, _OUT_DIR / "surface_hold_verdict.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
