"""scripts.platformkit.ingame.mlb_winprob_v3 -- adds a pregame MARKET-PRICE prior anchor
to v2 (commit 3aac11e8), an honest REJECT on the 125-game 2026 corpus (pooled Brier 0.2349
vs market 0.1898) that was well-calibrated in-domain (2025 val 0.154) but had NO pregame
prior and overshot to 0.970 in late|leading_big where realized was 0.682 -- prior-source
loading/matching lives in mlb_winprob_v3_prior.py (LOC-cap split).

DESIGN (K=2, declared before running): spec (a) = v2's 8 state features + prior_logit +
has_prior (10-feature HistGB, isotonic on 2025, else identical to v2's recipe). spec (b) =
logit-blend sigmoid(alpha*logit(p_state) + beta*logit(prior)), p_state = v2's own fully
trained 8-feature model (wp.train_model/predict_proba reused UNCHANGED), alpha/beta a
2-coefficient no-intercept logistic regression fit on 2025 VALIDATION ONLY. Selection:
lower 2025-val Brier wins; the loser is never scored on 2026 ("evaluate the winner once").
2026 never enters train/val (feat.load_training_seasons's hard guard, reused unchanged).

EVAL: identical structure to v2 -- pooled + per-bucket new(winner)/old(pooled)/market
Brier/log-loss/ECE + game-clustered bootstrap verdict (sb._score_bucket, wp._combine_row,
reused unchanged), plus a late|leading_big mean-pred-vs-realized diagnostic (old vs new).

HONESTY: calibration measurement only; edge_claimed always False; no $/ROI field. NO LIVE
WIRING. Prior coverage reported per split -- train PM matching is sparse (no Polymarket
MLB data on disk for 2022 or 2024); documented, not hidden.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; OMP/BLAS
threads capped to 4; never writes data/registry/; never flips a flag; never edits src/
kernel/ api/ intel/ scripts/team_system/ or mlb_winprob_v2.py / live_grade.py /
state_bucket_benchmark.py / ingame_outcome_label.py; parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v3.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import json
import logging
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

import scripts.platformkit.ingame.mlb_winprob_v2 as wp
import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v3_prior as prior_mod
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_winprob_v3_benchmark.json"
DEFAULT_MODEL_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v3.pkl"
DEFAULT_META_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v3_meta.json"

DEFAULT_TRAIN_SEASONS: Tuple[int, ...] = wp.DEFAULT_TRAIN_SEASONS
DEFAULT_VAL_SEASON = wp.DEFAULT_VAL_SEASON
FEATURE_NAMES_V3: Tuple[str, ...] = feat.FEATURE_NAMES + prior_mod.FEATURE_NAMES_PRIOR

def _valid_rows(df: pd.DataFrame) -> pd.Series:
    """Same half_inning_label mask feat.train_xy applies internally -- computed here too
    so the surviving rows can be aligned with the extra prior_home/has_prior columns."""
    half = df["half_inning_label"].astype(str).str.extract(r"^(top|bottom)(\d+)$")
    return half[1].notna()

def train_xy_v3(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, int]:
    """8 state features (feat.train_xy, reused unchanged) + prior_logit + has_prior."""
    if df.empty:
        return np.zeros((0, len(FEATURE_NAMES_V3))), np.zeros(0), 0
    ok = _valid_rows(df)
    n_dropped = int((~ok).sum())
    d = df.loc[ok]
    X8, y, _ = feat.train_xy(d)  # d already filtered -> feat.train_xy's own mask is a no-op
    prior_logit = prior_mod._logit(d["prior_home"].astype(float).to_numpy())
    has_prior = d["has_prior"].astype(float).to_numpy()
    X = np.column_stack([X8, prior_logit, has_prior])
    return X, y, n_dropped

def fit_blend(p_state: np.ndarray, prior_home: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """alpha, beta for sigmoid(alpha*logit(p_state) + beta*logit(prior)), 2-coefficient
    no-intercept logistic regression. Degenerate y (single class / empty) -> honest
    pass-through (alpha=1, beta=0), never a fabricated fit."""
    if len(y) == 0 or len(set(y.tolist())) < 2:
        return 1.0, 0.0
    X = np.column_stack([prior_mod._logit(p_state), prior_mod._logit(prior_home)])
    lr = LogisticRegression(fit_intercept=False)
    lr.fit(X, y)
    return float(lr.coef_[0][0]), float(lr.coef_[0][1])

def blend_predict(p_state: np.ndarray, prior_home: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    if len(p_state) == 0:
        return np.zeros(0)
    z = alpha * prior_mod._logit(p_state) + beta * prior_mod._logit(prior_home)
    return 1.0 / (1.0 + np.exp(-z))

# -- train both specs, select by 2025-validation Brier -- #
def train_specs(train_seasons: Sequence[int] = DEFAULT_TRAIN_SEASONS,
                val_season: int = DEFAULT_VAL_SEASON,
                data_dir: Optional[Path] = None,
                pm_dirs: Sequence[Path] = prior_mod.DEFAULT_PM_DIRS) -> Dict[str, Any]:
    pm_index, pm_counts = prior_mod.build_pm_prior_index(pm_dirs)
    train_df, missing_train = feat.load_training_seasons(train_seasons, data_dir)
    val_df, missing_val = feat.load_training_seasons((val_season,), data_dir)
    train_df, tr_prior_counts = prior_mod.attach_priors(train_df, pm_index)
    val_df, val_prior_counts = prior_mod.attach_priors(val_df, pm_index)

    # spec (a): 10-feature HGB, isotonic-calibrated on val
    Xtr, ytr, n_drop_tr = train_xy_v3(train_df)
    Xval, yval, n_drop_val = train_xy_v3(val_df)
    clf_a = HistGradientBoostingClassifier(random_state=42)
    if len(Xtr):
        clf_a.fit(Xtr, ytr)
    iso_a = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(Xval):
        iso_a.fit(clf_a.predict_proba(Xval)[:, 1], yval)
    else:
        iso_a.fit([0.0, 1.0], [0.0, 1.0])
    probs_a_val = wp.predict_proba(clf_a, iso_a, Xval)

    # spec (b): v2's own 8-feature model reused unchanged + logit-blend fit on val only
    clf_state, iso_state, meta_state = wp.train_model(train_seasons, val_season, data_dir)
    ok_val = _valid_rows(val_df)
    d_val = val_df.loc[ok_val]
    X8val, yval8, _ = feat.train_xy(d_val)
    p_state_val = wp.predict_proba(clf_state, iso_state, X8val)
    prior_val = d_val["prior_home"].astype(float).to_numpy()
    alpha, beta = fit_blend(p_state_val, prior_val, yval8)
    probs_b_val = blend_predict(p_state_val, prior_val, alpha, beta)

    brier_a = float(wp.sb.brier(probs_a_val, yval)) if len(Xval) else float("nan")
    brier_b = float(wp.sb.brier(probs_b_val, yval8)) if len(X8val) else float("nan")
    candidates = [(n, b) for n, b in (("a", brier_a), ("b", brier_b)) if not math.isnan(b)]
    winner = min(candidates, key=lambda kv: kv[1])[0] if candidates else "a"

    return {
        "clf_a": clf_a, "iso_a": iso_a, "clf_state": clf_state, "iso_state": iso_state,
        "alpha": alpha, "beta": beta, "winner": winner,
        "val_brier_spec_a": brier_a, "val_brier_spec_b": brier_b,
        "meta": {
            "train_seasons": list(train_seasons), "val_season": val_season,
            "missing_train_seasons": missing_train, "missing_val_season": missing_val,
            "n_train_rows": int(len(Xtr)), "n_val_rows": int(len(Xval)),
            "feature_names_spec_a": list(FEATURE_NAMES_V3),
            "prior_coverage": {
                "pm_index": pm_counts, "train": tr_prior_counts, "val": val_prior_counts,
            },
        },
    }

# -- eval on the 125-game 2026 grade corpus (winner only) -- #
def build_benchmark(bundle: Dict[str, Any], grade_dir: Optional[Path] = None,
                    resolver: Any = None, kalshi_dir: Optional[Path] = None) -> Dict[str, Any]:
    ticks, counts, eval_prior_counts = prior_mod.build_eval_ticks_with_prior(
        wp.build_eval_ticks, grade_dir, resolver, kalshi_dir)
    if bundle["winner"] == "a":
        X10 = np.array([[t[f] for f in feat.FEATURE_NAMES] +
                        [prior_mod._logit(t["prior_home"]).item(), float(t["has_prior"])]
                        for t in ticks], dtype=float) if ticks else np.zeros((0, len(FEATURE_NAMES_V3)))
        winner_probs = wp.predict_proba(bundle["clf_a"], bundle["iso_a"], X10)
    else:
        p_state = wp.score_new_model(bundle["clf_state"], bundle["iso_state"], ticks)
        prior_arr = np.array([t["prior_home"] for t in ticks], dtype=float)
        winner_probs = blend_predict(p_state, prior_arr, bundle["alpha"], bundle["beta"])

    new_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, winner_probs)]
    old_ticks = [dict(t, model_prob=t["old_model_prob"]) for t in ticks]
    new_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    old_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    for t in new_ticks:
        new_by_bucket.setdefault(t["bucket"], []).append(t)
    for t in old_ticks:
        old_by_bucket.setdefault(t["bucket"], []).append(t)

    bucket_rows = [wp._combine_row(name, wp.sb._score_bucket(new_by_bucket[name]),
                                   wp.sb._score_bucket(old_by_bucket[name]))
                  for name in sorted(new_by_bucket)]
    pooled = wp._combine_row("pooled", wp.sb._score_bucket(new_ticks), wp.sb._score_bucket(old_ticks))
    ll_big = "late|leading_big"
    diagnostic = {
        "bucket": ll_big,
        "new_model": prior_mod.mean_pred_vs_realized(new_by_bucket.get(ll_big, [])),
        "old_model": prior_mod.mean_pred_vs_realized(old_by_bucket.get(ll_big, [])),
    }

    doc: Dict[str, Any] = {
        "sport": "mlb", "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v3 (spec %s: %s)" % (
            bundle["winner"],
            "10-feature HistGB+prior, isotonic" if bundle["winner"] == "a"
            else "logit-blend(v2_state, market_prior)"),
        "baseline_model": "pooled in-game model (mlb_state_bucket_benchmark, commit 0eee3708)",
        "spec_selection": {
            "val_brier_spec_a": bundle["val_brier_spec_a"], "val_brier_spec_b": bundle["val_brier_spec_b"],
            "winner": bundle["winner"], "alpha": bundle["alpha"], "beta": bundle["beta"],
        },
        "feature_names": list(FEATURE_NAMES_V3),
        "n_grade_files_mlb": counts["n_files"],
        "n_games_outcome_resolved": counts["n_games_resolved"],
        "n_games_outcome_unresolved": counts["n_games_unresolved"],
        "n_ticks_seen": counts["n_ticks_seen"],
        "n_ticks_missing_state_dropped": counts["n_ticks_missing_state"],
        "n_ticks_used": counts["n_ticks_used"],
        "prior_coverage_eval": eval_prior_counts,
        "prior_coverage_train_val": bundle["meta"]["prior_coverage"],
        "min_games_for_verdict": wp.sb.MIN_GAMES,
        "buckets": bucket_rows, "pooled": pooled,
        "late_leading_big_diagnostic": diagnostic,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": (
            "Calibration/benchmark measurement only vs the LIVE market price, not a "
            "devigged close. Prior anchor = pregame market price (Polymarket train/val, "
            "Kalshi eval), NEVER a fabricated number: unmatched games fall back to "
            "prior=0.5 with has_prior=False, reported in prior_coverage_*. Train PM "
            "coverage is SPARSE (no Polymarket MLB data on disk for 2022 or 2024) -- "
            "documented, not hidden. Spec chosen by 2025-val Brier only; the losing spec "
            "was never scored on the 2026 corpus. No $/ROI/edge claim."),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_winprob_v3_pooled",
            "n": pooled["n_ticks"],
            "baseline_brier": pooled["market"]["brier"] if pooled["market"] else None,
            "improved_brier": pooled["new_model"]["brier"] if pooled["new_model"] else None,
            "baseline_ece": pooled["market"]["ece"] if pooled["market"] else None,
            "improved_ece": pooled["new_model"]["ece"] if pooled["new_model"] else None,
        }]},
    }
    return doc

def save_model(bundle: Dict[str, Any], model_path: Optional[Path] = None,
              meta_path: Optional[Path] = None) -> Tuple[Path, Path]:
    """Save pkl + _meta.json; asserts fitted feature count == declared meta count,
    shape depends on which spec won (prop-model-artifact-drift lesson)."""
    p_pkl = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
    p_meta = Path(meta_path) if meta_path is not None else DEFAULT_META_PATH
    p_pkl.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(bundle["meta"])
    meta["winner"] = bundle["winner"]
    if bundle["winner"] == "a":
        n_features_fit = int(getattr(bundle["clf_a"], "n_features_in_", len(FEATURE_NAMES_V3)))
        assert n_features_fit == len(FEATURE_NAMES_V3), (
            "mlb_winprob_v3 pkl/meta feature-count drift: fitted=%d meta=%d"
            % (n_features_fit, len(FEATURE_NAMES_V3)))
        meta["n_features"] = len(FEATURE_NAMES_V3)
        payload = {"spec": "a", "clf": bundle["clf_a"], "iso": bundle["iso_a"],
                  "feature_names": list(FEATURE_NAMES_V3)}
    else:
        meta["n_features"] = 2  # blend inputs: logit(p_state), logit(prior)
        payload = {"spec": "b", "clf_state": bundle["clf_state"], "iso_state": bundle["iso_state"],
                  "alpha": bundle["alpha"], "beta": bundle["beta"],
                  "feature_names": list(feat.FEATURE_NAMES) + ["prior_home"]}
    with p_pkl.open("wb") as fh:
        pickle.dump(payload, fh)
    p_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return p_pkl, p_meta

def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Optional[MlbOutcomeResolver] = None,
                    history_path: Optional[Path] = None,
                    train_seasons: Sequence[int] = DEFAULT_TRAIN_SEASONS,
                    val_season: int = DEFAULT_VAL_SEASON,
                    data_dir: Optional[Path] = None,
                    kalshi_dir: Optional[Path] = None) -> Dict[str, Any]:
    res = resolver if resolver is not None else MlbOutcomeResolver()
    bundle = train_specs(train_seasons, val_season, data_dir)
    doc = build_benchmark(bundle, grade_dir, res, kalshi_dir)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    try:
        from scripts.platformkit import scoreboard_history as sh
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_benchmark: scoreboard_history append skipped: %s", exc)
    save_model(bundle)
    return doc

if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"spec_selection": result["spec_selection"], "pooled": result["pooled"],
                      "late_leading_big_diagnostic": result["late_leading_big_diagnostic"],
                      "n_ticks_used": result["n_ticks_used"],
                      "honest_note": result["honest_note"]}, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_OUT_PATH", "DEFAULT_MODEL_PATH", "DEFAULT_META_PATH",
    "DEFAULT_TRAIN_SEASONS", "DEFAULT_VAL_SEASON", "FEATURE_NAMES_V3",
    "train_xy_v3", "fit_blend", "blend_predict", "train_specs",
    "build_eval_ticks_with_prior", "build_benchmark", "save_model", "write_benchmark",
]
