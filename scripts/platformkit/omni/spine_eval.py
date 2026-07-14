"""scripts.platformkit.omni.spine_eval -- P6 standing PBP-replay evaluator.

Scores spine_nba (v0 state-only, v1 +identity/+K-asof, v2 +lineup-identity) on
the FULL held-out 2025-26 season vs sim2_cells (PossessionModel fit on
FIT_SEASONS, a harder bar) and marginal (fixed class-frequency); v1/v2 also
verdict against their predecessor on the identical held-out rows.

Metrics (ordinal 5-class points-bucket {0,1,2,3,4+}): CRPS, log-loss,
reliability-by-prob-bin. Verdict BEATS/TIES/TRAILS (TIES=within 1% rel).
Seed-stability: retrain w/ 2nd seed, delta must stay <2% or reported unstable.

INVARIANTS: domains/src untouched (import-only); <=300 LOC; ASCII; local
only; no $/edge claims; ledger writes DEFERRED to end of run; prior versions'
artifacts (eval_2025_26.json, eval_2025_26_v1.json) never overwritten.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_spine_eval.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from domains.basketball_nba.sim2.corpus import FIT_SEASONS
from domains.basketball_nba.sim2.possession_model import PossessionModel, cell_index
from scripts.platformkit.io_atomic import write_json_atomic
from scripts.platformkit.omni import spine_nba as SP

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "omni" / "spine"
EVAL_OUT = _OUT_DIR / "eval_2025_26.json"
EVAL_OUT_V1 = _OUT_DIR / "eval_2025_26_v1.json"     # versioned, v0 untouched
EVAL_OUT_V2 = _OUT_DIR / "eval_2025_26_v2.json"     # versioned, v0/v1 untouched
PREDS_OUT = _OUT_DIR / "preds" / "preds_2025_26.parquet"   # ponytail: single
# overwritten file per run (standing evaluator re-run, not discovery sweep).
PREDS_OUT_V1 = _OUT_DIR / "preds" / "preds_2025_26_v1.parquet"
PREDS_OUT_V2 = _OUT_DIR / "preds" / "preds_2025_26_v2.parquet"
TEST_SEASON = "2025-26"
IMPORTANCE_SAMPLE = 20_000   # ponytail: permutation importance on a fixed
# subsample (HGB has no feature_importances_); full 247k rows is needless cost.
MIN_TEST_ROWS = 100_000
SEED_A, SEED_B = 42, 43
TIE_REL = 0.01          # within 1% relative -> TIES
SEED_STABLE_REL = 0.02  # seed-retrain delta must stay under this


# ordinal metrics (5-class CDF, class 4 == "4+")
def cdf_from_proba(proba: np.ndarray) -> np.ndarray:
    """[n,5] class-proba -> [n,5] inclusive CDF."""
    return np.cumsum(proba, axis=1)


def crps_ordinal(cdf: np.ndarray, y: np.ndarray, n_classes: int = SP.N_CLASSES) -> np.ndarray:
    """Discrete ranked-probability-score per row: sum_k (F(k) - 1{y<=k})^2."""
    k = np.arange(n_classes)
    step = (k[None, :] >= y[:, None]).astype(float)   # 1{y<=k}
    return np.sum((cdf - step) ** 2, axis=1)


def log_loss_rows(proba: np.ndarray, y: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    p_true = np.clip(proba[np.arange(len(y)), y], eps, 1.0)
    return -np.log(p_true)


def reliability_table(proba: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list:
    """Bin by predicted top-class prob; report count, mean pred prob, acc."""
    top_class = proba.argmax(axis=1)
    top_p = proba[np.arange(len(y)), top_class]
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (top_p >= lo) & (top_p < hi if i < n_bins - 1 else top_p <= hi)
        if not m.any():
            continue
        out.append({"bin": [round(float(lo), 2), round(float(hi), 2)],
                     "n": int(m.sum()), "mean_pred_p": round(float(top_p[m].mean()), 4),
                     "empirical_acc": round(float((top_class[m] == y[m]).mean()), 4)})
    return out


def _verdict(a: float, b: float) -> str:
    """a=model metric, b=baseline metric (lower-is-better)."""
    if b == 0:
        return "TIES"
    rel = (a - b) / abs(b)
    if abs(rel) <= TIE_REL:
        return "TIES"
    return "BEATS" if rel < 0 else "TRAILS"


# baselines on the same held-out rows
def sim2_cells_proba(test_df: pd.DataFrame, fit_df: pd.DataFrame) -> np.ndarray:
    """Fit the REAL existing engine (PossessionModel) on FIT_SEASONS, return
    its implied 5-class proba on test_df's cells -- the actual prod baseline."""
    pmodel = PossessionModel.fit(fit_df)
    cdf7 = pmodel.point_cdf_matrix()   # [N_CELLS, 7] (points 0..6)
    idx = cell_index(test_df["time_b"].to_numpy(), test_df["margin_b"].to_numpy(),
                      test_df["off_t"].to_numpy(), test_df["def_t"].to_numpy(),
                      test_df["pace_t"].to_numpy())
    cdf7_rows = cdf7[idx]
    cdf5 = np.empty((len(test_df), SP.N_CLASSES))
    cdf5[:, :4] = cdf7_rows[:, :4]      # F(0),F(1),F(2),F(3) unchanged
    cdf5[:, 4] = 1.0                    # class 4 ("4+") absorbs the rest
    proba = np.diff(cdf5, axis=1, prepend=0.0)
    return np.clip(proba, 0.0, 1.0)


