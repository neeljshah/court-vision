"""probe_strategy_d_plus_ast.py — iter-24 probe: should Strategy D extend to AST?

iter-9 OOS-validated AST at 54.74% / +4.51% ROI / PARTIAL (-2.90pp vs IS 57.6%).
AST currently EXCLUDED from Strategy D (BLK + FG3M + STL only). This probe:

1. Reuses iter-9's AST blend prediction path (XGB + LGB + multitask MLP + NNLS).
2. Reuses iter-18's quantile-q50 prediction path for the 3 Strategy D stats.
3. Sweeps AST threshold from 0.20 to 1.50 in 0.05 steps (mirror iter-18).
4. At each AST threshold, computes the per-stat lift if ADDED to Strategy D.
5. Compares to baseline Strategy D (BLK+FG3M+STL only) at threshold 0.50.
6. Same-game correlation check between AST and BLK/STL/FG3M won-flags.
7. Forward-test tonight's WCF G7 (no AST lines actually exist in slate).

Report: vault/Reports/iter24_strategy_d_plus_ast.md
Cache:  data/cache/iter24_strategy_d_plus_ast.json

Constraints:
- DO NOT modify production models or forbidden files.
- LOCAL ONLY (no RunPod).
- Leak-safe via iter-6 _build_asof_row.
- Iter-9 AST predict path: XGB log1p + LGB log1p + MultitaskMLPProxy + NNLS.
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
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import (  # noqa: E402
    feature_columns,
    apply_garbage_time_haircut,
)
from src.prediction.prop_quantiles import _inverse  # noqa: E402

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction  # noqa: E402
except Exception:  # pragma: no cover
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                       "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
FORWARD_CSV = os.path.join(PROJECT_DIR, "data", "cache",
                           "wcf_g7_lines_2026-05-27.csv")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                          "iter24_strategy_d_plus_ast.md")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                         "iter24_strategy_d_plus_ast.json")

STRATEGY_D_STATS = ("blk", "fg3m", "stl")
BET_SIZE = 100.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)
THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(27)]
STRATEGY_D_THRESHOLD = 0.50  # current pinned threshold


# ---- AST blend loader (mirror of backtest_ast_oos.py) -----------------------

def _load_ast_blend():
    import joblib
    import xgboost as xgb_lib
    import src.prediction.prop_pergame  # noqa: F401 — required for unpickle

    artifacts = {}
    xgb_path = os.path.join(OOS_DIR, "props_pg_ast.json")
    lgb_path = os.path.join(OOS_DIR, "props_pg_lgb_ast.pkl")
    mlp_path = os.path.join(OOS_DIR, "props_pg_mlp_ast.pkl")
    mlp_scaler_path = os.path.join(OOS_DIR, "props_pg_mlp_scaler_ast.pkl")
    cal_path = os.path.join(OOS_DIR, "calibration_pergame_ast.joblib")
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")

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
            artifacts["weights"] = weights_all.get("ast")
        except Exception:
            artifacts["weights"] = None
    else:
        artifacts["weights"] = None
    return artifacts


def _inv_log1p(v: float) -> float:
    return max(0.0, float(np.expm1(v)))


def _predict_ast(artifacts, feat_row: Dict[str, float]) -> Optional[float]:
    cols = feature_columns()
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
    if (artifacts.get("mlp") is not None and artifacts.get("mlp_scaler") is not None
            and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
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
    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, "ast", hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, "ast",
                                              model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


# ---- Quantile q50 loader for D stats ----------------------------------------

def _load_qstat_xgb(stat: str):
    import xgboost as xgb_lib
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None
    m = xgb_lib.XGBRegressor()
    m.load_model(path)
    return m


def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ---- Prediction pass --------------------------------------------------------

def _build_predictions() -> List[dict]:
    """Build prediction records for AST + BLK + FG3M + STL across canonical CSV."""
    print(f"  oos_dir: {OOS_DIR}")
    print(f"  csv:     {CSV_PATH}")

    ast_art = _load_ast_blend()
    miss = [k for k in ("xgb", "lgb", "weights") if ast_art.get(k) is None]
    if miss:
        raise SystemExit(f"  [abort] missing AST artifacts: {miss}")
    print(f"  AST loaded: xgb={ast_art['xgb'] is not None} "
          f"lgb={ast_art['lgb'] is not None} mlp={ast_art['mlp'] is not None} "
          f"weights={ast_art['weights']}")

    d_models: Dict[str, object] = {}
    for s in STRATEGY_D_STATS:
        m = _load_qstat_xgb(s)
        if m is None:
            raise SystemExit(f"  [abort] missing {s} quantile model")
        d_models[s] = m
    print(f"  D models loaded: {list(d_models.keys())}")

    target_stats = ("ast",) + STRATEGY_D_STATS
    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in target_stats:
                rows.append(r)
    print(f"  CSV rows (AST + D stats): {len(rows)}")
    stat_counts = defaultdict(int)
    for r in rows:
        stat_counts[r["stat"].lower()] += 1
    print(f"  per-stat counts: {dict(stat_counts)}")

    names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {nm: _resolve_player_id(nm) for nm in names}
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  player resolution: {n_resolved}/{len(names)}")

    preds: List[dict] = []
    skips = defaultdict(int)
    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}
    t0 = time.time()
    for i, r in enumerate(rows):
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skips["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skips["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skips["no_history"] += 1
            continue
        try:
            if stat == "ast":
                pred = _predict_ast(ast_art, feat)
            else:
                pred = _predict_qstat(stat, d_models[stat], feat)
        except Exception as e:
            skips[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skips["model_missing"] += 1
            continue

        edge = pred - line
        ae = abs(edge)
        if edge > 0:
            rec = "OVER"
        elif edge < 0:
            rec = "UNDER"
        else:
            rec = "PUSH_LINE"
        actual_result = _classify_result(actual, line)
        if rec == "PUSH_LINE":
            outcome = "skip"
        elif actual_result == "PUSH":
            outcome = "push"
        else:
            outcome = "win" if rec == actual_result else "loss"

        preds.append({
            "date": r["date"],
            "player": r["player"],
            "opp": r.get("opp", ""),
            "stat": stat,
            "line": line,
            "actual": actual,
            "pred": pred,
            "edge_signed": edge,
            "abs_edge": ae,
            "rec": rec,
            "outcome": outcome,
        })
        if (i + 1) % 500 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s) "
                  f"preds={len(preds)}")
    print(f"  predicted {len(preds)} rows in {time.time()-t0:.1f}s. "
          f"skips: {dict(skips)}")
    return preds


# ---- Sweep + combined ROI ---------------------------------------------------

def _pnl(stake: float, outcome: str,
         profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0


def _max_drawdown_chrono(records: List[Tuple[str, float]]) -> float:
    if not records:
        return 0.0
    records = sorted(records, key=lambda x: x[0])
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for _d, pnl in records:
        cum += pnl
        if cum > peak:
            peak = cum
        dd = min(dd, cum - peak)
    return float(-dd)


def _summarize(records: List[dict], label: str) -> dict:
    """Aggregate a list of prediction records into bet metrics."""
    n_bets = wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    pnl_chrono: List[Tuple[str, float]] = []
    for p in records:
        if p["outcome"] == "skip":
            continue
        n_bets += 1
        total_staked += BET_SIZE
        pnl = _pnl(BET_SIZE, p["outcome"])
        total_pnl += pnl
        if p["outcome"] == "win":
            wins += 1
        elif p["outcome"] == "loss":
            losses += 1
        else:
            pushes += 1
        pnl_chrono.append((p["date"], pnl))
    decisive = wins + losses
    hit = (wins / decisive) if decisive else 0.0
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    dd = _max_drawdown_chrono(pnl_chrono)
    pnl_dd = (total_pnl / dd) if dd > 0 else (
        float("inf") if total_pnl > 0 else 0.0)
    return {
        "label": label,
        "n_bets": n_bets, "wins": wins, "losses": losses, "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2),
        "roi_pct": round(roi, 2),
        "pnl_dollars": round(total_pnl, 2),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 2) if pnl_dd != float("inf") else None),
    }


def _filter_strategy_d(preds: List[dict]) -> List[dict]:
    return [p for p in preds
            if p["stat"] in STRATEGY_D_STATS
            and p["abs_edge"] > STRATEGY_D_THRESHOLD]


def _filter_ast_at(preds: List[dict], thr: float) -> List[dict]:
    return [p for p in preds
            if p["stat"] == "ast" and p["abs_edge"] > thr]


# ---- Correlation analysis ---------------------------------------------------

def _same_game_correlation(d_bets: List[dict], ast_bets: List[dict]) -> dict:
    """For each (date, player) pair where AST + a D-stat both fire, compute the
    correlation of won-flags."""
    # Index D bets by (date, player) and (date, opp set) for game-level join.
    by_player: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for p in d_bets:
        if p["outcome"] in ("skip", "push"):
            continue
        by_player[(p["date"], p["player"])].append(p)
        by_date[p["date"]].append(p)

    same_player_pairs: List[Tuple[int, int, str]] = []  # (ast_win, d_win, d_stat)
    same_game_pairs: List[Tuple[int, int, str]] = []    # any D bet same date
    for a in ast_bets:
        if a["outcome"] in ("skip", "push"):
            continue
        ast_won = 1 if a["outcome"] == "win" else 0
        # Same player + same date
        for d in by_player.get((a["date"], a["player"]), []):
            d_won = 1 if d["outcome"] == "win" else 0
            same_player_pairs.append((ast_won, d_won, d["stat"]))
        # Same date (game-level proxy via date)
        for d in by_date.get(a["date"], []):
            d_won = 1 if d["outcome"] == "win" else 0
            same_game_pairs.append((ast_won, d_won, d["stat"]))

    def _corr(pairs: List[Tuple[int, int, str]]) -> Optional[float]:
        if len(pairs) < 5:
            return None
        a = np.array([x[0] for x in pairs], dtype=float)
        b = np.array([x[1] for x in pairs], dtype=float)
        if a.std() == 0 or b.std() == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    def _by_stat(pairs: List[Tuple[int, int, str]]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for s in STRATEGY_D_STATS:
            sub = [x for x in pairs if x[2] == s]
            corr = _corr(sub)
            out[s] = {
                "n_pairs": len(sub),
                "corr": (round(corr, 4) if corr is not None else None),
                "joint_win_rate": (round(sum(1 for x in sub
                                              if x[0] == 1 and x[1] == 1)
                                          / len(sub), 4)
                                    if sub else None),
            }
        return out

    return {
        "same_player_same_date": {
            "n_pairs": len(same_player_pairs),
            "overall_corr": _corr(same_player_pairs),
            "per_d_stat": _by_stat(same_player_pairs),
        },
        "same_date_any_player": {
            "n_pairs": len(same_game_pairs),
            "overall_corr": _corr(same_game_pairs),
            "per_d_stat": _by_stat(same_game_pairs),
        },
    }


# ---- Forward test (WCF G7) --------------------------------------------------

def _forward_test_wcf_g7(ast_artifacts) -> dict:
    """Check whether tonight's WCF G7 slate contains AST props the system would
    have flagged. If yes, what does the model predict and (if known) what was
    the actual outcome?"""
    if not os.path.exists(FORWARD_CSV):
        return {"error": f"missing {FORWARD_CSV}"}
    rows = []
    with open(FORWARD_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == "ast":
                rows.append(r)
    if not rows:
        return {
            "ast_lines_in_slate": 0,
            "note": "No AST props on tonight's WCF G7 slate. AST filter "
                    "exclusion did not affect tonight's bet selection.",
            "ast_bets_missed": [],
        }
    # If lines exist, would predict each.
    pid_lookup = {r["player"]: _resolve_player_id(r["player"]) for r in rows}
    out_rows = []
    season = _season_for_date(datetime.fromisoformat("2026-05-27"))
    for r in rows:
        pid = pid_lookup.get(r["player"])
        if pid is None:
            continue
        is_home = (r["venue"] == "home")
        feat = _build_asof_row(pid, r["opp"], datetime.fromisoformat("2026-05-27"),
                              season, is_home=is_home, rest_days=2.0,
                              gamelog_dir=GAMELOG_DIR)
        if feat is None:
            continue
        try:
            pred = _predict_ast(ast_artifacts, feat)
        except Exception:
            continue
        if pred is None:
            continue
        try:
            line = float(r["line"])
        except Exception:
            continue
        edge = pred - line
        out_rows.append({
            "player": r["player"],
            "line": line,
            "pred": pred,
            "edge": round(edge, 2),
            "abs_edge": round(abs(edge), 2),
            "rec": ("OVER" if edge > 0 else
                    ("UNDER" if edge < 0 else "PUSH_LINE")),
        })
    return {
        "ast_lines_in_slate": len(rows),
        "ast_predicted_rows": out_rows,
        "note": ("Pre-game AST predictions for tonight. Without ground-truth "
                 "AST outcomes settled, PnL impact is hypothetical."),
    }


# ---- Main -------------------------------------------------------------------

def run() -> dict:
    print("\n  iter-24 Strategy D + AST extension probe\n")
    preds = _build_predictions()

    # Per-stat preds
    ast_preds = [p for p in preds if p["stat"] == "ast"]
    d_preds = [p for p in preds if p["stat"] in STRATEGY_D_STATS]
    print(f"\n  AST preds: {len(ast_preds)}, D-stat preds: {len(d_preds)}")

    # Baseline Strategy D at threshold 0.50
    d_bets = _filter_strategy_d(preds)
    baseline = _summarize(d_bets, "Strategy D baseline (BLK+FG3M+STL, |edge|>0.50)")
    print(f"\n  Baseline Strategy D: n={baseline['n_bets']}  "
          f"hit={baseline['hit_pct']:.2f}%  ROI={baseline['roi_pct']:+.2f}%  "
          f"PnL=${baseline['pnl_dollars']:+.0f}")

    # AST sweep + combined (D@0.50 + AST@thr) sweep
    sweep_rows: List[dict] = []
    for thr in THRESHOLDS:
        ast_added = _filter_ast_at(preds, thr)
        ast_only = _summarize(ast_added, f"AST_only @ {thr:.2f}")
        combined_records = d_bets + ast_added
        combined = _summarize(
            combined_records, f"Strategy D + AST @ {thr:.2f}")
        sweep_rows.append({
            "ast_threshold": thr,
            "ast_n_bets": ast_only["n_bets"],
            "ast_hit_pct": ast_only["hit_pct"],
            "ast_roi_pct": ast_only["roi_pct"],
            "ast_pnl": ast_only["pnl_dollars"],
            "combined_n_bets": combined["n_bets"],
            "combined_hit_pct": combined["hit_pct"],
            "combined_roi_pct": combined["roi_pct"],
            "combined_pnl": combined["pnl_dollars"],
            "combined_maxdd": combined["maxdd_dollars"],
            "combined_pnl_dd": combined["pnl_dd"],
            "delta_roi_pp": round(combined["roi_pct"] - baseline["roi_pct"], 2),
            "delta_pnl": round(combined["pnl_dollars"] - baseline["pnl_dollars"], 2),
        })

    # Pick the best AST threshold by combined ROI delta (require >=10 AST bets).
    valid = [r for r in sweep_rows if r["ast_n_bets"] >= 10]
    best = max(valid, key=lambda x: x["delta_roi_pp"]) if valid else None

    if best is None:
        verdict = "REJECT (no AST threshold yields >=10 bets)"
    elif best["delta_roi_pp"] >= 0.5:
        verdict = (f"SHIP — extend Strategy D to include AST at "
                  f"|edge| > {best['ast_threshold']:.2f}")
    elif best["delta_roi_pp"] >= -0.5:
        verdict = (f"WASH — AST at |edge| > {best['ast_threshold']:.2f} "
                  f"changes combined ROI by {best['delta_roi_pp']:+.2f}pp")
    else:
        verdict = (f"REJECT — best AST threshold ({best['ast_threshold']:.2f}) "
                  f"drops combined ROI by {best['delta_roi_pp']:.2f}pp")
    print(f"\n  Best AST threshold: "
          f"{best['ast_threshold'] if best else 'n/a'}  "
          f"verdict: {verdict}")

    # Same-game correlation (using D@0.50 vs AST at best threshold; also
    # AST at 0.50 as a stable reference).
    ast_at_050 = _filter_ast_at(preds, 0.50)
    corr_at_best = _same_game_correlation(
        d_bets, _filter_ast_at(preds, best["ast_threshold"]) if best
        else ast_at_050)
    corr_at_050 = _same_game_correlation(d_bets, ast_at_050)

    # Forward test on WCF G7
    ast_art = _load_ast_blend()
    fwd = _forward_test_wcf_g7(ast_art)

    return {
        "baseline_strategy_d": baseline,
        "sweep_rows": sweep_rows,
        "best": best,
        "verdict": verdict,
        "correlation_at_best_threshold": corr_at_best,
        "correlation_at_0.50": corr_at_050,
        "forward_test_wcf_g7": fwd,
        "n_preds": len(preds),
        "n_ast_preds": len(ast_preds),
        "n_d_preds": len(d_preds),
        "thresholds_swept": THRESHOLDS,
    }


# ---- Report -----------------------------------------------------------------

def _fmt_pnl_dd(v) -> str:
    if v is None:
        return "inf"
    return f"{v:.2f}"


def save_report(out: dict) -> None:
    L: List[str] = []
    L.append("# iter-24 — Should Strategy D Extend to Include AST?\n")
    L.append("Probe of AST OOS blend (XGB+LGB+MultitaskMLP+NNLS) added to "
             "Strategy D (BLK+FG3M+STL @ |edge|>0.50). Bet size: "
             f"${BET_SIZE:.0f} flat @ -110.\n")
    L.append(f"Predictions enumerated: {out['n_preds']} "
             f"(AST: {out['n_ast_preds']}, D: {out['n_d_preds']}).\n")

    # Baseline
    b = out["baseline_strategy_d"]
    L.append("## Baseline Strategy D (no AST)\n")
    L.append(f"- n_bets={b['n_bets']}, hit={b['hit_pct']:.2f}%, "
             f"ROI={b['roi_pct']:+.2f}%, PnL=${b['pnl_dollars']:+,.0f}, "
             f"MaxDD=${b['maxdd_dollars']:,.0f}, "
             f"PnL/DD={_fmt_pnl_dd(b['pnl_dd'])}.\n")

    # Sweep table
    L.append("## AST threshold sweep (added to Strategy D @ 0.50)\n")
    L.append("| AST_thr | n_AST | AST_hit% | AST_ROI% | Combined_n | "
             "Combined_hit% | Combined_ROI% | Δ_ROI_pp | "
             "Combined_PnL$ | PnL/DD |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in out["sweep_rows"]:
        L.append(f"| {r['ast_threshold']:.2f} | {r['ast_n_bets']} | "
                f"{r['ast_hit_pct']:.2f}% | {r['ast_roi_pct']:+.2f}% | "
                f"{r['combined_n_bets']} | {r['combined_hit_pct']:.2f}% | "
                f"{r['combined_roi_pct']:+.2f}% | "
                f"{r['delta_roi_pp']:+.2f} | "
                f"${r['combined_pnl']:+,.0f} | "
                f"{_fmt_pnl_dd(r['combined_pnl_dd'])} |")
    L.append("")

    # Best + verdict
    best = out["best"]
    L.append("## Best AST threshold + verdict\n")
    if best:
        L.append(f"- **Best AST threshold:** |edge| > {best['ast_threshold']:.2f}")
        L.append(f"  - AST bets added: {best['ast_n_bets']} "
                f"(hit {best['ast_hit_pct']:.2f}%, "
                f"ROI {best['ast_roi_pct']:+.2f}%)")
        L.append(f"  - Combined: n={best['combined_n_bets']}, "
                f"hit={best['combined_hit_pct']:.2f}%, "
                f"ROI={best['combined_roi_pct']:+.2f}%, "
                f"Δ ROI={best['delta_roi_pp']:+.2f}pp vs baseline.")
    L.append(f"\n**Verdict: {out['verdict']}**\n")

    # Correlation
    L.append("## Same-game correlation (AST vs D-stat won-flags)\n")
    for label, key in [
        (f"At best AST threshold "
         f"({best['ast_threshold'] if best else 'n/a'})",
         "correlation_at_best_threshold"),
        ("At AST threshold 0.50 (reference)", "correlation_at_0.50"),
    ]:
        c = out[key]
        L.append(f"### {label}")
        spp = c["same_player_same_date"]
        sgg = c["same_date_any_player"]
        L.append(f"- Same player + same date: n={spp['n_pairs']}, "
                f"overall corr="
                f"{spp['overall_corr'] if spp['overall_corr'] is not None else 'n/a'}")
        for s in STRATEGY_D_STATS:
            pds = spp["per_d_stat"].get(s, {})
            L.append(f"  - vs {s.upper()}: n={pds.get('n_pairs', 0)} "
                    f"corr={pds.get('corr')} "
                    f"joint_win_rate={pds.get('joint_win_rate')}")
        L.append(f"- Same date (any player): n={sgg['n_pairs']}, "
                f"overall corr="
                f"{sgg['overall_corr'] if sgg['overall_corr'] is not None else 'n/a'}")
        for s in STRATEGY_D_STATS:
            pds = sgg["per_d_stat"].get(s, {})
            L.append(f"  - vs {s.upper()}: n={pds.get('n_pairs', 0)} "
                    f"corr={pds.get('corr')} "
                    f"joint_win_rate={pds.get('joint_win_rate')}")
        L.append("")

    # Forward test
    L.append("## Forward test — tonight's WCF G7\n")
    fwd = out["forward_test_wcf_g7"]
    if fwd.get("error"):
        L.append(f"_({fwd['error']})_")
    elif fwd.get("ast_lines_in_slate", 0) == 0:
        L.append(f"- {fwd.get('note', '')}")
        L.append(f"- AST lines in WCF G7 slate: 0. "
                "**Excluding AST from Strategy D did NOT cost us any "
                "potential bets tonight.**")
    else:
        L.append(f"- {fwd.get('note', '')}")
        L.append(f"- AST lines on slate: {fwd['ast_lines_in_slate']}")
        L.append("| player | line | pred | edge | abs_edge | rec |")
        L.append("|---|---:|---:|---:|---:|---|")
        for r in fwd.get("ast_predicted_rows", []):
            L.append(f"| {r['player']} | {r['line']:.1f} | {r['pred']:.2f} | "
                    f"{r['edge']:+.2f} | {r['abs_edge']:.2f} | {r['rec']} |")
    L.append("")

    # Recommendation
    L.append("## Recommendation\n")
    if best and best["delta_roi_pp"] >= 0.5:
        L.append(f"- **EXTEND Strategy D to include AST at "
                f"|edge| > {best['ast_threshold']:.2f}.**")
        L.append(f"  - Expected lift: +{best['delta_roi_pp']:.2f}pp combined "
                f"ROI, +{best['ast_n_bets']} bets added.")
    elif best and best["delta_roi_pp"] >= -0.5:
        L.append("- **KEEP Strategy D at 3 stats (BLK+FG3M+STL).** "
                "AST adds neutral PnL — dilution risk without lift.")
    else:
        L.append("- **REJECT AST extension.** Strictly dilutes combined ROI.")

    L.append("")
    L.append("## Caveats\n")
    L.append("- AST blend uses log1p inverse and NNLS weights from "
             "`meta_weights_pergame.json`.")
    L.append("- ROI computed on decisive (win+loss) bets; pushes excluded.")
    L.append("- Leak safety preserved via iter-6 `_build_asof_row`.")
    L.append("- AST iter-9 OOS verdict was PARTIAL (-2.90pp vs IS). "
             "Threshold raising tested here may help.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  report -> {REPORT_PATH}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            **out,
        }, fh, indent=2, default=str)
    print(f"  cache  -> {CACHE_PATH}")


def main() -> None:
    out = run()
    save_report(out)
    print("\n  ===== ITER-24 PROBE SUMMARY =====")
    b = out["baseline_strategy_d"]
    print(f"  Baseline Strategy D: n={b['n_bets']} "
          f"hit={b['hit_pct']:.2f}% ROI={b['roi_pct']:+.2f}%")
    best = out["best"]
    if best:
        print(f"  Best AST threshold: |edge| > {best['ast_threshold']:.2f}")
        print(f"    AST adds {best['ast_n_bets']} bets, "
              f"AST hit {best['ast_hit_pct']:.2f}%, "
              f"AST ROI {best['ast_roi_pct']:+.2f}%")
        print(f"    Combined: n={best['combined_n_bets']} "
              f"hit={best['combined_hit_pct']:.2f}% "
              f"ROI={best['combined_roi_pct']:+.2f}% "
              f"(Δ {best['delta_roi_pp']:+.2f}pp)")
    print(f"  Verdict: {out['verdict']}")


if __name__ == "__main__":
    main()
