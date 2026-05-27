"""backtest_rs_wf_ast_reb.py — Iter 10b: WF gate for AST + REB using RS folds.

Extends the playoff-fold WF gate to include the new regular-season fold
data from regular_season_2024_25_oddsapi.csv (4 game-nights: Dec-20, Jan-25,
Feb-28, Apr-05).

Reports per-fold ROI for AST and REB across RS folds (and playoff folds
from playoffs_2024_canonical.csv where stat data exists).

Decision rule (same as backtest_holdout_wf.py):
  SHIP  = 3+/4 folds positive ROI AND mean_roi > +0.5%
  REVERT = 2+ folds negative ROI
  HOLD  = mixed signal
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import (  # noqa: E402
    feature_columns,
    feature_columns_for,
    apply_garbage_time_haircut,
)
from src.prediction.prop_quantiles import _inverse  # noqa: E402

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


# ─── paths ───────────────────────────────────────────────────────────────────

PLAYOFF_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                           "playoffs_2024_canonical.csv")
RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2024_25_oddsapi.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
THRESHOLD = 0.5

# Stats to evaluate this run
STATS_TO_EVAL = ["ast", "reb"]
BLEND_STATS = {"pts", "ast"}
LGB_STATS = {"reb"}

# RS folds: one per game-night in our 4-date RS sample
RS_FOLDS: List[Tuple[str, str, str]] = [
    ("rs_fold1_dec20",  "2024-12-20", "2024-12-20"),
    ("rs_fold2_jan25",  "2025-01-25", "2025-01-25"),
    ("rs_fold3_feb28",  "2025-02-28", "2025-02-28"),
    ("rs_fold4_apr05",  "2025-04-05", "2025-04-05"),
]

# Playoff folds (from iter5 — use these as additional context if data available)
PLAYOFF_FOLDS: List[Tuple[str, str, str]] = [
    ("pl_fold1_early_r1",   "2024-04-21", "2024-04-28"),
    ("pl_fold2_late_r1",    "2024-04-29", "2024-05-06"),
    ("pl_fold3_round2",     "2024-05-07", "2024-05-14"),
    ("pl_fold4_semifinals", "2024-05-15", "2024-05-23"),
]


# ─── artifact loaders ────────────────────────────────────────────────────────

_META_CACHE: Optional[Dict] = None

def _meta() -> Dict:
    global _META_CACHE
    if _META_CACHE is None:
        meta_path = os.path.join(OOS_DIR, "_meta.json")
        _META_CACHE = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    return _META_CACHE


def _q50_feature_columns(stat: str, model=None) -> List[str]:
    current = feature_columns()
    if model is not None:
        n_expected = getattr(model, "n_features_in_", None) or getattr(model, "n_features_", None)
        if n_expected is not None:
            if n_expected == len(current):
                return current
            saved = _meta().get("stats", {}).get(stat, {}).get("feature_columns", [])
            if saved and len(saved) == n_expected:
                return saved
            return current[:n_expected]
    saved = _meta().get("stats", {}).get(stat, {}).get("feature_columns")
    if saved:
        return saved
    return current


def _load_blend_artifacts(stat: str) -> Dict:
    import joblib, xgboost as xgb_lib
    if stat == "ast":
        import src.prediction.prop_pergame  # noqa
    arts: Dict = {}
    for key, path, loader in [
        ("xgb",        os.path.join(OOS_DIR, f"props_pg_{stat}.json"),             "xgb"),
        ("lgb",        os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"),          "joblib"),
        ("mlp",        os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"),          "joblib"),
        ("mlp_scaler", os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"),   "joblib"),
        ("cal",        os.path.join(OOS_DIR, f"calibration_pergame_{stat}.joblib"), "joblib"),
    ]:
        if not os.path.exists(path):
            arts[key] = None
            continue
        if loader == "xgb":
            m = xgb_lib.XGBRegressor()
            m.load_model(path)
            arts[key] = m
        else:
            arts[key] = joblib.load(path)
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    arts["weights"] = None
    if os.path.exists(weights_path):
        try:
            arts["weights"] = json.load(open(weights_path, encoding="utf-8")).get(stat)
        except Exception:
            pass
    return arts


def _load_q50_artifact(stat: str):
    if stat in LGB_STATS:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"OOS artifact missing: {path}")
        return joblib.load(path)
    else:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"OOS artifact missing: {path}")
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m


# ─── prediction helpers ───────────────────────────────────────────────────────

def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _inv_log1p(v: float) -> float:
    return max(0.0, float(np.expm1(v)))


def _predict_blend(stat: str, arts: Dict, feat_row: Dict[str, float]) -> Optional[float]:
    cols = feature_columns_for(stat, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = arts.get("weights") or {}
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    inv = _inv_sqrt if stat == "pts" else _inv_log1p
    parts: List[float] = []
    if arts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * inv(float(arts["xgb"].predict(X)[0])))
    if arts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * inv(float(arts["lgb"].predict(X)[0])))
    if arts.get("mlp") is not None and arts.get("mlp_scaler") is not None and w_mlp > 0:
        Xs = arts["mlp_scaler"].transform(X)
        parts.append(w_mlp * inv(float(arts["mlp"].predict(Xs)[0])))
    if not parts:
        return None
    pred = float(sum(parts))
    cal = arts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)
    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, stat, hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, stat, model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


def _predict_q50(stat: str, model, feat_row: Dict[str, float]) -> Optional[float]:
    cols = _q50_feature_columns(stat, model)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ─── single-fold runner ───────────────────────────────────────────────────────

def _run_fold(
    stat: str,
    fold_id: str,
    window_start: str,
    window_end: str,
    all_csv_rows: List[dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict,
    model_arts,
    is_blend: bool,
) -> Dict:
    window_rows = [
        r for r in all_csv_rows
        if r.get("stat", "").lower() == stat and window_start <= r["date"] <= window_end
    ]
    if not window_rows:
        return {
            "fold_id": fold_id, "window_start": window_start, "window_end": window_end,
            "stat": stat, "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "hit_rate": None, "roi_pct": None, "mae_actual": None,
            "skip_reasons": {"no_rows": 1}, "status": "SKIP_NO_ROWS",
        }

    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: List[float] = []

    for r in window_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            pid = _resolve_player_id(r["player"])
            name2pid[r["player"]] = pid
        if pid is None:
            skip["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue
        try:
            if is_blend:
                pred = _predict_blend(stat, model_arts, feat)
            else:
                pred = _predict_q50(stat, model_arts, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skip["model_none"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)
        n_pred += 1
        mae_a.append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    profit = _odds_to_decimal_profit(-110)
    roi_units = wins * profit - (n_bets - wins) * 1.0 if n_bets else 0.0
    hit = wins / n_bets if n_bets else None
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else None

    return {
        "fold_id": fold_id,
        "window_start": window_start,
        "window_end": window_end,
        "stat": stat,
        "n_pred": n_pred,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": round(hit, 4) if hit is not None else None,
        "roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "mae_actual": round(sum(mae_a) / len(mae_a), 4) if mae_a else None,
        "skip_reasons": dict(skip),
        "status": "OK" if n_bets > 0 else "SKIP_NO_BETS",
    }


# ─── decision ────────────────────────────────────────────────────────────────

def _wf_decision(fold_results: List[Dict]) -> Tuple[str, Dict]:
    valid = [f for f in fold_results if f["roi_pct"] is not None and f["n_bets"] >= 5]
    if not valid:
        return "INCONCLUSIVE", {}
    rois = [f["roi_pct"] for f in valid]
    n_pos = sum(1 for r in rois if r > 0.0)
    mean_roi = sum(rois) / len(rois)
    std_roi = float(np.std(rois)) if len(rois) > 1 else 0.0
    mean_hit = sum(f["hit_rate"] for f in valid if f["hit_rate"] is not None) / len(valid)
    mae_vals = [f["mae_actual"] for f in valid if f["mae_actual"] is not None]
    mean_mae = sum(mae_vals) / len(mae_vals) if mae_vals else None
    agg = {
        "n_valid_folds": len(valid),
        "n_pos_roi": n_pos,
        "mean_roi": round(mean_roi, 3),
        "std_roi": round(std_roi, 3),
        "mean_hit": round(mean_hit, 4),
        "mean_mae": round(mean_mae, 4) if mean_mae else None,
        "fold_rois": [f["roi_pct"] for f in fold_results],
        "fold_bets": [f["n_bets"] for f in fold_results],
    }
    if len(valid) < 2:
        decision = "INCONCLUSIVE"
    elif n_pos >= 3 and mean_roi > 0.5:
        decision = "SHIP"
    elif sum(1 for r in rois if r < 0.0) >= 2:
        decision = "REVERT"
    else:
        decision = "HOLD"
    return decision, agg


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t_total = time.time()
    print("\n" + "=" * 70)
    print("  Iter 10b — RS WF Gate: AST + REB")
    print("  RS folds: Dec-20, Jan-25, Feb-28, Apr-05 (new data)")
    print("  Playoff folds: Apr-May 2024 (existing data)")
    print("=" * 70)

    # Load all CSV rows
    all_rows: List[dict] = []
    if os.path.exists(PLAYOFF_CSV):
        with open(PLAYOFF_CSV, encoding="utf-8") as fh:
            playoff_rows = list(csv.DictReader(fh))
        all_rows.extend(playoff_rows)
        print(f"  Playoff CSV: {len(playoff_rows)} rows")
    if os.path.exists(RS_CSV):
        with open(RS_CSV, encoding="utf-8") as fh:
            rs_rows = list(csv.DictReader(fh))
        all_rows.extend(rs_rows)
        print(f"  RS CSV: {len(rs_rows)} rows")
    print(f"  Combined: {len(all_rows)} rows")

    # Per-stat counts
    from collections import Counter
    stat_counts = Counter(r.get("stat", "?") for r in all_rows)
    print(f"  Rows by stat: {dict(sorted(stat_counts.items()))}")

    # Shared caches
    name2pid: Dict[str, Optional[int]] = {}
    row_cache: Dict = {}

    all_results: Dict[str, Dict] = {}

    # Fold definitions: RS folds are the PRIMARY new addition
    rs_fold_ids = {f[0] for f in RS_FOLDS}
    all_folds = RS_FOLDS + PLAYOFF_FOLDS

    for stat in STATS_TO_EVAL:
        is_blend = stat in BLEND_STATS
        print(f"\n{'='*70}")
        print(f"  STAT: {stat.upper()}  ({'blend' if is_blend else 'q50-lgb'})")
        print(f"{'='*70}")

        try:
            if is_blend:
                model_arts = _load_blend_artifacts(stat)
                miss = [k for k in ("xgb", "lgb", "weights") if model_arts.get(k) is None]
                if miss:
                    print(f"  [skip] missing blend artifacts: {miss}")
                    all_results[stat] = {"decision": "SKIP_NO_ARTIFACT", "folds": [], "agg": {}}
                    continue
            else:
                model_arts = _load_q50_artifact(stat)
        except FileNotFoundError as e:
            print(f"  [skip] {e}")
            all_results[stat] = {"decision": "SKIP_NO_ARTIFACT", "folds": [], "agg": {}}
            continue

        fold_results: List[Dict] = []
        for fold_id, wstart, wend in all_folds:
            source = "RS" if fold_id in rs_fold_ids else "PL"
            t_fold = time.time()
            fr = _run_fold(stat, fold_id, wstart, wend, all_rows, name2pid,
                           row_cache, model_arts, is_blend)
            elapsed_f = time.time() - t_fold
            roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "N/A"
            hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "N/A"
            skip_str = str(fr.get("skip_reasons", {})) if fr.get("skip_reasons") else ""
            print(f"  [{source}] {fold_id:<22} n_pred={fr['n_pred']:>4}  n_bets={fr['n_bets']:>4}"
                  f"  hit={hit_str:>7}  ROI={roi_str:>8}  ({elapsed_f:.1f}s)")
            if skip_str and skip_str != "{}":
                print(f"         skip={skip_str}")
            fold_results.append(fr)

        # Decision based on RS folds only (new data)
        rs_folds_results = [f for f in fold_results if f["fold_id"] in rs_fold_ids]
        decision, agg = _wf_decision(rs_folds_results)
        print(f"\n  DECISION (RS folds only): {decision}")
        if agg:
            print(f"  mean_roi={agg['mean_roi']:+.2f}%  std_roi={agg['std_roi']:.2f}%"
                  f"  pos_folds={agg['n_pos_roi']}/{agg['n_valid_folds']}")
            print(f"  mean_mae={agg.get('mean_mae', 'N/A')}  mean_hit={agg['mean_hit']:.4f}")

        all_results[stat] = {
            "decision": decision,
            "folds": fold_results,
            "agg": agg,
            "rs_folds_only": rs_folds_results,
        }

    # ─── summary table ────────────────────────────────────────────────────────
    total_elapsed = time.time() - t_total
    print(f"\n{'='*70}")
    print(f"  RS WF SUMMARY  (total {total_elapsed:.1f}s)")
    print(f"{'='*70}")
    print(f"\n  {'stat':<6}  {'Dec-20':>8}  {'Jan-25':>8}  {'Feb-28':>8}  {'Apr-05':>8}  {'mean_roi':>10}  {'decision'}")
    print(f"  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}")
    for stat in STATS_TO_EVAL:
        res = all_results.get(stat, {})
        dec = res.get("decision", "?")
        agg = res.get("agg", {})
        fold_rois = agg.get("fold_rois", [None, None, None, None])
        mean_roi = agg.get("mean_roi", None)

        def _fmt(v):
            return f"{v:+.2f}%" if v is not None else "   N/A"

        rois = fold_rois + [None] * (4 - len(fold_rois))
        mean_str = f"{mean_roi:+.2f}%" if mean_roi is not None else "     N/A"
        print(f"  {stat:<6}  {_fmt(rois[0]):>8}  {_fmt(rois[1]):>8}  {_fmt(rois[2]):>8}  {_fmt(rois[3]):>8}  {mean_str:>10}  {dec}")

    print(f"\n  NOTE: Each RS fold has only 1 game-night (sparse) — interpret with caution.")
    print(f"  The WF gate requires n_bets>=5 per fold to count.")


if __name__ == "__main__":
    main()
