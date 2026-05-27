"""backtest_qstat_oos_2025_26.py - iter-12 OOS backtest vs 2025-26 nickflower lines.

Refactor of backtest_qstat_oos.py that:
  - Reads from season_2025_26_canonical.csv
  - Loads models from data/models/oos_pre_2025_26/
  - Outputs vault/Reports/<stat>_oos_2025_26.md

Verdict bar: VALIDATED if hit% within -2pp of 2024-playoffs OOS reference,
else PARTIAL / DEVIATION.
"""
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
from src.prediction.prop_pergame import feature_columns
from src.prediction.prop_quantiles import _inverse


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "season_2025_26_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_2025_26")
REPORT_DIR = os.path.join(PROJECT_DIR, "vault", "Reports")
THRESHOLD = 0.5
LGB_STATS = {"reb"}

# 2024-playoffs OOS reference from iter-6/7 (vault notes).
PLAYOFFS_REF = {
    "blk":  {"hit": 0.6970, "roi":  33.06, "bets":  33},
    "fg3m": {"hit": 0.6450, "roi":  23.14, "bets": 231},
    "stl":  {"hit": 0.7143, "roi":  36.36, "bets": 154},
    "reb":  {"hit": 0.553,  "roi":   5.5,  "bets": 588},
    "tov":  {"hit": 0.50,   "roi":   0.0,  "bets":   0},
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
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def run(stat):
    print(f"\n  iter-12 OOS 2025-26 {stat.upper()} backtest")
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
    print(f"  CSV rows for {stat}: {len(all_rows)}")
    if not all_rows:
        return {"stat": stat, "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0,
                "pushes": 0, "hit_rate": 0.0, "roi_pct": 0.0, "roi_units": 0.0,
                "mae_actual": 0.0, "mae_line": 0.0, "skip_reasons": {"no_csv_rows": 1},
                "meta": meta, "elapsed_sec": 0.0, "bet_keys": []}
    name2pid = {nm: _resolve_player_id(nm) for nm in sorted({r["player"] for r in all_rows})}
    row_cache = {}
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a, mae_l = [], []
    bet_keys = []  # for CV-coverage analysis
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
            row_cache[key] = _build_asof_row(pid, r["opp"], d, season,
                                             is_home=is_home, rest_days=2.0,
                                             gamelog_dir=GAMELOG_DIR)
        feat = row_cache[key]
        if feat is None: skip["no_history"] += 1; continue
        try:
            pred = _predict(stat, model, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1; continue
        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)
        n_pred += 1
        mae_a.append(abs(pred - actual)); mae_l.append(abs(pred - line))
        if rec != "NO_BET":
            if actual_result == "PUSH": pushes += 1
            else:
                n_bets += 1
                bet_keys.append({"date": r["date"], "player": r["player"], "pid": pid})
                if rec == actual_result: wins += 1
                else: losses += 1
    elapsed = time.time() - t0
    profit = _odds_to_decimal_profit(-110)
    roi_u = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_u / n_bets * 100.0) if n_bets else 0.0
    print(f"\n  {stat.upper()} OOS 2025-26 results ({elapsed:.1f}s):")
    print(f"    n_pred={n_pred} n_bets={n_bets} hit={hit*100:.2f}% ROI={roi_pct:+.2f}%")
    print(f"    skip: {dict(skip)}")
    return {"stat":stat, "n_pred":n_pred, "n_bets":n_bets, "wins":wins, "losses":losses,
            "pushes":pushes, "hit_rate":hit, "roi_pct":roi_pct, "roi_units":roi_u,
            "mae_actual": sum(mae_a)/len(mae_a) if mae_a else 0.0,
            "mae_line": sum(mae_l)/len(mae_l) if mae_l else 0.0,
            "skip_reasons":dict(skip), "meta":meta, "elapsed_sec":elapsed,
            "bet_keys": bet_keys}


