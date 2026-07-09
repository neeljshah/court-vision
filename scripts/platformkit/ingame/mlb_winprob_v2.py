"""scripts.platformkit.ingame.mlb_winprob_v2 -- state-conditioned MLB live win-prob model
(K=1) vs the pooled-model baseline AND the live Kalshi market on the SAME 125-game
corpus that showed the pooled model behind the market (Brier 0.2295 vs 0.1898 / 40,218
ticks, commit 0eee3708, data/frontend/ops/mlb_state_bucket_benchmark.json).

DESIGN (declared before running):
SPLIT: train mlb_pitch_states__{2022,2023,2024}.parquet (2021 file is ABSENT on disk --
2022 is earliest available, so train window is 2022-2024, not 2021-2024 as scoped).
Validate/calibrate on 2025. TEST = the same 125-game 2026 grade corpus
state_bucket_benchmark used (discover_grade_files + live_grade._load_pairs +
MlbOutcomeResolver + bucket fns, reused unchanged). 2026 NEVER enters train/val --
mlb_winprob_v2_features.load_training_seasons() hard-asserts this.

FEATURES (must exist in BOTH the training parquet AND a live tick's state_summary, or
the model can't be scored on the eval corpus): inning, half_bottom, outs, base_state
(0-7, bit0=1st/bit1=2nd/bit2=3rd per ingame_baseout_mlb.parse_baseout), balls, strikes,
score_margin (home-away), frac_elapsed. ASSUMPTION: train's `runners` col and eval's
`base` field share this bit convention (both trace to ESPN situation parsing; not
independently bit-verified here) -- flagged in honest_note. Feature builders live in
the sibling mlb_winprob_v2_features.py (LOC-cap split, zero behavior change).

DROPPED vs the original brief, with reasons (never silently 0-filled):
  * p0 (pregame prior): in the training parquet but NOT reconstructable for the 125-game
    eval corpus -- live_p0 only reads TODAY's latest.json snapshot, not a historical
    per-game store. Fits WITHOUT a prior -- a real gap vs a model that could see p0.
  * total_runs: training parquet stores only state_diff (margin), not both scores.
  * sp_pitch_count_prior / velo_decline_vs_early: this SP-fatigue class is already
    CLOSED (honest REJECT 2026-07-04, memory mlb_sp_fatigue_closed) -- not re-attempted.

MODEL: HistGradientBoostingClassifier on the 8 features, isotonic-calibrated on 2025.

EVAL: pooled + per-bucket (state_bucket_benchmark phase|margin buckets) Brier/log-loss/
ECE for NEW vs OLD (pooled) model vs MARKET, reusing sb._score_bucket's game-clustered
bootstrap verdict unchanged. Ticks missing outs/base/count (pre-deep-state captures) are
dropped, counted honestly, never guessed.

HONESTY: calibration measurement only; edge_claimed always False; no $/ROI field. NO
LIVE WIRING -- if the CI shows the new model ahead, wiring it in is a follow-up decision.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; OMP/BLAS
threads capped to 4; never writes data/registry/; never flips a flag; never edits src/
kernel/ api/ intel/ scripts/team_system/ or live_grade.py/state_bucket_benchmark.py;
parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v2.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

import scripts.platformkit.ingame.state_bucket_benchmark as sb
from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.ingame import mlb_winprob_v2_features as feat
from scripts.platformkit.ingame.ingame_clv_aggregate import discover_grade_files
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_winprob_v2_benchmark.json"
DEFAULT_MODEL_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v2.pkl"
DEFAULT_META_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v2_meta.json"

DEFAULT_TRAIN_SEASONS: Tuple[int, ...] = (2022, 2023, 2024)
DEFAULT_VAL_SEASON = 2025
FEATURE_NAMES = feat.FEATURE_NAMES

# -- train + calibrate -- #
def train_model(train_seasons: Sequence[int] = DEFAULT_TRAIN_SEASONS,
                val_season: int = DEFAULT_VAL_SEASON,
                data_dir: Optional[Path] = None
                ) -> Tuple[HistGradientBoostingClassifier, IsotonicRegression, Dict[str, Any]]:
    """Fit HGB on train seasons, isotonic-calibrate on val_season. Never touches 2026."""
    train_df, missing_train = feat.load_training_seasons(train_seasons, data_dir)
    val_df, missing_val = feat.load_training_seasons((val_season,), data_dir)
    Xtr, ytr, n_drop_tr = feat.train_xy(train_df)
    Xval, yval, n_drop_val = feat.train_xy(val_df)
    clf = HistGradientBoostingClassifier(random_state=42)
    if len(Xtr):
        clf.fit(Xtr, ytr)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(Xval):
        raw_val = clf.predict_proba(Xval)[:, 1]
        iso.fit(raw_val, yval)
    else:  # no val data -> identity calibration (honest no-op, never fabricated)
        iso.fit([0.0, 1.0], [0.0, 1.0])
    meta = {
        "train_seasons": list(train_seasons), "val_season": val_season,
        "missing_train_seasons": missing_train, "missing_val_season": missing_val,
        "n_train_rows": int(len(Xtr)), "n_val_rows": int(len(Xval)),
        "n_train_rows_dropped_unparseable_half": n_drop_tr,
        "n_val_rows_dropped_unparseable_half": n_drop_val,
        "feature_names": list(FEATURE_NAMES), "n_features": len(FEATURE_NAMES),
        "dropped_features": ["p0 (not reconstructable on eval corpus)",
                              "total_runs (not stored train-side)",
                              "sp_pitch_count_prior/velo_decline_vs_early (CLOSED class)"],
    }
    return clf, iso, meta

def predict_proba(clf: HistGradientBoostingClassifier, iso: IsotonicRegression,
                  X: np.ndarray) -> np.ndarray:
    if len(X) == 0:
        return np.zeros(0)
    raw = clf.predict_proba(X)[:, 1]
    return np.clip(iso.predict(raw), 0.0, 1.0)

# -- eval on the 125-game grade corpus -- #
def build_eval_ticks(grade_dir: Optional[Path] = None,
                     resolver: Optional[MlbOutcomeResolver] = None
                     ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Ticks with the 8 model features + old_model_prob/market_prob/outcome/bucket,
    via the SAME loaders state_bucket_benchmark uses (same 125-game corpus). Never raises."""
    res = resolver if resolver is not None else MlbOutcomeResolver()
    files = discover_grade_files(grade_dir, sport="mlb")
    ticks: List[Dict[str, Any]] = []
    counts = {"n_files": len(files), "n_games_resolved": 0, "n_games_unresolved": 0,
              "n_ticks_seen": 0, "n_ticks_missing_state": 0, "n_ticks_used": 0}
    for path in files:
        try:
            pairs = lg._load_pairs(path)
        except Exception as exc:  # noqa: BLE001 -- one bad file is not a crash
            logger.debug("build_eval_ticks: %s failed: %s", path, exc)
            continue
        if not pairs:
            continue
        gid = str(pairs[0].get("game_id", path.stem))
        home_win = res.home_win(gid)
        if home_win is None:
            counts["n_games_unresolved"] += 1
            continue
        counts["n_games_resolved"] += 1
        for r in pairs:
            counts["n_ticks_seen"] += 1
            st = feat.parse_tick_state(r.get("state_summary"))
            if st is None:
                counts["n_ticks_missing_state"] += 1
                continue
            counts["n_ticks_used"] += 1
            bucket = "%s|%s" % (sb.phase_bucket(st["inning"]),
                                sb.margin_bucket(st["home_score"], st["away_score"]))
            row = {"game_id": gid, "bucket": bucket,
                  "old_model_prob": float(r["model_prob"]),
                  "market_prob": float(r["market_prob"]), "outcome": float(home_win)}
            row.update({k: st[k] for k in FEATURE_NAMES})
            ticks.append(row)
    return ticks, counts

