"""iter21_threshold_sweep_all_stats.py — Iter-21 per-stat edge-threshold sweep.

Sweeps [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0] for each stat across all 4 eval
slices combined. STL/BLK already tuned — included for context but not
updated. Focus: PTS, AST, REB, FG3M.

Usage:
    python scripts/iter21_threshold_sweep_all_stats.py

Output:
    vault/Models/Iter21_ThresholdSweep_<date>.md
    data/cache/iter21_threshold_sweep.json
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

LINES_DIR = os.path.join(PROJECT_DIR, "data", "external", "historical_lines")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Models")
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")

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

ALL_STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
QSTAT_LGB = {"reb"}
QSTAT_XGB = {"fg3m", "stl", "blk", "tov"}

PROFIT_AT_110 = _odds_to_decimal_profit(-110)
MIN_BETS_SIGNIFICANT = 30


# ---------------------------------------------------------------------------
# Model loading (same pattern as iter21_edge_shrinkage.py)
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
    if a["xgb"] and a["weights"]:
        a["mode"] = "blend"; _AST_ART_CACHE = a; return a
    if os.path.exists(qp):
        m2 = xgb.XGBRegressor(); m2.load_model(qp)
        a["q50"] = m2; a["mode"] = "q50"; _AST_ART_CACHE = a; return a
    return None


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
    pred = max(sum(parts), 0.0)
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
    return round(max(sum(parts), 0.0), 2)


def _predict(stat: str, model_or_art, feat_row: Dict) -> Optional[float]:
    if stat == "pts":
        return _predict_pts(model_or_art, feat_row) if model_or_art else None
    elif stat == "ast":
        return _predict_ast(model_or_art, feat_row) if model_or_art else None
    else:
        return _predict_qstat(stat, model_or_art, feat_row)


def _get_model(stat: str):
    if stat == "pts":
        return _load_pts_artifacts()
    elif stat == "ast":
        return _load_ast_artifacts()
    else:
        try:
            return _load_qstat_model(stat)
        except FileNotFoundError:
            return None


# ---------------------------------------------------------------------------
# Collect all (pred, line, actual) for a stat from a set of rows
# ---------------------------------------------------------------------------

def _collect_all_triples(
    stat: str,
    all_rows: List[Dict],
    name2pid: Dict,
    row_cache: Dict,
) -> List[Tuple[float, float, float]]:
    model_or_art = _get_model(stat)
    if model_or_art is None:
        return []

    stat_rows = [r for r in all_rows if r.get("stat", "").lower() == stat]
    triples: List[Tuple[float, float, float]] = []
    skip: Dict[str, int] = defaultdict(int)

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
        triples.append((pred, line, actual))

    if skip:
        print(f"    [{stat}] skip: {dict(skip)}", flush=True)
    return triples


# ---------------------------------------------------------------------------
# Threshold eval
# ---------------------------------------------------------------------------

def _eval_at_threshold(
    triples: List[Tuple[float, float, float]],
    threshold: float,
) -> Dict:
    n_bets = wins = losses = 0
    for pred, line, actual in triples:
        edge = pred - line
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
    roi_units = wins * PROFIT_AT_110 - losses
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else None
    hit_rate = (wins / n_bets) if n_bets else None
    return {
        "threshold": threshold,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "roi_pct": roi_pct,
        "hit_rate": hit_rate,
        "roi_units": roi_units,
        "significant": n_bets >= MIN_BETS_SIGNIFICANT,
    }


# ---------------------------------------------------------------------------
# Optimal threshold selection
# ---------------------------------------------------------------------------

def _pick_optimal(rows: List[Dict], current_threshold: float) -> Optional[Dict]:
    """
    Select threshold maximising ROI subject to n_bets >= MIN_BETS_SIGNIFICANT.
    Only return if it beats current threshold's ROI.
    """
    sig = [r for r in rows if r["significant"] and r["roi_pct"] is not None]
    if not sig:
        return None
    best = max(sig, key=lambda r: r["roi_pct"])
    # Also find current threshold row
    current_row = next((r for r in rows if abs(r["threshold"] - current_threshold) < 1e-6), None)
    if current_row and current_row.get("roi_pct") is not None:
        if best["roi_pct"] <= current_row["roi_pct"] + 0.5:
            return None  # Not meaningfully better
    return best


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("\n" + "=" * 70)
    print("  Iter-21 — Per-stat Threshold Sweep (PTS/AST/REB/FG3M + all)")
    print(f"  Thresholds: {THRESHOLDS}")
    print("=" * 70)

    os.makedirs(VAULT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Load all 4 slices into a single list
    all_rows: List[Dict] = []
    for sf, label in zip(SLICE_FILES, SLICE_LABELS):
        if os.path.exists(sf):
            with open(sf, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            print(f"  Loaded {label}: {len(rows)} rows")
            all_rows.extend(rows)
        else:
            print(f"  [WARN] Missing slice: {sf}")

    # Resolve all player IDs
    all_names = sorted({r["player"] for r in all_rows if r.get("player")})
    print(f"\n  Resolving {len(all_names)} unique players...")
    name2pid: Dict[str, Optional[int]] = {}
    for nm in all_names:
        name2pid[nm] = _resolve_player_id(nm)
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved: {n_res}/{len(all_names)}")

    row_cache: Dict = {}
    sweep_results: Dict[str, List[Dict]] = {}
    all_triples: Dict[str, List[Tuple[float, float, float]]] = {}
    recommendations: Dict[str, Optional[Dict]] = {}

    for stat in ALL_STATS:
        current_thr = edge_threshold_for(stat)
        print(f"\n{'='*70}")
        print(f"  STAT: {stat.upper()}  (current threshold={current_thr})")
        print(f"{'='*70}")

        t1 = time.time()
        triples = _collect_all_triples(stat, all_rows, name2pid, row_cache)
        all_triples[stat] = triples
        print(f"  Collected {len(triples)} triples ({time.time()-t1:.1f}s)")

        if not triples:
            print(f"  [SKIP] No data for {stat}")
            sweep_results[stat] = []
            recommendations[stat] = None
            continue

        print(f"\n  {'thresh':>8}  {'n_bets':>8}  {'hit%':>8}  {'roi%':>9}  {'units':>9}  {'sig':>5}")
        print(f"  {'-'*60}")

        stat_rows = []
        for thr in THRESHOLDS:
            ev = _eval_at_threshold(triples, thr)
            sig_mark = "*" if thr == current_thr else (" " if ev["significant"] else "!")
            roi_s = f"{ev['roi_pct']:+.2f}%" if ev["roi_pct"] is not None else "    N/A"
            hit_s = f"{(ev['hit_rate'] or 0)*100:.2f}%" if ev["hit_rate"] is not None else "    N/A"
            print(f"  {thr:>8.2f}  {ev['n_bets']:>8}  {hit_s:>8}  {roi_s:>9}  "
                  f"{ev['roi_units']:>+9.2f}  {sig_mark:>5}")
            stat_rows.append(ev)
        sweep_results[stat] = stat_rows

        # Pick optimal threshold
        rec = _pick_optimal(stat_rows, current_thr)
        recommendations[stat] = rec
        if rec:
            print(f"\n  OPTIMAL threshold: {rec['threshold']:.2f} "
                  f"(n_bets={rec['n_bets']}, hit={( rec['hit_rate'] or 0)*100:.2f}%, "
                  f"roi={( rec['roi_pct'] or 0):+.2f}%)")
            print(f"  vs current {current_thr:.2f}: "
                  f"n_bets={next((r['n_bets'] for r in stat_rows if abs(r['threshold']-current_thr)<1e-6), '?')}, "
                  f"roi={next((r['roi_pct'] or 0 for r in stat_rows if abs(r['threshold']-current_thr)<1e-6), 0):+.2f}%")
        else:
            print(f"\n  No better threshold found — keep {current_thr:.2f}")

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RECOMMENDATIONS SUMMARY")
    print("=" * 70)
    print(f"  {'stat':6}  {'current_thr':>13}  {'optimal_thr':>13}  "
          f"{'cur_roi':>10}  {'opt_roi':>10}  {'delta':>8}  {'action':>10}")
    print(f"  {'-'*80}")

    final_recs: Dict[str, float] = {}
    for stat in ALL_STATS:
        current_thr = edge_threshold_for(stat)
        stat_rows = sweep_results.get(stat, [])
        rec = recommendations.get(stat)
        cur_row = next((r for r in stat_rows if abs(r["threshold"] - current_thr) < 1e-6), None)
        cur_roi = (cur_row["roi_pct"] or 0) if cur_row else 0

        if rec and rec["roi_pct"] is not None:
            delta = (rec["roi_pct"] or 0) - cur_roi
            action = "CHANGE" if delta > 0.5 else "KEEP"
            opt_thr = rec["threshold"]
            opt_roi = rec["roi_pct"] or 0
        else:
            delta = 0.0
            action = "KEEP"
            opt_thr = current_thr
            opt_roi = cur_roi

        if action == "CHANGE":
            final_recs[stat] = opt_thr
        else:
            final_recs[stat] = current_thr

        print(f"  {stat:6}  {current_thr:>13.2f}  {opt_thr:>13.2f}  "
              f"{cur_roi:>+10.2f}%  {opt_roi:>+10.2f}%  {delta:>+8.2f}pp  {action:>10}")

    # -----------------------------------------------------------------------
    # Compute aggregate ROI before vs after applying recommended thresholds
    # -----------------------------------------------------------------------
    print("\n  Computing aggregate ROI before vs after...")
    base_total_bets = base_wins = base_losses = 0
    new_total_bets = new_wins = new_losses = 0

    for stat in ALL_STATS:
        triples = all_triples.get(stat, [])
        if not triples:
            continue
        current_thr = edge_threshold_for(stat)
        new_thr = final_recs.get(stat, current_thr)

        base_ev = _eval_at_threshold(triples, current_thr)
        new_ev = _eval_at_threshold(triples, new_thr)

        base_total_bets += base_ev["n_bets"]
        base_wins += base_ev["wins"]
        base_losses += base_ev["losses"]
        new_total_bets += new_ev["n_bets"]
        new_wins += new_ev["wins"]
        new_losses += new_ev["losses"]

    base_roi_units = base_wins * PROFIT_AT_110 - base_losses
    new_roi_units = new_wins * PROFIT_AT_110 - new_losses
    base_roi_pct = (base_roi_units / base_total_bets * 100) if base_total_bets else 0
    new_roi_pct = (new_roi_units / new_total_bets * 100) if new_total_bets else 0
    base_hit = (base_wins / base_total_bets) if base_total_bets else 0
    new_hit = (new_wins / new_total_bets) if new_total_bets else 0

    agg_delta = new_roi_pct - base_roi_pct
    print(f"\n  {'':30}  {'n_bets':>8}  {'hit%':>7}  {'ROI%':>9}  {'units':>10}")
    print(f"  {'Current thresholds (baseline)':30}  {base_total_bets:>8}  "
          f"{base_hit*100:>7.2f}  {base_roi_pct:>+9.2f}  {base_roi_units:>+10.2f}")
    print(f"  {'Recommended thresholds':30}  {new_total_bets:>8}  "
          f"{new_hit*100:>7.2f}  {new_roi_pct:>+9.2f}  {new_roi_units:>+10.2f}")
    print(f"\n  Aggregate delta ROI: {agg_delta:+.2f}pp")

    decision = "SHIP" if agg_delta > 0.5 else ("REVERT" if agg_delta < -1.0 else "INCONCLUSIVE")
    print(f"  Decision: {decision}")

    # -----------------------------------------------------------------------
    # Cache + Vault
    # -----------------------------------------------------------------------
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_slices": SLICE_LABELS,
        "thresholds_swept": THRESHOLDS,
        "min_bets_significant": MIN_BETS_SIGNIFICANT,
        "baseline_aggregate": {
            "n_bets": base_total_bets,
            "roi_pct": round(base_roi_pct, 4),
            "hit_rate": round(base_hit * 100, 4),
            "roi_units": round(base_roi_units, 4),
        },
        "recommended_aggregate": {
            "n_bets": new_total_bets,
            "roi_pct": round(new_roi_pct, 4),
            "hit_rate": round(new_hit * 100, 4),
            "roi_units": round(new_roi_units, 4),
        },
        "delta_roi_pp": round(agg_delta, 4),
        "decision": decision,
        "final_thresholds": final_recs,
        "per_stat": {
            stat: {
                "current_threshold": edge_threshold_for(stat),
                "recommended_threshold": final_recs.get(stat, edge_threshold_for(stat)),
                "action": "CHANGE" if final_recs.get(stat, edge_threshold_for(stat)) != edge_threshold_for(stat) else "KEEP",
                "sweep_rows": sweep_results.get(stat, []),
            }
            for stat in ALL_STATS
        },
    }

    cache_path = os.path.join(CACHE_DIR, "iter21_threshold_sweep.json")
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\n  Cache -> {cache_path}")

    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(VAULT_DIR, f"Iter21_ThresholdSweep_{today}.md")
    _write_report(payload, report_path)
    print(f"  Report -> {report_path}")

    total_elapsed = time.time() - t0
    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    print(f"  DONE. Aggregate delta: {agg_delta:+.2f}pp  Decision: {decision}")

    return payload


def _write_report(payload: dict, path: str) -> None:
    lines = [
        f"# Iter-21 Per-stat Threshold Sweep — {payload['generated_at'][:10]}",
        "",
        f"Sweep thresholds {payload['thresholds_swept']} across 4 slices "
        f"({', '.join(payload['eval_slices'])}).",
        f"Significance gate: n_bets >= {payload['min_bets_significant']}",
        "",
        "## Aggregate before vs after",
        "",
        "| | n_bets | hit% | ROI@-110 | units |",
        "|--|------:|-----:|---------:|------:|",
    ]
    b = payload["baseline_aggregate"]
    r = payload["recommended_aggregate"]
    lines.append(f"| Current thresholds | {b['n_bets']} | {b['hit_rate']:.2f}% | "
                 f"{b['roi_pct']:+.2f}% | {b['roi_units']:+.2f} |")
    lines.append(f"| Recommended thresholds | {r['n_bets']} | {r['hit_rate']:.2f}% | "
                 f"{r['roi_pct']:+.2f}% | {r['roi_units']:+.2f} |")
    lines += [
        "",
        f"**Aggregate delta ROI:** {payload['delta_roi_pp']:+.2f}pp",
        f"**Decision:** **{payload['decision']}**",
        "",
        "## Per-stat recommendations",
        "",
        "| stat | current_thr | optimal_thr | cur_roi | opt_roi | delta | action |",
        "|------|------------:|------------:|--------:|--------:|------:|--------|",
    ]
    for stat in ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]:
        ps = payload["per_stat"].get(stat, {})
        cur_thr = ps.get("current_threshold", 0.5)
        rec_thr = ps.get("recommended_threshold", cur_thr)
        action = ps.get("action", "KEEP")
        sweep = ps.get("sweep_rows", [])
        cur_row = next((r for r in sweep if abs(r["threshold"] - cur_thr) < 1e-6), None)
        rec_row = next((r for r in sweep if abs(r["threshold"] - rec_thr) < 1e-6), None)
        cur_roi = (cur_row["roi_pct"] or 0) if cur_row else 0
        rec_roi = (rec_row["roi_pct"] or 0) if rec_row else cur_roi
        delta = rec_roi - cur_roi
        lines.append(
            f"| {stat.upper()} | {cur_thr:.2f} | {rec_thr:.2f} | "
            f"{cur_roi:+.2f}% | {rec_roi:+.2f}% | {delta:+.2f}pp | {action} |"
        )
    lines += [""]

    for stat in ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]:
        ps = payload["per_stat"].get(stat, {})
        cur_thr = ps.get("current_threshold", 0.5)
        sweep = ps.get("sweep_rows", [])
        if not sweep:
            continue
        lines += [
            f"## {stat.upper()} sweep",
            "",
            "| threshold | n_bets | hit% | ROI@-110 | units | significant |",
            "|----------:|-------:|-----:|---------:|------:|:-----------:|",
        ]
        for row in sweep:
            roi_s = f"{row['roi_pct']:+.2f}%" if row["roi_pct"] is not None else "N/A"
            hit_s = f"{(row['hit_rate'] or 0)*100:.2f}%" if row["hit_rate"] is not None else "N/A"
            cur_mark = " ← current" if abs(row["threshold"] - cur_thr) < 1e-6 else ""
            lines.append(
                f"| {row['threshold']:.2f}{cur_mark} | {row['n_bets']} | {hit_s} | "
                f"{roi_s} | {row['roi_units']:+.2f} | {'yes' if row['significant'] else 'no'} |"
            )
        lines.append("")

    lines += [
        "## Final recommended thresholds",
        "",
        "```python",
        "_STAT_THRESHOLDS = {",
    ]
    for stat in ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]:
        thr = payload["final_thresholds"].get(stat, 0.5)
        lines.append(f'    "{stat}": {thr},')
    lines += ["}", "```", "", "_Generated by `scripts/iter21_threshold_sweep_all_stats.py`_"]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
