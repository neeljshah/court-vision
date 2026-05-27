"""iter21_edge_shrinkage.py — Iter-21 edge shrinkage analysis (candidate A).

For each stat, fits a linear regression:
    actual_margin ~ predicted_edge
across the training portion (playoffs_2024 canonical), then applies the
fitted slope as a shrinkage factor to all 4 eval slices.

Shrunk edge = predicted_edge * slope.

Reports ROI before vs after per stat and aggregated.

Usage:
    python scripts/iter21_edge_shrinkage.py

Output:
    vault/Models/Iter21_EdgeShrinkage_<date>.md
    data/cache/iter21_edge_shrinkage.json
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns_for, apply_garbage_time_haircut, _safe_mlp_scaler_transform
from src.prediction.prop_quantiles import _inverse
from src.prediction.bet_thresholds import edge_threshold_for

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred

# Paths
LINES_DIR = os.path.join(PROJECT_DIR, "data", "external", "historical_lines")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Models")
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")

# 4 slices: first one is training portion for slope fitting
SLICE_FILES = [
    os.path.join(LINES_DIR, "playoffs_2024_canonical.csv"),
    os.path.join(LINES_DIR, "regular_season_2024_25_oddsapi.csv"),
    os.path.join(LINES_DIR, "regular_season_2025_26_oddsapi.csv"),
    os.path.join(LINES_DIR, "playoffs_2025_26_oddsapi.csv"),
]
SLICE_LABELS = [
    "playoffs_2024",
    "regular_season_2024_25",
    "regular_season_2025_26",
    "playoffs_2025_26",
]
TRAIN_SLICE_IDX = 0  # playoffs_2024 used to fit shrinkage slope

ALL_STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]
QSTAT_LGB = {"reb"}
QSTAT_XGB = {"fg3m", "stl", "blk", "tov"}

PROFIT_AT_110 = _odds_to_decimal_profit(-110)


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

_MODEL_CACHE: Dict[str, object] = {}
_PTS_ART_CACHE: Optional[dict] = None
_AST_ART_CACHE: Optional[dict] = None


def _load_qstat_model(stat: str):
    if stat in _MODEL_CACHE:
        return _MODEL_CACHE[stat]
    if stat in QSTAT_LGB:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing: {path}")
        m = joblib.load(path)
    else:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing: {path}")
        m = xgb.XGBRegressor()
        m.load_model(path)
    _MODEL_CACHE[stat] = m
    return m


def _load_pts_artifacts() -> Optional[dict]:
    global _PTS_ART_CACHE
    if _PTS_ART_CACHE is not None:
        return _PTS_ART_CACHE
    import joblib, xgboost as xgb
    a = {}
    xp = os.path.join(OOS_DIR, "props_pg_pts.json")
    lp = os.path.join(OOS_DIR, "props_pg_lgb_pts.pkl")
    mp = os.path.join(OOS_DIR, "props_pg_mlp_pts.pkl")
    sp = os.path.join(OOS_DIR, "props_pg_mlp_scaler_pts.pkl")
    cp = os.path.join(OOS_DIR, "calibration_pergame_pts.joblib")
    wp = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    if os.path.exists(xp):
        m = xgb.XGBRegressor(); m.load_model(xp); a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lp) if os.path.exists(lp) else None
    a["mlp"] = joblib.load(mp) if os.path.exists(mp) else None
    a["mlp_scaler"] = joblib.load(sp) if os.path.exists(sp) else None
    a["cal"] = joblib.load(cp) if os.path.exists(cp) else None
    a["weights"] = None
    if os.path.exists(wp):
        try:
            a["weights"] = json.load(open(wp, encoding="utf-8")).get("pts")
        except Exception:
            pass
    if not (a["xgb"] and a["lgb"] and a["weights"]):
        return None
    _PTS_ART_CACHE = a
    return a


def _load_ast_artifacts() -> Optional[dict]:
    global _AST_ART_CACHE
    if _AST_ART_CACHE is not None:
        return _AST_ART_CACHE
    import joblib, xgboost as xgb
    a = {}
    # Prefer blend path (multitask MLP), then q50 fallback
    xp = os.path.join(OOS_DIR, "props_pg_ast.json")
    lp = os.path.join(OOS_DIR, "props_pg_lgb_ast.pkl")
    mp = os.path.join(OOS_DIR, "props_pg_mlp_ast.pkl")
    sp = os.path.join(OOS_DIR, "props_pg_mlp_scaler_ast.pkl")
    wp = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    qp = os.path.join(OOS_DIR, "quantile_pergame_ast_q50.json")
    if os.path.exists(xp):
        m = xgb.XGBRegressor(); m.load_model(xp); a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lp) if os.path.exists(lp) else None
    a["mlp"] = joblib.load(mp) if os.path.exists(mp) else None
    a["mlp_scaler"] = joblib.load(sp) if os.path.exists(sp) else None
    a["weights"] = None
    if os.path.exists(wp):
        try:
            a["weights"] = json.load(open(wp, encoding="utf-8")).get("ast")
        except Exception:
            pass
    # Check if we have a workable blend
    if a["xgb"] and a["weights"]:
        a["mode"] = "blend"
        _AST_ART_CACHE = a
        return a
    # Fallback: q50 model
    if os.path.exists(qp):
        m2 = xgb.XGBRegressor(); m2.load_model(qp)
        a["q50"] = m2; a["mode"] = "q50"
        _AST_ART_CACHE = a
        return a
    return None


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_qstat(stat: str, model, feat_row: Dict) -> Optional[float]:
    cols = feature_columns_for(stat, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    return max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))


def _predict_pts(artifacts: dict, feat_row: Dict) -> Optional[float]:
    cols = feature_columns_for("pts", OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    w = artifacts["weights"]
    w_xgb = float(w.get("w_xgb", 0.0))
    w_lgb = float(w.get("w_lgb", 0.0))
    w_mlp = float(w.get("w_mlp", 0.0))
    parts = []
    if artifacts.get("xgb") and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if artifacts.get("mlp") and artifacts.get("mlp_scaler") and w_mlp > 0:
        Xs = _safe_mlp_scaler_transform(artifacts["mlp_scaler"], X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))
    if not parts:
        return None
    pred = sum(parts)
    cal = artifacts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)
    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, "pts", hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, "pts", model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


def _predict_ast(artifacts: dict, feat_row: Dict) -> Optional[float]:
    mode = artifacts.get("mode", "blend")
    if mode == "q50":
        return _predict_qstat("ast", artifacts["q50"], feat_row)
    # blend
    cols = feature_columns_for("ast", OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    w = artifacts.get("weights") or {}
    w_xgb = float(w.get("w_xgb", 0.0))
    w_lgb = float(w.get("w_lgb", 0.0))
    w_mlp = float(w.get("w_mlp", 0.0))
    parts = []
    if artifacts.get("xgb") and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if artifacts.get("mlp") and artifacts.get("mlp_scaler") and w_mlp > 0:
        Xs = _safe_mlp_scaler_transform(artifacts["mlp_scaler"], X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))
    if not parts:
        return None
    pred = max(sum(parts), 0.0)
    return round(pred, 2)


def _get_model(stat: str):
    """Return model/artifact for the given stat."""
    if stat == "pts":
        return _load_pts_artifacts()
    elif stat == "ast":
        return _load_ast_artifacts()
    else:
        return _load_qstat_model(stat)


def _predict(stat: str, model_or_art, feat_row: Dict) -> Optional[float]:
    if stat == "pts":
        if model_or_art is None:
            return None
        return _predict_pts(model_or_art, feat_row)
    elif stat == "ast":
        if model_or_art is None:
            return None
        return _predict_ast(model_or_art, feat_row)
    else:
        return _predict_qstat(stat, model_or_art, feat_row)


# ---------------------------------------------------------------------------
# Row collection
# ---------------------------------------------------------------------------

def _collect_rows(
    stat: str,
    csv_rows: List[Dict],
    name2pid: Dict,
    row_cache: Dict,
) -> List[Tuple[float, float, float]]:
    """Return list of (pred, line, actual) for all valid stat rows."""
    model_or_art = _get_model(stat)
    if model_or_art is None:
        return []

    stat_rows = [r for r in csv_rows if r.get("stat", "").lower() == stat]
    results = []
    skip = defaultdict(int)

    for r in stat_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
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
            pred = _predict(stat, model_or_art, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skip["model_missing"] += 1
            continue
        results.append((pred, line, actual))

    return results


# ---------------------------------------------------------------------------
# ROI evaluation
# ---------------------------------------------------------------------------

def _eval_roi(
    triples: List[Tuple[float, float, float]],
    threshold: float,
    shrink: float = 1.0,
) -> Dict:
    """Evaluate ROI given (pred, line, actual) with optional edge shrinkage."""
    n_bets = wins = losses = 0
    for pred, line, actual in triples:
        edge = (pred - line) * shrink
        rec = _recommend(edge, threshold)
        if rec == "NO_BET":
            continue
        result = _classify_result(actual, line)
        if result == "PUSH":
            continue
        n_bets += 1
        if rec == result:
            wins += 1
        else:
            losses += 1
    roi_units = wins * PROFIT_AT_110 - losses * 1.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else None
    hit_rate = (wins / n_bets) if n_bets else None
    return {
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "roi_pct": roi_pct,
        "hit_rate": hit_rate,
        "roi_units": roi_units,
    }


# ---------------------------------------------------------------------------
# Shrinkage slope fitting
# ---------------------------------------------------------------------------

def _fit_shrinkage_slope(
    triples: List[Tuple[float, float, float]],
) -> float:
    """
    Fit OLS: actual_margin ~ predicted_edge + intercept.
    actual_margin = actual - line  (positive = OVER hit)
    predicted_edge = pred - line

    Returns slope coefficient. Slope < 1 means model is overconfident.
    Falls back to 1.0 if insufficient data.
    """
    if len(triples) < 10:
        return 1.0
    edges = np.array([pred - line for pred, line, _ in triples])
    margins = np.array([actual - line for _, line, actual in triples])
    # OLS with intercept
    A = np.column_stack([edges, np.ones(len(edges))])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, margins, rcond=None)
        slope = float(coeffs[0])
        # Clip to [0.1, 1.5] to prevent degenerate shrinkage
        slope = max(0.1, min(1.5, slope))
        return slope
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("\n" + "=" * 70)
    print("  Iter-21 — Edge Shrinkage Analysis (Candidate A)")
    print("=" * 70)

    os.makedirs(VAULT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Load all CSV slices
    all_slices: List[List[Dict]] = []
    for sf in SLICE_FILES:
        rows = []
        if os.path.exists(sf):
            with open(sf, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            print(f"  Loaded {os.path.basename(sf)}: {len(rows)} rows")
        else:
            print(f"  [WARN] Missing: {sf}")
        all_slices.append(rows)

    train_rows = all_slices[TRAIN_SLICE_IDX]
    all_rows_combined = []
    for rows in all_slices:
        all_rows_combined.extend(rows)

    # Resolve player IDs from combined data
    all_names = sorted({r["player"] for r in all_rows_combined if r.get("player")})
    print(f"\n  Resolving {len(all_names)} unique players...")
    name2pid: Dict[str, Optional[int]] = {}
    for nm in all_names:
        name2pid[nm] = _resolve_player_id(nm)
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved: {n_res}/{len(all_names)}")

    row_cache: Dict = {}

    results: Dict[str, Dict] = {}

    for stat in ALL_STATS:
        print(f"\n{'='*70}")
        print(f"  STAT: {stat.upper()}")
        print(f"{'='*70}")

        threshold = edge_threshold_for(stat)

        # Collect training predictions (for slope fitting)
        print(f"  Building training triples (slice 0: playoffs_2024)...")
        t1 = time.time()
        train_triples = _collect_rows(stat, train_rows, name2pid, row_cache)
        print(f"  Training triples: {len(train_triples)} ({time.time()-t1:.1f}s)")

        if not train_triples:
            print(f"  [SKIP] No training data for {stat}")
            results[stat] = {"skip": True, "reason": "no_train_data"}
            continue

        # Fit shrinkage slope on training data
        slope = _fit_shrinkage_slope(train_triples)
        print(f"  Fitted shrinkage slope: {slope:.4f}")

        # Collect eval predictions across all 4 slices
        print(f"  Building eval triples (all 4 slices)...")
        eval_triples: List[Tuple[float, float, float]] = []
        for i, (sf_label, rows) in enumerate(zip(SLICE_LABELS, all_slices)):
            t1 = time.time()
            slice_triples = _collect_rows(stat, rows, name2pid, row_cache)
            eval_triples.extend(slice_triples)
            print(f"    [{sf_label}] {len(slice_triples)} triples ({time.time()-t1:.1f}s)")

        if not eval_triples:
            print(f"  [SKIP] No eval data for {stat}")
            results[stat] = {"skip": True, "reason": "no_eval_data", "slope": slope}
            continue

        # Baseline: no shrinkage
        base = _eval_roi(eval_triples, threshold, shrink=1.0)

        # With shrinkage: apply fitted slope
        shrunk = _eval_roi(eval_triples, threshold, shrink=slope)

        # Also test slope=0.75 and 0.9 as fixed alternatives
        shrunk_75 = _eval_roi(eval_triples, threshold, shrink=0.75)
        shrunk_90 = _eval_roi(eval_triples, threshold, shrink=0.90)

        delta_roi = ((shrunk["roi_pct"] or 0) - (base["roi_pct"] or 0)) if base["roi_pct"] is not None else None
        delta_bets = shrunk["n_bets"] - base["n_bets"]

        print(f"\n  {'':40}  {'n_bets':>8}  {'hit%':>7}  {'ROI%':>8}  {'units':>8}")
        print(f"  {'Baseline (slope=1.0)':40}  {base['n_bets']:>8}  "
              f"{(base['hit_rate'] or 0)*100:>7.2f}  "
              f"{(base['roi_pct'] or 0):>+8.2f}  "
              f"{base['roi_units']:>+8.2f}")
        print(f"  {f'Fitted slope={slope:.4f}':40}  {shrunk['n_bets']:>8}  "
              f"{(shrunk['hit_rate'] or 0)*100:>7.2f}  "
              f"{(shrunk['roi_pct'] or 0):>+8.2f}  "
              f"{shrunk['roi_units']:>+8.2f}")
        print(f"  {'Fixed slope=0.90':40}  {shrunk_90['n_bets']:>8}  "
              f"{(shrunk_90['hit_rate'] or 0)*100:>7.2f}  "
              f"{(shrunk_90['roi_pct'] or 0):>+8.2f}  "
              f"{shrunk_90['roi_units']:>+8.2f}")
        print(f"  {'Fixed slope=0.75':40}  {shrunk_75['n_bets']:>8}  "
              f"{(shrunk_75['hit_rate'] or 0)*100:>7.2f}  "
              f"{(shrunk_75['roi_pct'] or 0):>+8.2f}  "
              f"{shrunk_75['roi_units']:>+8.2f}")
        if delta_roi is not None:
            print(f"\n  Delta ROI (fitted vs baseline): {delta_roi:+.2f}pp  "
                  f"Delta bets: {delta_bets:+d}")

        results[stat] = {
            "slope": round(slope, 4),
            "n_train_triples": len(train_triples),
            "n_eval_triples": len(eval_triples),
            "threshold": threshold,
            "baseline": base,
            "shrunk_fitted": shrunk,
            "shrunk_090": shrunk_90,
            "shrunk_075": shrunk_75,
            "delta_roi_fitted": round(delta_roi, 4) if delta_roi is not None else None,
            "delta_bets_fitted": delta_bets,
        }

    # -----------------------------------------------------------------------
    # Aggregate summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  AGGREGATE SUMMARY")
    print("=" * 70)

    valid_stats = [s for s, v in results.items() if not v.get("skip")]

    base_total_bets = sum(results[s]["baseline"]["n_bets"] for s in valid_stats)
    shrunk_total_bets = sum(results[s]["shrunk_fitted"]["n_bets"] for s in valid_stats)
    base_total_wins = sum(results[s]["baseline"]["wins"] for s in valid_stats)
    shrunk_total_wins = sum(results[s]["shrunk_fitted"]["wins"] for s in valid_stats)
    base_total_losses = sum(results[s]["baseline"]["losses"] for s in valid_stats)
    shrunk_total_losses = sum(results[s]["shrunk_fitted"]["losses"] for s in valid_stats)

    base_roi_units = base_total_wins * PROFIT_AT_110 - base_total_losses
    shrunk_roi_units = shrunk_total_wins * PROFIT_AT_110 - shrunk_total_losses
    base_roi_pct = (base_roi_units / base_total_bets * 100) if base_total_bets else 0
    shrunk_roi_pct = (shrunk_roi_units / shrunk_total_bets * 100) if shrunk_total_bets else 0
    base_hit = (base_total_wins / base_total_bets) if base_total_bets else 0
    shrunk_hit = (shrunk_total_wins / shrunk_total_bets) if shrunk_total_bets else 0

    print(f"\n  {'':30}  {'n_bets':>8}  {'hit%':>7}  {'ROI%':>8}  {'units':>10}")
    print(f"  {'Baseline':30}  {base_total_bets:>8}  {base_hit*100:>7.2f}  "
          f"{base_roi_pct:>+8.2f}  {base_roi_units:>+10.2f}")
    print(f"  {'Fitted shrinkage':30}  {shrunk_total_bets:>8}  {shrunk_hit*100:>7.2f}  "
          f"{shrunk_roi_pct:>+8.2f}  {shrunk_roi_units:>+10.2f}")

    agg_delta = shrunk_roi_pct - base_roi_pct
    print(f"\n  Aggregate delta ROI: {agg_delta:+.2f}pp")
    decision = "SHIP" if agg_delta > 0.5 and shrunk_total_bets >= base_total_bets * 0.8 else (
        "REVERT" if agg_delta < -1.0 else "INCONCLUSIVE"
    )
    print(f"  Decision: {decision}")

    # -----------------------------------------------------------------------
    # Per-stat shrinkage slope summary
    # -----------------------------------------------------------------------
    print("\n  Per-stat slope summary:")
    print(f"  {'stat':6}  {'slope':>8}  {'n_train':>8}  {'base_roi':>10}  "
          f"{'shrunk_roi':>11}  {'delta':>8}  {'base_bets':>10}  {'shrunk_bets':>12}")
    for stat in ALL_STATS:
        v = results.get(stat, {})
        if v.get("skip"):
            print(f"  {stat:6}  {'SKIPPED':>8}")
            continue
        br = v["baseline"]["roi_pct"] or 0
        sr = v["shrunk_fitted"]["roi_pct"] or 0
        dr = v.get("delta_roi_fitted") or 0
        print(f"  {stat:6}  {v['slope']:>8.4f}  {v['n_train_triples']:>8}  "
              f"{br:>+10.2f}%  {sr:>+11.2f}%  {dr:>+8.2f}pp  "
              f"{v['baseline']['n_bets']:>10}  {v['shrunk_fitted']['n_bets']:>12}")

    # -----------------------------------------------------------------------
    # Cache + Vault
    # -----------------------------------------------------------------------
    cache_path = os.path.join(CACHE_DIR, "iter21_edge_shrinkage.json")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_slice": SLICE_LABELS[TRAIN_SLICE_IDX],
        "eval_slices": SLICE_LABELS,
        "baseline_aggregate": {
            "n_bets": base_total_bets,
            "roi_pct": round(base_roi_pct, 4),
            "hit_rate": round(base_hit * 100, 4),
            "roi_units": round(base_roi_units, 4),
        },
        "shrunk_aggregate": {
            "n_bets": shrunk_total_bets,
            "roi_pct": round(shrunk_roi_pct, 4),
            "hit_rate": round(shrunk_hit * 100, 4),
            "roi_units": round(shrunk_roi_units, 4),
        },
        "delta_roi_pp": round(agg_delta, 4),
        "decision": decision,
        "per_stat": results,
    }
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\n  Cache -> {cache_path}")

    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(VAULT_DIR, f"Iter21_EdgeShrinkage_{today}.md")
    _write_report(payload, report_path)
    print(f"  Report -> {report_path}")

    total_elapsed = time.time() - t0
    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    print(f"  DONE. Aggregate delta: {agg_delta:+.2f}pp  Decision: {decision}")


def _write_report(payload: dict, path: str) -> None:
    lines = [
        f"# Iter-21 Edge Shrinkage Analysis — {payload['generated_at'][:10]}",
        "",
        "Fits OLS slope (actual_margin ~ predicted_edge) on training slice, "
        "then applies shrink factor to all 4 eval slices.",
        "",
        f"**Train slice:** {payload['train_slice']}",
        f"**Eval slices:** {', '.join(payload['eval_slices'])}",
        "",
        "## Aggregate results",
        "",
        "| | n_bets | hit% | ROI@-110 | units |",
        "|--|------:|-----:|---------:|------:|",
    ]
    b = payload["baseline_aggregate"]
    s = payload["shrunk_aggregate"]
    lines.append(f"| Baseline | {b['n_bets']} | {b['hit_rate']:.2f}% | "
                 f"{b['roi_pct']:+.2f}% | {b['roi_units']:+.2f} |")
    lines.append(f"| Fitted shrinkage | {s['n_bets']} | {s['hit_rate']:.2f}% | "
                 f"{s['roi_pct']:+.2f}% | {s['roi_units']:+.2f} |")
    lines += [
        "",
        f"**Aggregate delta ROI:** {payload['delta_roi_pp']:+.2f}pp",
        f"**Decision:** **{payload['decision']}**",
        "",
        "## Per-stat shrinkage slopes",
        "",
        "| stat | slope | n_train | base_ROI | shrunk_ROI | delta_ROI | base_bets | shrunk_bets |",
        "|------|------:|-------:|---------:|-----------:|----------:|----------:|------------:|",
    ]
    for stat in ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]:
        v = payload["per_stat"].get(stat, {})
        if v.get("skip"):
            lines.append(f"| {stat.upper()} | SKIP | - | - | - | - | - | - |")
            continue
        br = v["baseline"]["roi_pct"] or 0
        sr = v["shrunk_fitted"]["roi_pct"] or 0
        dr = v.get("delta_roi_fitted") or 0
        lines.append(
            f"| {stat.upper()} | {v['slope']:.4f} | {v['n_train_triples']} | "
            f"{br:+.2f}% | {sr:+.2f}% | {dr:+.2f}pp | "
            f"{v['baseline']['n_bets']} | {v['shrunk_fitted']['n_bets']} |"
        )
    lines += [
        "",
        "## Decision rationale",
        f"Shrinkage ships if aggregate delta ROI > +0.5pp AND shrunk_bets >= 80% of baseline_bets.",
        f"Result: **{payload['decision']}**",
        "",
        "_Generated by `scripts/iter21_edge_shrinkage.py`_",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