def marginal_proba(train_df: pd.DataFrame, n_rows: int) -> np.ndarray:
    """Fixed class-frequency vector from spine_nba's own train rows, broadcast
    to n_rows -- the naive 'no state at all' baseline."""
    y = SP.points_to_class(train_df["points"].to_numpy())
    counts = np.bincount(y, minlength=SP.N_CLASSES).astype(float)
    p = counts / counts.sum()
    return np.tile(p, (n_rows, 1))


# one full eval pass (reused for both seeds)
def feature_importance_top10(clf, test_df: pd.DataFrame, features: list,
                              seed: int) -> list:
    """Permutation importance (neg_log_loss drop) on a fixed subsample."""
    rng = np.random.default_rng(seed)
    n = min(IMPORTANCE_SAMPLE, len(test_df))
    idx = rng.choice(len(test_df), size=n, replace=False)
    sub = test_df.iloc[idx]
    x = sub[features].to_numpy(dtype=float)
    y = SP.points_to_class(sub["points"].to_numpy())
    r = permutation_importance(clf, x, y, scoring="neg_log_loss",
                                n_repeats=3, random_state=seed)
    order = np.argsort(r.importances_mean)[::-1][:10]
    return [{"feature": features[i], "importance_mean": round(float(r.importances_mean[i]), 5)}
            for i in order]


def _score_all(state_df: pd.DataFrame, seed: int, features: list = None,
                model_name: str = "spine_v0") -> Tuple[Dict[str, Any], pd.DataFrame, Any]:
    features = features or SP.FEATURES
    clf, train_df = SP.fit_spine_discovery(state_df, seed=seed, features=features)
    test_df = state_df[state_df["season"] == TEST_SEASON].reset_index(drop=True)
    if len(test_df) < MIN_TEST_ROWS:
        raise ValueError(f"held-out {TEST_SEASON} has {len(test_df)} rows < {MIN_TEST_ROWS}")
    y = SP.points_to_class(test_df["points"].to_numpy())
    p_model = SP.predict_proba(clf, test_df, features=features)
    p_sim2 = sim2_cells_proba(test_df, state_df[state_df["season"].isin(FIT_SEASONS)])
    p_marg = marginal_proba(train_df, len(test_df))
    metrics: Dict[str, Any] = {}
    per_model = {}
    for name, proba in ((model_name, p_model), ("sim2_cells", p_sim2), ("marginal", p_marg)):
        cdf = cdf_from_proba(proba)
        crps = float(crps_ordinal(cdf, y).mean())
        ll = float(log_loss_rows(proba, y).mean())
        per_model[name] = {"crps": round(crps, 5), "log_loss": round(ll, 5)}
    metrics["per_model"] = per_model
    metrics["verdict"] = {
        "crps_vs_sim2_cells": _verdict(per_model[model_name]["crps"], per_model["sim2_cells"]["crps"]),
        "crps_vs_marginal": _verdict(per_model[model_name]["crps"], per_model["marginal"]["crps"]),
        "log_loss_vs_sim2_cells": _verdict(per_model[model_name]["log_loss"], per_model["sim2_cells"]["log_loss"]),
        "log_loss_vs_marginal": _verdict(per_model[model_name]["log_loss"], per_model["marginal"]["log_loss"]),
    }
    metrics[f"reliability_{model_name}"] = reliability_table(p_model, y)
    metrics["n_test"] = int(len(test_df))
    metrics["n_train"] = int(len(train_df))
    metrics["seed"] = seed
    preds = pd.DataFrame({
        "game_id": test_df["game_id"].to_numpy(), "true_class": y,
        f"p_{model_name}": list(p_model.astype("float32")),
        "p_sim2_cells": list(p_sim2.astype("float32")),
    })
    return metrics, preds, (clf, test_df)