def score_new_model(clf: HistGradientBoostingClassifier, iso: IsotonicRegression,
                    ticks: List[Dict[str, Any]]) -> np.ndarray:
    if not ticks:
        return np.zeros(0)
    X = np.array([[t[f] for f in FEATURE_NAMES] for t in ticks], dtype=float)
    return predict_proba(clf, iso, X)

def _side(res: Dict[str, Any]) -> Dict[str, Any]:
    return {"verdict": res["verdict"], "brier_delta_ci95": res["brier_delta_ci95"],
           "mean_abs_gap": res["mean_abs_gap"]}

def _combine_row(name: str, new_res: Dict[str, Any], old_res: Dict[str, Any]) -> Dict[str, Any]:
    return {"bucket": name, "n_ticks": new_res["n_ticks"], "n_games": new_res["n_games"],
           "new_model": new_res["model"], "old_model": old_res["model"],
           "market": new_res["market"], "new_vs_market": _side(new_res),
           "old_vs_market": _side(old_res)}

def build_benchmark(clf: HistGradientBoostingClassifier, iso: IsotonicRegression,
                    grade_dir: Optional[Path] = None,
                    resolver: Optional[MlbOutcomeResolver] = None) -> Dict[str, Any]:
    """Pooled + per-bucket new/old/market comparison on the 125-game corpus (clf/iso
    already fit -- never trained or selected on this data)."""
    ticks, counts = build_eval_ticks(grade_dir, resolver)
    new_probs = score_new_model(clf, iso, ticks)
    new_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, new_probs)]
    old_ticks = [dict(t, model_prob=t["old_model_prob"]) for t in ticks]

    new_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    old_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    for t in new_ticks:
        new_by_bucket.setdefault(t["bucket"], []).append(t)
    for t in old_ticks:
        old_by_bucket.setdefault(t["bucket"], []).append(t)

    bucket_rows = [_combine_row(name, sb._score_bucket(new_by_bucket[name]),
                                sb._score_bucket(old_by_bucket[name]))
                  for name in sorted(new_by_bucket)]
    pooled = _combine_row("pooled", sb._score_bucket(new_ticks), sb._score_bucket(old_ticks))

    doc: Dict[str, Any] = {
        "sport": "mlb", "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v2 (HistGradientBoosting, isotonic-calibrated)",
        "baseline_model": "pooled in-game model (mlb_state_bucket_benchmark, commit 0eee3708)",
        "feature_names": list(FEATURE_NAMES),
        "n_grade_files_mlb": counts["n_files"],
        "n_games_outcome_resolved": counts["n_games_resolved"],
        "n_games_outcome_unresolved": counts["n_games_unresolved"],
        "n_ticks_seen": counts["n_ticks_seen"],
        "n_ticks_missing_state_dropped": counts["n_ticks_missing_state"],
        "n_ticks_used": counts["n_ticks_used"],
        "min_games_for_verdict": sb.MIN_GAMES,
        "buckets": bucket_rows, "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": (
            "Calibration/benchmark measurement only vs the LIVE market price, not a "
            "devigged close. Trained 2022-2024, isotonic-calibrated on 2025, ZERO 2026 "
            "rows in train/val. No p0 (pregame prior) feature -- unavailable "
            "historically for this eval corpus. base_state assumed to share the same "
            "3-bit convention between train's `runners` col and eval's `base` field "
            "(not independently verified). Ticks predating deep base-out enrichment "
            "are dropped, counted, never guessed. No $/ROI/edge claim."),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_winprob_v2_pooled",
            "n": pooled["n_ticks"],
            "baseline_brier": pooled["market"]["brier"] if pooled["market"] else None,
            "improved_brier": pooled["new_model"]["brier"] if pooled["new_model"] else None,
            "baseline_ece": pooled["market"]["ece"] if pooled["market"] else None,
            "improved_ece": pooled["new_model"]["ece"] if pooled["new_model"] else None,
        }]},
    }
    return doc

