"""backtest_ast_oos.py - iter-9 OOS backtest for AST multitask MLP blend.

Loads the OOS AST artifacts (XGB + LGB + multitask MLP proxy + scaler + optional
isotonic calibrator + NNLS weights) from data/models/oos_pre_playoffs/ and replays
the 2024 playoffs canonical CSV row-by-row, reusing _build_asof_row from the iter-6
closing-line backtest for leak-free feature construction.

Mirrors scripts/backtest_pts_oos.py but for AST. Key diffs vs PTS:
  - AST uses log1p target transform (PTS uses sqrt). _inv = np.expm1 clipped at 0.
  - AST MLP is a _MultitaskMLPProxy with .predict() identical to a 1D regressor —
    joblib pickles it directly, no behaviour difference from the caller's view.
  - AST IS in _GARBAGE_HAIRCUT_STATS so the haircut still applies (same as PTS).

We bypass prop_pergame.predict_pergame() entirely so we read the OOS artifacts and
OOS NNLS weights (not the production module-cached ones).

Reference (iter-4 in-sample, from closing_line_backtest_2024_playoffs.md):
    AST  n_pred=831  n_bets=406  hit=57.64%  ROI=+10.03%
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
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

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction  # noqa: E402
except Exception:  # pragma: no cover
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


STAT = "ast"
# NBA_BACKTEST_CSV_OVERRIDE allows build_unified_baseline.py to inject a
# merged multi-slice CSV without modifying this script.
CSV_PATH = os.environ.get("NBA_BACKTEST_CSV_OVERRIDE") or os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv"
)
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports", "ast_oos_backtest.md")
THRESHOLD = 0.5

# iter-4 in-sample reference (closing_line_backtest_2024_playoffs.md row for AST).
IS_REF = {"hit": 0.5764, "roi": 10.03, "bets": 406, "n_pred": 831}


def _load_oos_artifacts():
    import joblib
    import xgboost as xgb_lib

    # Make sure _MultitaskMLPProxy / _MultitaskMLPEnsemble can unpickle. Importing
    # prop_pergame above already loads the classes; joblib uses the module path.
    import src.prediction.prop_pergame  # noqa: F401

    xgb_path = os.path.join(OOS_DIR, f"props_pg_{STAT}.json")
    lgb_path = os.path.join(OOS_DIR, f"props_pg_lgb_{STAT}.pkl")
    mlp_path = os.path.join(OOS_DIR, f"props_pg_mlp_{STAT}.pkl")
    mlp_scaler_path = os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{STAT}.pkl")
    cal_path = os.path.join(OOS_DIR, f"calibration_pergame_{STAT}.joblib")
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")

    artifacts = {}

    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        artifacts["xgb"] = m
    else:
        artifacts["xgb"] = None

    artifacts["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    artifacts["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    artifacts["mlp_scaler"] = (joblib.load(mlp_scaler_path)
                                if os.path.exists(mlp_scaler_path) else None)
    artifacts["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None

    if os.path.exists(weights_path):
        try:
            weights_all = json.load(open(weights_path, encoding="utf-8"))
            artifacts["weights"] = weights_all.get(STAT)
        except Exception:
            artifacts["weights"] = None
    else:
        artifacts["weights"] = None

    return artifacts


def _inv_log1p(v: float) -> float:
    return max(0.0, float(np.expm1(v)))


def _predict_blend(artifacts, feat_row: Dict[str, float]) -> Optional[float]:
    # Use feature_columns_for() to get the frozen 129-col list matching OOS artifacts.
    cols = feature_columns_for(STAT, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)

    weights = artifacts["weights"]
    if not weights:
        return None

    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))

    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_log1p(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_log1p(float(artifacts["lgb"].predict(X)[0])))
    if artifacts.get("mlp") is not None and artifacts.get("mlp_scaler") is not None and w_mlp > 0:
        Xs = _safe_mlp_scaler_transform(artifacts["mlp_scaler"], X)
        parts.append(w_mlp * _inv_log1p(float(artifacts["mlp"].predict(Xs)[0])))

    if not parts:
        return None
    pred = float(sum(parts))

    cal = artifacts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)

    # Cycle 96a haircut (AST IS in _GARBAGE_HAIRCUT_STATS).
    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, STAT, hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, STAT, model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


def run() -> dict:
    print(f"\n  iter-9 OOS AST backtest")
    artifacts = _load_oos_artifacts()
    miss = [k for k in ("xgb", "lgb", "weights") if artifacts.get(k) is None]
    if miss:
        raise SystemExit(f"  [abort] missing OOS artifacts: {miss}")
    print(f"  artifacts loaded: xgb={artifacts['xgb'] is not None} "
          f"lgb={artifacts['lgb'] is not None} mlp={artifacts['mlp'] is not None} "
          f"cal={artifacts['cal'] is not None}")
    print(f"  NNLS weights: {artifacts['weights']}")

    all_rows = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == STAT:
                all_rows.append(r)
    print(f"  CSV AST rows: {len(all_rows)}")

    name2pid = {nm: _resolve_player_id(nm)
                for nm in sorted({r["player"] for r in all_rows})}
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  player resolution: {n_resolved}/{len(name2pid)}")

    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a, mae_l = [], []
    preview: List[Tuple] = []

    t0 = time.time()
    for r in all_rows:
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
            pred = _predict_blend(artifacts, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skip["model_missing"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)

        n_pred += 1
        mae_a.append(abs(pred - actual))
        mae_l.append(abs(pred - line))

        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1
        if len(preview) < 10:
            preview.append((r["player"], r["date"], pred, line, actual))

    elapsed = time.time() - t0
    profit_per_win = _odds_to_decimal_profit(-110)
    roi_units = wins * profit_per_win - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0

    print(f"\n  AST OOS results ({elapsed:.1f}s):")
    print(f"    n_pred={n_pred}  n_bets={n_bets}  W/L/P={wins}/{losses}/{pushes}")
    print(f"    hit_rate={hit*100:.2f}%  ROI@-110={roi_pct:+.2f}%  units={roi_units:+.2f}")
    print(f"    MAE_actual={(sum(mae_a)/len(mae_a) if mae_a else 0):.4f}  "
          f"MAE_line={(sum(mae_l)/len(mae_l) if mae_l else 0):.4f}")
    print(f"    skip: {dict(skip)}")

    return {
        "n_pred": n_pred, "n_bets": n_bets, "wins": wins, "losses": losses,
        "pushes": pushes, "hit_rate": hit, "roi_pct": roi_pct,
        "roi_units": roi_units,
        "mae_actual": sum(mae_a) / len(mae_a) if mae_a else 0.0,
        "mae_line": sum(mae_l) / len(mae_l) if mae_l else 0.0,
        "skip_reasons": dict(skip), "elapsed_sec": elapsed,
        "preview": preview, "weights": artifacts["weights"],
    }


def _verdict(hit_rate: float, n_bets: int) -> str:
    if n_bets < 30:
        return f"INCONCLUSIVE - {n_bets} bets < 30"
    delta_pp = (hit_rate - IS_REF["hit"]) * 100
    if delta_pp >= -0.5:
        return f"VALIDATED ({delta_pp:+.2f}pp vs IS)"
    if delta_pp >= -3.0:
        return f"PARTIAL ({delta_pp:+.2f}pp vs IS)"
    if delta_pp >= -5.0:
        return f"PARTIAL/WEAK ({delta_pp:+.2f}pp vs IS)"
    return f"LEAK INFLATED ({delta_pp:+.2f}pp vs IS)"


def save_report(result: dict) -> str:
    meta_path = os.path.join(OOS_DIR, "_meta.json")
    meta_all = {}
    if os.path.exists(meta_path):
        try:
            meta_all = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            meta_all = {}
    m = (meta_all.get("stats", {}) or {}).get(STAT, {})

    verdict = _verdict(result["hit_rate"], result["n_bets"])
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    L: List[str] = []
    L.append("# AST OOS Backtest - iter-9\n")
    L.append("Leak-clean OOS backtest of the AST log1p multitask-MLP blend vs 2024 playoff closing lines.\n")
    L.append("## Training metadata")
    L.append(f"- cutoff_date: {m.get('cutoff_date')}")
    L.append(f"- method: {m.get('method')}")
    L.append(f"- n_train: {m.get('n_train')} | n_val: {m.get('n_val')} | n_holdout: {m.get('n_holdout')}")
    L.append(f"- holdout_R²: {m.get('holdout_r2')}")
    L.append(f"- holdout_MAE: {m.get('holdout_mae')} (uncal {m.get('uncal_holdout_mae')})")
    L.append(f"- calibration_used: {m.get('calibration_used')} (lift_MAE {m.get('calibration_lift_mae')})")
    L.append(f"- NNLS weights: xgb={m.get('meta_w_xgb')} / lgb={m.get('meta_w_lgb')} / mlp={m.get('meta_w_mlp')} (src={m.get('meta_fit_source')})")
    L.append(f"- base R²: xgb={m.get('xgb_holdout_r2')} / lgb={m.get('lgb_holdout_r2')} / mlp={m.get('mlp_holdout_r2')}")
    L.append(f"- HPs: {json.dumps(m.get('hps', {}))}")
    L += [
        "",
        "## OOS results",
        f"- n_pred: {result['n_pred']} | n_bets: {result['n_bets']} | W/L/P: {result['wins']}/{result['losses']}/{result['pushes']}",
        f"- hit_rate: {result['hit_rate']*100:.2f}% | ROI @-110: {result['roi_pct']:+.2f}% ({result['roi_units']:+.2f} units)",
        f"- MAE_actual: {result['mae_actual']:.4f} | MAE_line: {result['mae_line']:.4f}",
        f"- skip: {result['skip_reasons']}",
        "",
        "## vs iter-4 in-sample (closing_line_backtest_2024_playoffs.md)",
        "| metric | in-sample | OOS | delta |",
        "|---|---:|---:|---:|",
        f"| n_pred | {IS_REF['n_pred']} | {result['n_pred']} | {result['n_pred']-IS_REF['n_pred']:+d} |",
        f"| hit_rate | {IS_REF['hit']*100:.2f}% | {result['hit_rate']*100:.2f}% | {(result['hit_rate']-IS_REF['hit'])*100:+.2f}pp |",
        f"| ROI | {IS_REF['roi']:+.2f}% | {result['roi_pct']:+.2f}% | {result['roi_pct']-IS_REF['roi']:+.2f}pp |",
        f"| n_bets | {IS_REF['bets']} | {result['n_bets']} | {result['n_bets']-IS_REF['bets']:+d} |",
        "",
        f"## Verdict: **{verdict}**",
        "",
        "Threshold: |edge| > 0.5 AST. Bet pricing: -110/-110. Verdict rule:",
        " VALIDATED if hit >= IS - 0.5pp, PARTIAL if within -3pp, LEAK INFLATED if > -5pp drop.",
        "",
        "## Preview (first 10)",
        "| player | date | pred | line | actual |",
        "|---|---|---:|---:|---:|",
    ]
    for (pl, dt, pr, ln, ac) in result["preview"]:
        L.append(f"| {pl} | {dt} | {pr:.2f} | {ln:.2f} | {ac:.2f} |")
    L.append("")
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  Report -> {REPORT_PATH}")
    print(f"  VERDICT: {verdict}")
    return verdict


def main() -> None:
    result = run()
    save_report(result)


if __name__ == "__main__":
    main()