def _seed_deltas(metrics_a: Dict, metrics_b: Dict, model_name: str) -> Tuple[Dict, bool]:
    deltas, stable = {}, True
    for metric in ("crps", "log_loss"):
        va = metrics_a["per_model"][model_name][metric]
        vb = metrics_b["per_model"][model_name][metric]
        rel = abs(va - vb) / abs(va) if va else 0.0
        deltas[f"{model_name}_{metric}_rel_delta"] = round(rel, 5)
        stable = stable and (rel <= SEED_STABLE_REL)
    return deltas, stable


def run() -> Dict[str, Any]:
    state_df = SP.build_state_frame()
    metrics_a, preds, _ = _score_all(state_df, SEED_A)
    metrics_b, _, _ = _score_all(state_df, SEED_B)
    deltas, stable = _seed_deltas(metrics_a, metrics_b, "spine_v0")

    doc = {
        "model": "nba_spine_v0", "edge_claimed": False,
        "train_season": SP.TRAIN_SEASON, "test_season": TEST_SEASON,
        "fit_seasons_sim2_baseline": list(FIT_SEASONS),
        "seed_a": metrics_a, "seed_b": {"seed": SEED_B, "per_model": metrics_b["per_model"]},
        "seed_stability": {"deltas": deltas, "threshold_rel": SEED_STABLE_REL, "seed_stable": bool(stable)},
        "honest_note": "Calibration/sharpness only, no dollars/edge. sim2_cells baseline is fit on FIT_SEASONS (2 seasons) -- a harder bar than spine_v0's single discovery season.",
    }
    _write_versioned(doc, preds, EVAL_OUT, PREDS_OUT)
    return doc