def save_model(clf: HistGradientBoostingClassifier, iso: IsotonicRegression,
              train_meta: Dict[str, Any], model_path: Optional[Path] = None,
              meta_path: Optional[Path] = None) -> Tuple[Path, Path]:
    """Save pkl + _meta.json; asserts fitted feature count == declared meta count
    (prop-model-artifact-drift lesson: pkl/meta must never silently disagree)."""
    p_pkl = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
    p_meta = Path(meta_path) if meta_path is not None else DEFAULT_META_PATH
    p_pkl.parent.mkdir(parents=True, exist_ok=True)
    n_features_fit = int(getattr(clf, "n_features_in_", len(FEATURE_NAMES)))
    assert n_features_fit == train_meta["n_features"], (
        "mlb_winprob_v2 pkl/meta feature-count drift: fitted=%d meta=%d"
        % (n_features_fit, train_meta["n_features"]))
    with p_pkl.open("wb") as fh:
        pickle.dump({"model": clf, "isotonic": iso, "feature_names": list(FEATURE_NAMES)}, fh)
    p_meta.write_text(json.dumps(train_meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return p_pkl, p_meta

def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Optional[MlbOutcomeResolver] = None,
                    history_path: Optional[Path] = None,
                    train_seasons: Sequence[int] = DEFAULT_TRAIN_SEASONS,
                    val_season: int = DEFAULT_VAL_SEASON,
                    data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Train, benchmark, write JSON + best-effort scoreboard append, save the model."""
    clf, iso, train_meta = train_model(train_seasons, val_season, data_dir)
    doc = build_benchmark(clf, iso, grade_dir, resolver)
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
    save_model(clf, iso, train_meta)
    return doc

if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"pooled": result["pooled"], "n_buckets": len(result["buckets"]),
                      "n_ticks_used": result["n_ticks_used"],
                      "honest_note": result["honest_note"]}, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_OUT_PATH", "DEFAULT_MODEL_PATH", "DEFAULT_META_PATH",
    "DEFAULT_TRAIN_SEASONS", "DEFAULT_VAL_SEASON", "FEATURE_NAMES",
    "train_model", "predict_proba", "build_eval_ticks",
    "score_new_model", "build_benchmark", "save_model", "write_benchmark",
]
