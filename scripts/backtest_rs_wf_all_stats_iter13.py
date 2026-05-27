"""backtest_rs_wf_all_stats_iter13.py -- Iter 13: 12-fold RS WF for all 7 stats.

Uses the expanded regular_season_2024_25_oddsapi.csv (12 game-nights after
the expansive backfill: Nov-15, Dec-05, Dec-20, Dec-28, Jan-08, Jan-25,
Feb-05, Feb-28, Mar-08, Mar-25, Apr-05 + Feb-15 (empty)).

Each unique game-date in the RS CSV is one fold.

Decision rule (scaled for 12 folds):
  SHIP   = 8+/12 valid folds positive ROI AND mean_roi > +0.5%
  REVERT = 4+ folds negative ROI
  HOLD   = mixed signal
  (For stats with fewer valid folds, falls back to 3+/4 rule from prior iters)
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
    _safe_mlp_scaler_transform,
)
from src.prediction.prop_quantiles import _inverse  # noqa: E402

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


# -- paths ---------------------------------------------------------------------

RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2024_25_oddsapi.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
THRESHOLD = 0.5

# All 7 props stats
STATS_TO_EVAL = ["pts", "ast", "reb", "fg3m", "stl", "blk"]

# Model type per stat
# pts uses blend (sqrt+Huber NNLS)
# ast uses blend (MLP)
# reb uses LGB-q50
# fg3m, stl, blk use XGB-q50
BLEND_STATS = {"pts", "ast"}
LGB_Q50_STATS = {"reb"}
XGB_Q50_STATS = {"fg3m", "stl", "blk"}

# The 11 RS game-dates now in the CSV (Feb-15 was All-Star break, 0 events)
RS_DATES_ORDERED = [
    "2024-11-15",
    "2024-12-05",
    "2024-12-20",
    "2024-12-28",
    "2025-01-08",
    "2025-01-25",
    "2025-02-05",
    "2025-02-28",
    "2025-03-08",
    "2025-03-25",
    "2025-04-05",
]


# -- artifact loaders ----------------------------------------------------------

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
    import joblib
    import xgboost as xgb_lib
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
    if stat in LGB_Q50_STATS:
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


# -- prediction helpers --------------------------------------------------------

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
        Xs = _safe_mlp_scaler_transform(arts["mlp_scaler"], X)
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


# -- single-fold runner --------------------------------------------------------

def _run_fold(
    stat: str,
    fold_id: str,
    fold_date: str,
    all_csv_rows: List[dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict,
    model_arts,
    is_blend: bool,
) -> Dict:
    window_rows = [
        r for r in all_csv_rows
        if r.get("stat", "").lower() == stat and r["date"] == fold_date
    ]
    if not window_rows:
        return {
            "fold_id": fold_id, "date": fold_date, "stat": stat,
            "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
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
        "date": fold_date,
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


# -- WF decision (12-fold version) --------------------------------------------

def _wf_decision_12fold(fold_results: List[Dict]) -> Tuple[str, Dict]:
    valid = [f for f in fold_results if f["roi_pct"] is not None and f["n_bets"] >= 5]
    if not valid:
        return "INCONCLUSIVE", {}
    rois = [f["roi_pct"] for f in valid]
    n_valid = len(valid)
    n_pos = sum(1 for r in rois if r > 0.0)
    n_neg = sum(1 for r in rois if r < 0.0)
    mean_roi = sum(rois) / n_valid
    std_roi = float(np.std(rois)) if n_valid > 1 else 0.0
    hit_vals = [f["hit_rate"] for f in valid if f["hit_rate"] is not None]
    mean_hit = sum(hit_vals) / len(hit_vals) if hit_vals else 0.0
    mae_vals = [f["mae_actual"] for f in valid if f["mae_actual"] is not None]
    mean_mae = sum(mae_vals) / len(mae_vals) if mae_vals else None

    agg = {
        "n_valid_folds": n_valid,
        "n_pos_roi": n_pos,
        "n_neg_roi": n_neg,
        "mean_roi": round(mean_roi, 3),
        "std_roi": round(std_roi, 3),
        "mean_hit": round(mean_hit, 4),
        "mean_mae": round(mean_mae, 4) if mean_mae else None,
        "fold_rois": [f["roi_pct"] for f in fold_results],
        "fold_bets": [f["n_bets"] for f in fold_results],
    }

    if n_valid < 2:
        decision = "INCONCLUSIVE"
    elif n_valid >= 8:
        # 12-fold gate: need 8+/12 positive AND mean > 0.5%
        if n_pos >= int(n_valid * 0.67) and mean_roi > 0.5:
            decision = "SHIP"
        elif n_neg >= int(n_valid * 0.33 + 0.5):
            decision = "REVERT"
        else:
            decision = "HOLD"
    else:
        # Fewer folds -- fall back to 3+/4 rule from prior iters
        if n_pos >= 3 and mean_roi > 0.5 and n_valid >= 4:
            decision = "SHIP"
        elif n_neg >= 2:
            decision = "REVERT"
        else:
            decision = "HOLD"

    return decision, agg


# -- main ----------------------------------------------------------------------

def main() -> None:
    t_total = time.time()
    print("\n" + "=" * 70)
    print("  Iter 13 -- RS WF Gate: ALL 7 STATS (12-fold)")
    print("  Folds: Nov-15, Dec-05, Dec-20, Dec-28, Jan-08, Jan-25,")
    print("         Feb-05, Feb-28, Mar-08, Mar-25, Apr-05")
    print("=" * 70)

    if not os.path.exists(RS_CSV):
        print(f"  ERROR: RS CSV not found at {RS_CSV}")
        return

    with open(RS_CSV, encoding="utf-8") as fh:
        all_rows: List[dict] = list(csv.DictReader(fh))
    print(f"  RS CSV: {len(all_rows)} rows")

    from collections import Counter
    stat_counts = Counter(r.get("stat", "?") for r in all_rows)
    date_counts = Counter(r.get("date", "?") for r in all_rows)
    print(f"  Rows by stat: {dict(sorted(stat_counts.items()))}")
    print(f"  Dates: {sorted(date_counts.keys())}")

    # Discover actual folds from data
    unique_dates = sorted(set(r["date"] for r in all_rows))
    folds = [(f"rs_fold_{d}", d) for d in unique_dates]
    print(f"  Folds: {len(folds)} unique dates")

    name2pid: Dict[str, Optional[int]] = {}
    row_cache: Dict = {}
    all_results: Dict[str, Dict] = {}

    for stat in STATS_TO_EVAL:
        is_blend = stat in BLEND_STATS
        model_type = "blend" if is_blend else ("lgb-q50" if stat in LGB_Q50_STATS else "xgb-q50")
        print(f"\n{'='*70}")
        print(f"  STAT: {stat.upper()}  ({model_type})")
        print(f"{'='*70}")

        try:
            if is_blend:
                model_arts = _load_blend_artifacts(stat)
                miss = [k for k in ("xgb", "lgb", "weights") if model_arts.get(k) is None]
                if miss and stat == "pts":
                    # pts only needs xgb+weights (LGB weight can be 0)
                    crit_miss = [k for k in ("xgb", "weights") if model_arts.get(k) is None]
                    if crit_miss:
                        print(f"  [skip] missing blend artifacts: {crit_miss}")
                        all_results[stat] = {"decision": "SKIP_NO_ARTIFACT", "folds": [], "agg": {}}
                        continue
                elif miss:
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
        for fold_id, fold_date in folds:
            t_fold = time.time()
            fr = _run_fold(stat, fold_id, fold_date, all_rows, name2pid,
                           row_cache, model_arts, is_blend)
            elapsed_f = time.time() - t_fold
            roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "    N/A"
            hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "  N/A"
            bets_str = f"{fr['n_bets']}"
            skip_str = str(fr.get("skip_reasons", {})) if fr.get("skip_reasons") else ""
            status = fr.get("status", "?")
            print(f"  {fold_date}  n_pred={fr['n_pred']:>4}  n_bets={bets_str:>4}"
                  f"  hit={hit_str:>7}  ROI={roi_str:>9}  [{status}]  ({elapsed_f:.1f}s)")
            if skip_str and skip_str != "{}":
                print(f"      skip={skip_str}")
            fold_results.append(fr)

        decision, agg = _wf_decision_12fold(fold_results)
        print(f"\n  DECISION ({agg.get('n_valid_folds',0)}-fold WF): {decision}")
        if agg:
            n_valid = agg.get("n_valid_folds", 0)
            n_pos = agg.get("n_pos_roi", 0)
            print(f"  pos_folds={n_pos}/{n_valid}  mean_roi={agg['mean_roi']:+.3f}%"
                  f"  std_roi={agg['std_roi']:.3f}%  mean_hit={agg['mean_hit']:.4f}")
            if agg.get("mean_mae"):
                print(f"  mean_mae={agg['mean_mae']:.4f}")

        all_results[stat] = {
            "decision": decision,
            "folds": fold_results,
            "agg": agg,
        }

    # -- summary table ---------------------------------------------------------
    total_elapsed = time.time() - t_total
    print(f"\n{'='*70}")
    print(f"  12-FOLD RS WF SUMMARY  (total {total_elapsed:.1f}s)")
    print(f"{'='*70}")

    # Header: stat + one col per date
    date_abbrevs = [d[5:] for d in unique_dates]  # "11-15", "12-05", ...
    hdr = f"  {'stat':<6}  " + "  ".join(f"{d:>7}" for d in date_abbrevs)
    hdr += f"  {'pos/n':>7}  {'mean_roi':>10}  decision"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for stat in STATS_TO_EVAL:
        res = all_results.get(stat, {})
        dec = res.get("decision", "?")
        agg = res.get("agg", {})
        fold_rois = agg.get("fold_rois", [])
        mean_roi = agg.get("mean_roi")
        n_pos = agg.get("n_pos_roi", 0)
        n_valid = agg.get("n_valid_folds", 0)
        folds_list = res.get("folds", [])

        def _fmt(v):
            if v is None:
                return "    N/A"
            return f"{v:+6.1f}%"

        # Build ROI per fold, matched to unique_dates
        date2roi = {f["date"]: f["roi_pct"] for f in folds_list}
        roi_cols = "  ".join(f"{_fmt(date2roi.get(d)):>7}" for d in unique_dates)
        pos_str = f"{n_pos}/{n_valid}"
        mean_str = f"{mean_roi:+.2f}%" if mean_roi is not None else "      N/A"
        print(f"  {stat:<6}  {roi_cols}  {pos_str:>7}  {mean_str:>10}  {dec}")

    print(f"\n  Gate (>=8 valid folds): SHIP = 67%+ folds positive AND mean_roi > +0.5%")
    print(f"  Gate (<8 valid folds):  SHIP = 3+/4 folds positive AND mean_roi > +0.5%")
    print(f"  n_bets >= 5 required per fold to be counted as valid.")

    # FG3M special note
    fg3m_res = all_results.get("fg3m", {})
    fg3m_agg = fg3m_res.get("agg", {})
    if fg3m_agg.get("mean_roi") is not None:
        print(f"\n  [FG3M KEY FINDING] mean_roi={fg3m_agg['mean_roi']:+.3f}%  "
              f"pos={fg3m_agg.get('n_pos_roi',0)}/{fg3m_agg.get('n_valid_folds',0)}")
        fg3m_dec = fg3m_res.get("decision", "?")
        if fg3m_agg.get("mean_roi", 0) >= 20.0:
            print(f"  FG3M: RS WF holds at +20%+ -- NOT playoff overfit. CONFIRM SHIP.")
        elif fg3m_agg.get("mean_roi", 0) < 5.0:
            print(f"  FG3M: RS WF collapses to <5% -- playoff +23% was OVERFIT. REVERT.")
        else:
            print(f"  FG3M: RS WF mixed signal ({fg3m_dec}) -- proceed with caution.")


if __name__ == "__main__":
    main()