def _run_version(state_df: pd.DataFrame, features: list, model_name: str,
                  prev_features: list, prev_model_name: str
                 ) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Shared run_v1/run_v2 body: score model_name + prev_model_name on the
    SAME state_df -- apples-to-apples, not a re-read of a versioned artifact."""
    metrics_prev, _preds_prev, _ = _score_all(state_df, SEED_A, features=prev_features, model_name=prev_model_name)
    metrics_a, preds, (clf_a, test_df) = _score_all(state_df, SEED_A, features=features, model_name=model_name)
    metrics_b, _, _ = _score_all(state_df, SEED_B, features=features, model_name=model_name)
    deltas, stable = _seed_deltas(metrics_a, metrics_b, model_name)

    mp, pp = metrics_a["per_model"][model_name], metrics_prev["per_model"][prev_model_name]
    verdict_vs_prev = {"crps_vs_prev": _verdict(mp["crps"], pp["crps"]),
                        "log_loss_vs_prev": _verdict(mp["log_loss"], pp["log_loss"])}
    importance = feature_importance_top10(clf_a, test_df, features, SEED_A)
    base = {
        "train_season": SP.TRAIN_SEASON, "test_season": TEST_SEASON,
        "fit_seasons_sim2_baseline": list(FIT_SEASONS),
        "seed_a": metrics_a, "seed_b": {"seed": SEED_B, "per_model": metrics_b["per_model"]},
        "prev_baseline": {"per_model": {prev_model_name: pp}},
        "verdict_vs_prev": verdict_vs_prev,
        "feature_importance_top10": importance,
        "seed_stability": {"deltas": deltas, "threshold_rel": SEED_STABLE_REL, "seed_stable": bool(stable)},
    }
    return base, preds, test_df


def _write_versioned(doc: Dict[str, Any], preds: pd.DataFrame, eval_path: Path, preds_path: Path) -> None:
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(eval_path, doc, indent=2)
    preds_path.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(preds_path, index=False)


def run_v1() -> Dict[str, Any]:
    """v1 = v0 features + team identity + K-asof team-strength."""
    state_df = SP.build_state_frame_v1()
    base, preds, _test_df = _run_version(state_df, SP.FEATURES_V1, "spine_v1", SP.FEATURES, "spine_v0")
    doc = {"model": "nba_spine_v1", "edge_claimed": False,
           "features_added": SP.FEATURES_V1[len(SP.FEATURES):], **base,
           "honest_note": "Calibration/sharpness only, no dollars/edge. Adds team identity + K-asof (season-prior) team-strength to v0's state-only features; sim2_cells baseline still fit on FIT_SEASONS (2 seasons), a harder bar than v1's single discovery season."}
    _write_versioned(doc, preds, EVAL_OUT_V1, PREDS_OUT_V1)
    return doc


def run_v2() -> Dict[str, Any]:
    """v2 = v0 features + possession-grain lineup-identity rates (2024-25-
    fitted, fallback ladder), verdicted vs v0 (spec: vs v0/sim2_cells/marginal)."""
    state_df = SP.build_state_frame_v2()
    base, preds, test_df = _run_version(state_df, SP.FEATURES_V2, "spine_v2", SP.FEATURES, "spine_v0")
    fallback_dist = {
        "off_lineup_tier_v2": test_df["off_lineup_tier_v2"].value_counts(normalize=True).round(4).to_dict(),
        "def_lineup_tier_v2": test_df["def_lineup_tier_v2"].value_counts(normalize=True).round(4).to_dict(),
    }
    doc = {"model": "nba_spine_v2", "edge_claimed": False,
           "features_added": SP.FEATURES_V2[len(SP.FEATURES):], **base,
           "lineup_fallback_distribution": fallback_dist,
           "honest_note": "Calibration/sharpness only, no dollars/edge. Adds possession-count-shrunk lineup-identity offense/defense rates (2024-25-fitted, lineup->player->team fallback ladder) to v0's state-only features; sim2_cells baseline still fit on FIT_SEASONS (2 seasons), a harder bar than v2's single discovery season."}
    _write_versioned(doc, preds, EVAL_OUT_V2, PREDS_OUT_V2)
    return doc


def _ledger_claims_versioned(doc: Dict[str, Any], model_label: str, prev_label: str,
                              context: str, eval_path: Path) -> None:
    """Ledger a version's verdict claims in ONE batch call (rails: batch API)."""
    from scripts.platformkit.omni import claims_ledger as CL
    v, vprev, n = doc["seed_a"]["verdict"], doc["verdict_vs_prev"], doc["seed_a"]["n_test"]
    stable = doc["seed_stability"]["seed_stable"]
    specs = (
        (f"{model_label} next-possession CRPS vs {prev_label} on held-out 2025-26", "crps_vs_prev", vprev),
        (f"{model_label} next-possession log-loss vs {prev_label} on held-out 2025-26", "log_loss_vs_prev", vprev),
        (f"{model_label} next-possession CRPS vs sim2-cells engine on held-out 2025-26", "crps_vs_sim2_cells", v),
    )
    claims = [{
        "statement": f"{statement}: {block[key]} (n={n}, seed_stable={stable})", "type": "conditional",
        "scope": {"sport": "basketball_nba", "context": context, "seasons": [TEST_SEASON]},
        "effect": {"metric": key, "verdict": block[key], "n": n}, "evidence": {"artifact": str(eval_path)},
    } for statement, key, block in specs]
    CL.add_claims_batch(claims)


def _main() -> int:
    # v0 already ran+ledgered (SPINE-1, eval_2025_26.json, commit 5caee20d).
    doc1 = run_v1()
    print("spine_eval v1: n_test=%d verdict_vs_prev=%s seed_stable=%s" % (
        doc1["seed_a"]["n_test"], doc1["verdict_vs_prev"], doc1["seed_stability"]["seed_stable"]))
    _ledger_claims_versioned(doc1, "spine v1 (identity+K-asof)", "spine v0", "next_possession_spine_v1", EVAL_OUT_V1)

    doc2 = run_v2()
    print("spine_eval v2: n_test=%d verdict_vs_prev=%s seed_stable=%s fallback_off=%s" % (
        doc2["seed_a"]["n_test"], doc2["verdict_vs_prev"], doc2["seed_stability"]["seed_stable"],
        doc2["lineup_fallback_distribution"]["off_lineup_tier_v2"]))
    _ledger_claims_versioned(doc2, "spine v2 (lineup identity)", "spine v0", "next_possession_spine_v2", EVAL_OUT_V2)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