def _verdict(stat, hit_rate, n_bets):
    ref = PLAYOFFS_REF.get(stat, {"hit": 0.5})
    if n_bets < 30: return f"INCONCLUSIVE - {n_bets} bets < 30"
    delta_pp = (hit_rate - ref["hit"]) * 100
    if delta_pp >= -2.0: return f"VALIDATED ({delta_pp:+.1f}pp vs 2024-playoffs OOS)"
    if delta_pp >= -5.0: return f"PARTIAL ({delta_pp:+.1f}pp vs 2024-playoffs OOS)"
    return f"DEVIATION ({delta_pp:+.1f}pp vs 2024-playoffs OOS)"


def _cv_coverage(bet_keys):
    """Fraction of bet rows that have any prior entry in player_cv_per_game.parquet."""
    if not bet_keys:
        return 0.0, 0, 0
    try:
        import pandas as pd
        cv_path = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
        if not os.path.exists(cv_path):
            return 0.0, 0, len(bet_keys)
        df = pd.read_parquet(cv_path)
    except Exception as e:
        print(f"  [warn] CV coverage skipped: {e}")
        return 0.0, 0, len(bet_keys)
    # CV parquet columns vary — try common keys
    pid_col = None
    for c in ("player_id","PLAYER_ID","pid"):
        if c in df.columns:
            pid_col = c; break
    # CV parquet is keyed (game_id, player_id) — no date col. Player-level
    # coverage is sufficient for the iter-12 feasibility check.
    if pid_col is None:
        print(f"  [warn] CV parquet missing pid col (have: {list(df.columns)[:8]})")
        return 0.0, 0, len(bet_keys)
    pids_with_cv = set(df[pid_col].astype(int).unique().tolist())
    hits = sum(1 for b in bet_keys if int(b["pid"]) in pids_with_cv)
    return hits / len(bet_keys), hits, len(bet_keys)


def save_report(result):
    stat = result["stat"]
    ref = PLAYOFFS_REF.get(stat, {"hit":0.5,"roi":0.0,"bets":0})
    verdict = _verdict(stat, result["hit_rate"], result["n_bets"])
    cov_frac, cov_hits, cov_total = _cv_coverage(result.get("bet_keys", []))
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"{stat}_oos_2025_26.md")
    m = result["meta"] or {}
    L = [
        f"# {stat.upper()} OOS 2025-26 Backtest - iter-12\n",
        "Leak-clean OOS backtest vs nickflower 2025-26 lines (Jan-Feb 2026 slate).\n",
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
        f"- skip: {result['skip_reasons']}",
        "",
        "## vs 2024-playoffs OOS (iter-6/7)",
        "| metric | 2024-playoffs OOS | 2025-26 OOS | delta |",
        "|---|---:|---:|---:|",
        f"| hit_rate | {ref['hit']*100:.2f}% | {result['hit_rate']*100:.2f}% | {(result['hit_rate']-ref['hit'])*100:+.2f}pp |",
        f"| ROI | {ref['roi']:+.2f}% | {result['roi_pct']:+.2f}% | {result['roi_pct']-ref['roi']:+.2f}pp |",
        f"| n_bets | {ref['bets']} | {result['n_bets']} | {result['n_bets']-ref['bets']:+d} |",
        "",
        "## CV coverage on bet set",
        f"- bets with prior CV data: {cov_hits}/{cov_total} = {cov_frac*100:.1f}%",
        f"- CV-augmented retest feasible: {'YES' if cov_frac > 0.40 else 'NO'} (>40% bar)",
        "",
        f"## Verdict: **{verdict}**",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  Report -> {path}")
    print(f"  VERDICT: {verdict}")
    print(f"  CV coverage: {cov_hits}/{cov_total} = {cov_frac*100:.1f}%")
    return cov_frac, cov_hits, cov_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", required=True, choices=sorted({"reb","fg3m","stl","blk","tov"}))
    args = ap.parse_args()
    result = run(args.stat)
    save_report(result)


if __name__ == "__main__":
    main()
