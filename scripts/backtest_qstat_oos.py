"""backtest_qstat_oos.py - iter-7 generalized OOS backtest for q50 stats."""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from collections import defaultdict
from datetime import datetime
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row, _resolve_player_id, _season_for_date,
    _classify_result, _recommend, _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns, feature_columns_for
from src.prediction.prop_quantiles import _inverse
from src.prediction.bet_thresholds import edge_threshold_for


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_DIR = os.path.join(PROJECT_DIR, "vault", "Reports")
# THRESHOLD is now per-stat via edge_threshold_for() — kept as 0.5 fallback
# for any stat not listed in bet_thresholds._STAT_THRESHOLDS.
THRESHOLD = 0.5
LGB_STATS = {"reb"}

IS_REF = {
    "reb":  {"hit": 0.553, "roi": 5.5,  "bets": 588},
    "fg3m": {"hit": 0.648, "roi": 23.6, "bets": 298},
    "stl":  {"hit": 0.926, "roi": 76.8, "bets":  27},
    "blk":  {"hit": 0.678, "roi": 29.4, "bets":  59},
    "tov":  {"hit": 0.50,  "roi": 0.0,  "bets":  0},
}


def _load_model(stat):
    if stat in LGB_STATS:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            raise SystemExit(f"  [abort] OOS artifact missing: {path}")
        return joblib.load(path), path
    else:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            raise SystemExit(f"  [abort] OOS artifact missing: {path}")
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m, path


def _predict(stat, model, feat_row):
    # Use frozen column list from artifact _meta.json so the OOS model always
    # receives the exact feature set it was trained on (handles schema drift).
    cols = feature_columns_for(stat, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def run(stat):
    print(f"\n  iter-7 OOS {stat.upper()} backtest")
    model, model_path = _load_model(stat)
    print(f"  model: {model_path}")
    meta_path = os.path.join(OOS_DIR, "_meta.json")
    meta_all = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    meta = (meta_all.get("stats", {}) or {}).get(stat, {})
    all_rows = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == stat:
                all_rows.append(r)
    print(f"  CSV rows: {len(all_rows)}")
    name2pid = {nm: _resolve_player_id(nm) for nm in sorted({r["player"] for r in all_rows})}
    row_cache = {}
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a, mae_l = [], []
    t0 = time.time()
    for r in all_rows:
        try:
            line = float(r["closing_line"]); actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1; continue
        pid = name2pid.get(r["player"])
        if pid is None: skip["no_pid"] += 1; continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(pid, r["opp"], d, season, is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR)
        feat = row_cache[key]
        if feat is None: skip["no_history"] += 1; continue
        try:
            pred = _predict(stat, model, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1; continue
        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, edge_threshold_for(stat))
        n_pred += 1
        mae_a.append(abs(pred - actual)); mae_l.append(abs(pred - line))
        if rec != "NO_BET":
            if actual_result == "PUSH": pushes += 1
            else:
                n_bets += 1
                if rec == actual_result: wins += 1
                else: losses += 1
    elapsed = time.time() - t0
    profit = _odds_to_decimal_profit(-110)
    roi_u = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_u / n_bets * 100.0) if n_bets else 0.0
    print(f"\n  {stat.upper()} OOS results ({elapsed:.1f}s):")
    print(f"    n_pred={n_pred} n_bets={n_bets} hit={hit*100:.2f}% ROI={roi_pct:+.2f}%")
    print(f"    skip: {dict(skip)}")
    return {"stat":stat, "n_pred":n_pred, "n_bets":n_bets, "wins":wins, "losses":losses, "pushes":pushes,
            "hit_rate":hit, "roi_pct":roi_pct, "roi_units":roi_u,
            "mae_actual": sum(mae_a)/len(mae_a) if mae_a else 0.0,
            "mae_line": sum(mae_l)/len(mae_l) if mae_l else 0.0,
            "skip_reasons":dict(skip), "meta":meta, "elapsed_sec":elapsed}


def _verdict(stat, hit_rate, n_bets):
    ref = IS_REF.get(stat, {"hit": 0.5})
    if n_bets < 30: return f"INCONCLUSIVE - {n_bets} bets < 30"
    delta_pp = (hit_rate - ref["hit"]) * 100
    if delta_pp >= -0.5: return f"VALIDATED ({delta_pp:+.1f}pp vs IS)"
    if delta_pp >= -3.0: return f"PARTIAL ({delta_pp:+.1f}pp vs IS)"
    return f"LEAK INFLATED ({delta_pp:+.1f}pp vs IS)"


def save_report(result):
    stat = result["stat"]
    ref = IS_REF.get(stat, {"hit":0.5,"roi":0.0,"bets":0})
    verdict = _verdict(stat, result["hit_rate"], result["n_bets"])
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"{stat}_oos_backtest.md")
    m = result["meta"] or {}
    L = [
        f"# {stat.upper()} OOS Backtest - iter-7\n",
        "Leak-clean OOS backtest vs 2024 playoff closing lines.\n",
        "## Training metadata",
        f"- cutoff_date: {m.get('cutoff_date')}",
        f"- method: {m.get('method')}",
        f"- n_train: {m.get('n_train')} | n_val: {m.get('n_val')}",
    ]
    if m.get("val_pinball_q50") is not None:
        L.append(f"- val_pinball@0.5: {m['val_pinball_q50']:.4f}")
    if m.get("val_mae") is not None:
        L.append(f"- val_MAE: {m['val_mae']:.4f}")
    L += [
        "",
        "## OOS results",
        f"- n_pred: {result['n_pred']} | n_bets: {result['n_bets']} | W/L/P: {result['wins']}/{result['losses']}/{result['pushes']}",
        f"- hit_rate: {result['hit_rate']*100:.2f}% | ROI @-110: {result['roi_pct']:+.2f}% ({result['roi_units']:+.2f} units)",
        f"- MAE_actual: {result['mae_actual']:.4f} | MAE_line: {result['mae_line']:.4f}",
        "",
        "## vs iter-4 in-sample",
        "| metric | in-sample | OOS | delta |",
        "|---|---:|---:|---:|",
        f"| hit_rate | {ref['hit']*100:.2f}% | {result['hit_rate']*100:.2f}% | {(result['hit_rate']-ref['hit'])*100:+.2f}pp |",
        f"| ROI | {ref['roi']:+.2f}% | {result['roi_pct']:+.2f}% | {result['roi_pct']-ref['roi']:+.2f}pp |",
        f"| n_bets | {ref['bets']} | {result['n_bets']} | {result['n_bets']-ref['bets']:+d} |",
        "",
        f"## Verdict: **{verdict}**",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  Report -> {path}")
    print(f"  VERDICT: {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", required=True, choices=sorted({"reb","fg3m","stl","blk","tov"}))
    args = ap.parse_args()
    result = run(args.stat)
    save_report(result)


if __name__ == "__main__":
    main()
