"""train_pts_q50_candidate.py - Iter-8 architecture swap candidate.

Trains XGB-q50 (quantile median, alpha=0.5) for PTS using the same 129-feature
schema, same OOS cutoff (2024-04-21), and same HP regime as the other q50 stats.
Saves candidate artifacts WITHOUT overwriting production sqrt+Huber blend.

Candidate artifacts land at:
    data/models/oos_pre_playoffs/_candidate_pts_q50/quantile_pergame_pts_q50.json
    data/models/oos_pre_playoffs/_candidate_pts_q50/quantile_pergame_pts_q50_xgb.pkl

Then backtests both production and candidate vs:
  - playoffs_2024_canonical.csv  (playoffs slice)
  - regular_season_2024_25_oddsapi.csv  (RS slice)

Prints head-to-head ROI table and saves vault report.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

STAT = "pts"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CANDIDATE_DIR = os.path.join(OOS_DIR, "_candidate_pts_q50")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
PLAYOFFS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                            "playoffs_2024_canonical.csv")
RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2024_25_oddsapi.csv")
VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Models")
CUTOFF_DATE = "2024-04-21"
THRESHOLD = 0.5


# ── PTS q50 HP set (matching production STL/FG3M/BLK/TOV reg regime) ──────────
PTS_Q50_HPS: dict = dict(
    n_estimators=600,
    max_depth=4,
    learning_rate=0.025,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=20,
    reg_lambda=6.0,
    reg_alpha=0.5,
    gamma=0.2,
    random_state=42,
)


# ── Training ──────────────────────────────────────────────────────────────────

def _sqrt_transform(y: np.ndarray) -> np.ndarray:
    return np.sqrt(np.clip(y, 0.0, None))


def _inv_sqrt(v: np.ndarray) -> np.ndarray:
    return np.clip(v, 0.0, None) ** 2


def train_candidate() -> dict:
    import xgboost as xgb
    import joblib
    from sklearn.metrics import mean_absolute_error

    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns_for

    print(f"\n[train] Building pergame dataset...")
    t0 = time.time()
    rows, fcols = build_pergame_dataset(None)
    print(f"[train] Total rows: {len(rows)}, features: {len(fcols)}, elapsed={time.time()-t0:.1f}s")

    # Sort by date then apply OOS cutoff split
    rows.sort(key=lambda r: r["date"])
    pre_cutoff = [r for r in rows if r["date"] <= CUTOFF_DATE]
    post_cutoff = [r for r in rows if r["date"] > CUTOFF_DATE]
    print(f"[train] pre-cutoff rows: {len(pre_cutoff)}, post-cutoff (test): {len(post_cutoff)}")

    # Use same split as production: 80/20 train/val within pre-cutoff
    n_pre = len(pre_cutoff)
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    train_rows = pre_cutoff[:train_end]
    val_rows = pre_cutoff[train_end:]

    print(f"[train] n_train={len(train_rows)}, n_val={len(val_rows)}")

    # Feature matrix
    X_tr = np.array([[float(r.get(c, 0.0) or 0.0) for c in fcols] for r in train_rows], dtype=float)
    X_val = np.array([[float(r.get(c, 0.0) or 0.0) for c in fcols] for r in val_rows], dtype=float)

    y_tr = np.array([r[f"target_{STAT}"] for r in train_rows], dtype=float)
    y_val = np.array([r[f"target_{STAT}"] for r in val_rows], dtype=float)

    # sqrt transform (same as production PTS)
    yt_tr = _sqrt_transform(y_tr)
    yt_val = _sqrt_transform(y_val)

    # Sample weights: exponential decay by age
    train_dates = [datetime.fromisoformat(r["date"]) for r in train_rows]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    print(f"[train] Training XGB-q50 for PTS (n_estimators={PTS_Q50_HPS['n_estimators']})...")
    t1 = time.time()

    m = xgb.XGBRegressor(
        **{k: v for k, v in PTS_Q50_HPS.items() if k != "random_state"},
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40,
        eval_metric="mae",
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    fit_sec = time.time() - t1

    best_iter = int(m.best_iteration) if hasattr(m, "best_iteration") else PTS_Q50_HPS["n_estimators"]
    print(f"[train] Done in {fit_sec:.1f}s, best_iteration={best_iter}")

    # Validation metrics
    pred_val_t = m.predict(X_val)
    pred_val = _inv_sqrt(pred_val_t)
    val_mae = float(np.mean(np.abs(pred_val - y_val)))
    pinball_val = float(np.mean(np.maximum(0.5 * (y_val - pred_val), (0.5 - 1) * (y_val - pred_val))))
    print(f"[train] val_MAE={val_mae:.4f}, val_pinball_q50={pinball_val:.4f}")

    # Save artifacts
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    json_path = os.path.join(CANDIDATE_DIR, "quantile_pergame_pts_q50.json")
    pkl_path = os.path.join(CANDIDATE_DIR, "quantile_pergame_pts_q50_xgb.pkl")
    m.save_model(json_path)
    import joblib as jl
    jl.dump(m, pkl_path)
    print(f"[train] Artifacts saved to {CANDIDATE_DIR}")

    # Save candidate meta
    meta = {
        "stat": STAT,
        "method": "xgb_q50",
        "cutoff_date": CUTOFF_DATE,
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "n_total_rows": len(rows),
        "n_pre_cutoff_rows": n_pre,
        "val_pinball_q50": pinball_val,
        "val_mae": val_mae,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_sec,
        "best_iteration": best_iter,
        "n_features": len(fcols),
        "hps": PTS_Q50_HPS,
        "model_filename": "quantile_pergame_pts_q50.json",
        "feature_columns": fcols,
    }
    with open(os.path.join(CANDIDATE_DIR, "_meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"stats": {"pts": meta}}, fh, indent=2)

    return meta


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _load_candidate() -> object:
    import xgboost as xgb
    path = os.path.join(CANDIDATE_DIR, "quantile_pergame_pts_q50.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Candidate model not found: {path}")
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _load_production() -> dict:
    import xgboost as xgb
    import joblib

    arts: dict = {}
    xgb_path = os.path.join(OOS_DIR, "props_pg_pts.json")
    lgb_path = os.path.join(OOS_DIR, "props_pg_lgb_pts.pkl")
    mlp_path = os.path.join(OOS_DIR, "props_pg_mlp_pts.pkl")
    scaler_path = os.path.join(OOS_DIR, "props_pg_mlp_scaler_pts.pkl")
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    cal_path = os.path.join(OOS_DIR, "calibration_pergame_pts.joblib")

    if os.path.exists(xgb_path):
        m = xgb.XGBRegressor()
        m.load_model(xgb_path)
        arts["xgb"] = m
    arts["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    arts["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    arts["mlp_scaler"] = joblib.load(scaler_path) if os.path.exists(scaler_path) else None
    arts["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None

    if os.path.exists(weights_path):
        try:
            w_all = json.load(open(weights_path, encoding="utf-8"))
            arts["weights"] = w_all.get(STAT)
        except Exception:
            arts["weights"] = None
    return arts


def _predict_candidate(model: object, feat_row: Dict[str, float], fcols: List[str]) -> float:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    return float(max(0.0, pred_t ** 2))


def _predict_production(arts: dict, feat_row: Dict[str, float], fcols: List[str]) -> Optional[float]:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    w = arts.get("weights") or {}
    w_xgb = float(w.get("w_xgb", 0.0))
    w_lgb = float(w.get("w_lgb", 0.0))
    w_mlp = float(w.get("w_mlp", 0.0))
    parts: List[float] = []
    if arts.get("xgb") and w_xgb > 0:
        parts.append(w_xgb * max(0.0, float(arts["xgb"].predict(X)[0])) ** 2)
    if arts.get("lgb") and w_lgb > 0:
        parts.append(w_lgb * max(0.0, float(arts["lgb"].predict(X)[0])) ** 2)
    if arts.get("mlp") and arts.get("mlp_scaler") and w_mlp > 0:
        Xs = arts["mlp_scaler"].transform(X)
        parts.append(w_mlp * max(0.0, float(arts["mlp"].predict(Xs)[0])) ** 2)
    if not parts:
        return None
    pred = sum(parts)
    cal = arts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    return max(0.0, pred)


def _odds_to_decimal_profit(american_odds: int) -> float:
    if american_odds > 0:
        return american_odds / 100.0
    return 100.0 / abs(american_odds)


def _classify(actual: float, line: float) -> str:
    if actual > line:
        return "OVER"
    if actual < line:
        return "UNDER"
    return "PUSH"


def _backtest_slice(
    csv_path: str,
    candidate_model: object,
    production_arts: dict,
    fcols: List[str],
    slice_label: str,
) -> Tuple[dict, dict]:
    from scripts.backtest_closing_lines_2024_playoffs import (
        _build_asof_row, _resolve_player_id, _season_for_date,
    )

    all_rows = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == STAT:
                all_rows.append(r)
    print(f"[{slice_label}] {len(all_rows)} PTS rows")

    name2pid = {nm: _resolve_player_id(nm) for nm in sorted({r["player"] for r in all_rows})}
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"[{slice_label}] player resolution: {n_res}/{len(name2pid)}")

    row_cache: dict = {}
    cand_stats: dict = defaultdict(int)
    prod_stats: dict = defaultdict(int)
    cand_skip = defaultdict(int)
    prod_skip = defaultdict(int)

    cand_wins = cand_losses = cand_bets = 0
    prod_wins = prod_losses = prod_bets = 0
    n_pred = 0
    cand_mae, prod_mae = [], []

    for r in all_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            cand_skip["bad_row"] += 1
            prod_skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            cand_skip["no_pid"] += 1
            prod_skip["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (r.get("venue") == "home")
        key = (pid, r["date"], r.get("venue"), r.get("opp"))
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r.get("opp", ""), d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            cand_skip["no_history"] += 1
            prod_skip["no_history"] += 1
            continue

        n_pred += 1
        actual_result = _classify(actual, line)

        # Candidate
        try:
            cand_pred = _predict_candidate(candidate_model, feat, fcols)
            cand_edge = cand_pred - line
            cand_mae.append(abs(cand_pred - actual))
            if abs(cand_edge) > THRESHOLD:
                rec = "OVER" if cand_edge > 0 else "UNDER"
                if actual_result == "PUSH":
                    pass
                else:
                    cand_bets += 1
                    if rec == actual_result:
                        cand_wins += 1
                    else:
                        cand_losses += 1
        except Exception as e:
            cand_skip[f"err:{type(e).__name__}"] += 1

        # Production
        try:
            prod_pred = _predict_production(production_arts, feat, fcols)
            if prod_pred is not None:
                prod_edge = prod_pred - line
                prod_mae.append(abs(prod_pred - actual))
                if abs(prod_edge) > THRESHOLD:
                    rec = "OVER" if prod_edge > 0 else "UNDER"
                    if actual_result == "PUSH":
                        pass
                    else:
                        prod_bets += 1
                        if rec == actual_result:
                            prod_wins += 1
                        else:
                            prod_losses += 1
            else:
                prod_skip["model_missing"] += 1
        except Exception as e:
            prod_skip[f"err:{type(e).__name__}"] += 1

    profit = _odds_to_decimal_profit(-110)

    def _roi(w: int, b: int) -> float:
        if b == 0:
            return 0.0
        return (w * profit - (b - w) * 1.0) / b * 100.0

    def _hit(w: int, b: int) -> float:
        return w / b if b > 0 else 0.0

    cand_roi = _roi(cand_wins, cand_bets)
    prod_roi = _roi(prod_wins, prod_bets)
    cand_hit = _hit(cand_wins, cand_bets)
    prod_hit = _hit(prod_wins, prod_bets)

    print(f"\n[{slice_label}] n_pred={n_pred}")
    print(f"  CANDIDATE  n_bets={cand_bets} hit={cand_hit*100:.2f}% ROI={cand_roi:+.2f}%  skip={dict(cand_skip)}")
    print(f"  PRODUCTION n_bets={prod_bets} hit={prod_hit*100:.2f}% ROI={prod_roi:+.2f}%  skip={dict(prod_skip)}")

    cand_result = {
        "n_pred": n_pred, "n_bets": cand_bets, "wins": cand_wins, "losses": cand_losses,
        "hit_rate": cand_hit, "roi_pct": cand_roi,
        "mae": sum(cand_mae) / len(cand_mae) if cand_mae else 0.0,
    }
    prod_result = {
        "n_pred": n_pred, "n_bets": prod_bets, "wins": prod_wins, "losses": prod_losses,
        "hit_rate": prod_hit, "roi_pct": prod_roi,
        "mae": sum(prod_mae) / len(prod_mae) if prod_mae else 0.0,
    }
    return cand_result, prod_result


# ── Vault report ──────────────────────────────────────────────────────────────

def save_vault_report(
    train_meta: dict,
    playoffs_cand: dict, playoffs_prod: dict,
    rs_cand: dict, rs_prod: dict,
    recommend_swap: bool,
    rationale: str,
) -> str:
    os.makedirs(VAULT_DIR, exist_ok=True)
    report_path = os.path.join(VAULT_DIR, "PTS q50 Candidate 2026-05-27.md")

    def _comb(c: dict, p: dict) -> dict:
        nb = c["n_bets"] + p["n_bets"]
        # note: c and p are comparing same slices, not combined cand vs prod
        return c  # placeholder — we build combined separately

    # Combined: sum wins/losses/bets across slices
    cand_combined_bets = playoffs_cand["n_bets"] + rs_cand["n_bets"]
    cand_combined_wins = playoffs_cand["wins"] + rs_cand["wins"]
    prod_combined_bets = playoffs_prod["n_bets"] + rs_prod["n_bets"]
    prod_combined_wins = playoffs_prod["wins"] + rs_prod["wins"]
    profit = _odds_to_decimal_profit(-110)

    def _roi(w: int, b: int) -> float:
        return (w * profit - (b - w) * 1.0) / b * 100.0 if b > 0 else 0.0

    cand_combined_roi = _roi(cand_combined_wins, cand_combined_bets)
    prod_combined_roi = _roi(prod_combined_wins, prod_combined_bets)

    delta_playoffs = playoffs_cand["roi_pct"] - playoffs_prod["roi_pct"]
    delta_rs = rs_cand["roi_pct"] - rs_prod["roi_pct"]
    delta_combined = cand_combined_roi - prod_combined_roi

    # hit rate delta
    delta_hit_playoffs = (playoffs_cand["hit_rate"] - playoffs_prod["hit_rate"]) * 100
    delta_hit_rs = (rs_cand["hit_rate"] - rs_prod["hit_rate"]) * 100
    cand_combined_hit = cand_combined_wins / cand_combined_bets if cand_combined_bets > 0 else 0
    prod_combined_hit = prod_combined_wins / prod_combined_bets if prod_combined_bets > 0 else 0
    delta_hit_combined = (cand_combined_hit - prod_combined_hit) * 100

    lines: List[str] = [
        "# PTS q50 Candidate — Iter-8 Architecture Swap Test",
        "",
        f"**Date:** 2026-05-27",
        f"**Hypothesis:** XGB-q50 (quantile median) is the unified winning architecture for PTS prop betting. "
        f"The 3 stats that SHIP under walk-forward (FG3M/BLK/STL, 17-21% mean ROI) all use XGB-q50. "
        f"Sportsbook O/U lines score against the median, not the mean.",
        "",
        "## Training Config",
        f"- method: xgb_q50 (reg:quantileerror, alpha=0.5)",
        f"- cutoff_date: {train_meta.get('cutoff_date')}",
        f"- n_train: {train_meta.get('n_train')} | n_val: {train_meta.get('n_val')}",
        f"- n_features: {train_meta.get('n_features')}",
        f"- val_pinball_q50: {train_meta.get('val_pinball_q50', 0.0):.4f}",
        f"- val_MAE: {train_meta.get('val_mae', 0.0):.4f}",
        f"- fit_seconds: {train_meta.get('fit_seconds', 0.0):.1f}s",
        f"- best_iteration: {train_meta.get('best_iteration')}",
        f"- HPs: {json.dumps(train_meta.get('hps', {}))}",
        "",
        "## Artifact Paths",
        f"- `data/models/oos_pre_playoffs/_candidate_pts_q50/quantile_pergame_pts_q50.json`",
        f"- `data/models/oos_pre_playoffs/_candidate_pts_q50/quantile_pergame_pts_q50_xgb.pkl`",
        "",
        "## Head-to-Head ROI vs Closing Lines",
        "",
        "| slice | prod_PTS_ROI | candidate_q50_PTS_ROI | delta | n_bets (cand) |",
        "|---|---:|---:|---:|---:|",
        f"| playoffs | {playoffs_prod['roi_pct']:+.2f}% | {playoffs_cand['roi_pct']:+.2f}% | {delta_playoffs:+.2f}pp | {playoffs_cand['n_bets']} |",
        f"| RS | {rs_prod['roi_pct']:+.2f}% | {rs_cand['roi_pct']:+.2f}% | {delta_rs:+.2f}pp | {rs_cand['n_bets']} |",
        f"| combined | {prod_combined_roi:+.2f}% | {cand_combined_roi:+.2f}% | {delta_combined:+.2f}pp | {cand_combined_bets} |",
        f"| hit_rate_delta | {prod_combined_hit*100:.2f}% | {cand_combined_hit*100:.2f}% | {delta_hit_combined:+.2f}pp | - |",
        "",
        "## MAE Comparison",
        "",
        "| slice | prod_MAE | cand_q50_MAE | delta |",
        "|---|---:|---:|---:|",
        f"| playoffs | {playoffs_prod['mae']:.4f} | {playoffs_cand['mae']:.4f} | {playoffs_cand['mae']-playoffs_prod['mae']:+.4f} |",
        f"| RS | {rs_prod['mae']:.4f} | {rs_cand['mae']:.4f} | {rs_cand['mae']-rs_prod['mae']:+.4f} |",
        "",
        f"## Recommendation: **{'SWAP' if recommend_swap else 'NO SWAP'}**",
        "",
        f"**Rationale:** {rationale}",
        "",
        "## Context",
        "- Production model: sqrt+Huber blend (XGB + LGB + MLP, NNLS weights)",
        "- Candidate: XGB-q50 solo (reg:quantileerror alpha=0.5)",
        "- Same 129 features, same OOS cutoff 2024-04-21",
        "- Threshold: |edge| > 0.5 PTS, pricing -110/-110",
        f"- Generated: 2026-05-27",
    ]
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n[vault] Report saved: {report_path}")
    return report_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  PTS q50 CANDIDATE TRAINING + SCORING")
    print("=" * 60)

    # 1. Train candidate
    try:
        train_meta = train_candidate()
    except Exception:
        print("[FATAL] Training failed:")
        traceback.print_exc()
        sys.exit(1)

    # 2. Load models
    try:
        candidate_model = _load_candidate()
        print("[load] Candidate model loaded.")
    except Exception:
        print("[FATAL] Could not load candidate:")
        traceback.print_exc()
        sys.exit(1)

    try:
        production_arts = _load_production()
        print(f"[load] Production arts loaded. weights={production_arts.get('weights')}")
    except Exception:
        print("[FATAL] Could not load production:")
        traceback.print_exc()
        sys.exit(1)

    from src.prediction.prop_pergame import feature_columns_for
    fcols = feature_columns_for(STAT, OOS_DIR)
    print(f"[load] Feature columns: {len(fcols)}")

    # 3. Backtest both slices
    print("\n--- PLAYOFFS 2024 SLICE ---")
    playoffs_cand, playoffs_prod = _backtest_slice(
        PLAYOFFS_CSV, candidate_model, production_arts, fcols, "playoffs")

    print("\n--- REGULAR SEASON 2024-25 SLICE ---")
    rs_cand, rs_prod = _backtest_slice(
        RS_CSV, candidate_model, production_arts, fcols, "RS")

    # 4. Print head-to-head table
    profit = _odds_to_decimal_profit(-110)
    cand_comb_b = playoffs_cand["n_bets"] + rs_cand["n_bets"]
    cand_comb_w = playoffs_cand["wins"] + rs_cand["wins"]
    prod_comb_b = playoffs_prod["n_bets"] + rs_prod["n_bets"]
    prod_comb_w = playoffs_prod["wins"] + rs_prod["wins"]

    def _roi(w: int, b: int) -> float:
        return (w * profit - (b - w) * 1.0) / b * 100.0 if b > 0 else 0.0

    cand_comb_roi = _roi(cand_comb_w, cand_comb_b)
    prod_comb_roi = _roi(prod_comb_w, prod_comb_b)
    cand_comb_hit = cand_comb_w / cand_comb_b if cand_comb_b > 0 else 0.0
    prod_comb_hit = prod_comb_w / prod_comb_b if prod_comb_b > 0 else 0.0

    print("\n" + "=" * 70)
    print("  HEAD-TO-HEAD: sqrt+Huber BLEND vs XGB-q50 CANDIDATE")
    print("=" * 70)
    print(f"  {'slice':<12} {'prod_PTS_ROI':>14} {'cand_q50_ROI':>14} {'delta':>10} {'n_bets':>8}")
    print("-" * 70)
    print(f"  {'playoffs':<12} {playoffs_prod['roi_pct']:>13.2f}% {playoffs_cand['roi_pct']:>13.2f}% "
          f"{playoffs_cand['roi_pct']-playoffs_prod['roi_pct']:>+9.2f}pp {playoffs_cand['n_bets']:>8}")
    print(f"  {'RS':<12} {rs_prod['roi_pct']:>13.2f}% {rs_cand['roi_pct']:>13.2f}% "
          f"{rs_cand['roi_pct']-rs_prod['roi_pct']:>+9.2f}pp {rs_cand['n_bets']:>8}")
    print(f"  {'combined':<12} {prod_comb_roi:>13.2f}% {cand_comb_roi:>13.2f}% "
          f"{cand_comb_roi-prod_comb_roi:>+9.2f}pp {cand_comb_b:>8}")
    print(f"  {'hit_rate':<12} {prod_comb_hit*100:>13.2f}% {cand_comb_hit*100:>13.2f}% "
          f"{(cand_comb_hit-prod_comb_hit)*100:>+9.2f}pp {'(comb)':>8}")
    print("=" * 70)

    # 5. Recommendation
    delta_combined = cand_comb_roi - prod_comb_roi
    recommend_swap = delta_combined > 3.0

    if recommend_swap:
        rationale = (
            f"Candidate XGB-q50 outperforms production blend by {delta_combined:+.2f}pp ROI "
            f"on combined slice ({cand_comb_b} bets). This exceeds the +3pp threshold. "
            f"Consistent with q50 winning pattern on FG3M/BLK/STL — sportsbook lines "
            f"score against the median, and q50 directly minimises median error."
        )
        print(f"\n  RECOMMENDATION: SWAP — delta={delta_combined:+.2f}pp > +3pp threshold")
    elif delta_combined > 0:
        rationale = (
            f"Candidate XGB-q50 improves ROI by {delta_combined:+.2f}pp combined "
            f"but does not exceed the +3pp swap threshold. Hypothesis directionally "
            f"confirmed but margin insufficient for production swap without walk-forward validation."
        )
        print(f"\n  RECOMMENDATION: NO SWAP (yet) — delta={delta_combined:+.2f}pp < +3pp threshold")
    else:
        rationale = (
            f"Candidate XGB-q50 does NOT improve over production blend (delta={delta_combined:+.2f}pp). "
            f"sqrt+Huber blend remains superior for PTS, suggesting mean-prediction is competitive "
            f"here due to PTS being a less skewed distribution than BLK/STL/FG3M."
        )
        print(f"\n  RECOMMENDATION: NO SWAP — candidate does not improve ({delta_combined:+.2f}pp)")

    # 6. Save vault report
    report_path = save_vault_report(
        train_meta,
        playoffs_cand, playoffs_prod,
        rs_cand, rs_prod,
        recommend_swap, rationale,
    )

    print("\n" + "=" * 60)
    print(f"  CANDIDATE ARTIFACTS: {CANDIDATE_DIR}")
    print(f"  VAULT REPORT: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
