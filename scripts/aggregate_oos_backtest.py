"""aggregate_oos_backtest.py - iter-9 honest aggregate OOS backtest.

Replays the 2024 NBA playoff closing-line slate using the leak-clean OOS
artifacts (data/models/oos_pre_playoffs/) for each stat and pools the
results so we get an HONEST aggregate ROI/PnL number that the iter-4 claim
(+10.57% / +$21,827 across 2,065 bets) can be compared against.

Per-stat predict paths reproduce the per-stat iter-6/7/8 OOS scripts:
  - q50 stats (blk/fg3m/reb/stl/tov): raw q50 inverse-transform (log1p
    inverse via prop_quantiles._inverse), then clip>=0. NO garbage-time
    haircut / residual head (mirrors backtest_qstat_oos.py).
  - PTS: full sqrt+Huber blend (XGB + LGB + MLP scaled) under the OOS
    NNLS weights, then optional isotonic calibrator (none on disk in
    iter-9), then cycle-96a garbage-time haircut + residual passthrough
    (mirrors backtest_pts_oos.py).
  - AST: not retrained OOS yet (iter-9 only has the parallel agent in
    flight). Skipped with a clear log line.

All other plumbing (asof feature row, player id resolution, recommend,
classify_result, -110 profit, threshold |edge| > 0.5) is reused verbatim
from scripts/backtest_closing_lines_2024_playoffs.py to keep the iter-4
↔ iter-9 comparison apples-to-apples.

Report: vault/Reports/honest_aggregate_oos_backtest.md
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
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "honest_aggregate_oos_backtest.md")
THRESHOLD = 0.5
BET_SIZE = 100.0  # flat $100/bet @ -110

# Stat universe and which family of artifact to load. PTS is special (blend).
QSTAT_XGB = {"blk", "fg3m", "stl", "tov"}
QSTAT_LGB = {"reb"}
ALL_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# iter-4 in-sample reference, from closing_line_backtest_2024_playoffs.md.
# Used for the delta column in the per-stat table.
IS_REF = {
    "pts":  {"hit": 0.5517, "roi": 5.32,  "bets": 687, "n_pred": 853},
    "reb":  {"hit": 0.553,  "roi": 5.5,   "bets": 588, "n_pred": None},
    "ast":  {"hit": 0.0,    "roi": 0.0,   "bets": 0,   "n_pred": None},
    "fg3m": {"hit": 0.648,  "roi": 23.6,  "bets": 298, "n_pred": None},
    "stl":  {"hit": 0.926,  "roi": 76.8,  "bets": 27,  "n_pred": None},
    "blk":  {"hit": 0.678,  "roi": 29.4,  "bets": 59,  "n_pred": None},
    "tov":  {"hit": 0.50,   "roi": 0.0,   "bets": 0,   "n_pred": None},
}
# Aggregate iter-4 totals as quoted in the iter-9 task brief.
ITER4_TOTAL_BETS = 2065
ITER4_TOTAL_ROI_PCT = 10.57
ITER4_TOTAL_PNL = 21827.0


# ----------------------------------------------------------------------
# Artifact loaders
# ----------------------------------------------------------------------

def _load_qstat_model(stat: str):
    """Return (model, path) or (None, path) if not on disk."""
    if stat in QSTAT_LGB:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            return None, path
        return joblib.load(path), path
    if stat in QSTAT_XGB:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            return None, path
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m, path
    return None, ""


def _load_pts_artifacts():
    import joblib
    import xgboost as xgb_lib
    xgb_path = os.path.join(OOS_DIR, "props_pg_pts.json")
    lgb_path = os.path.join(OOS_DIR, "props_pg_lgb_pts.pkl")
    mlp_path = os.path.join(OOS_DIR, "props_pg_mlp_pts.pkl")
    sca_path = os.path.join(OOS_DIR, "props_pg_mlp_scaler_pts.pkl")
    cal_path = os.path.join(OOS_DIR, "calibration_pergame_pts.joblib")
    wts_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    a = {}
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    a["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    a["mlp_scaler"] = joblib.load(sca_path) if os.path.exists(sca_path) else None
    a["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None
    weights = None
    if os.path.exists(wts_path):
        try:
            weights_all = json.load(open(wts_path, encoding="utf-8"))
            weights = weights_all.get("pts")
        except Exception:
            weights = None
    a["weights"] = weights
    return a


# ----------------------------------------------------------------------
# Prediction
# ----------------------------------------------------------------------

def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_pts(artifacts: dict, feat_row: Dict[str, float]) -> Optional[float]:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    weights = artifacts.get("weights")
    if not weights:
        return None
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None
            and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))
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
        pred = float(apply_garbage_time_haircut(pred, "pts", hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, "pts",
                                               model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------

EDGE_BUCKETS = [(0.5, 0.75), (0.75, 1.0), (1.0, 1.5), (1.5, float("inf"))]


def _bucket_of(edge_mag: float) -> Optional[Tuple[float, float]]:
    for lo, hi in EDGE_BUCKETS:
        if edge_mag >= lo and edge_mag < hi:
            return (lo, hi)
    return None


def run() -> dict:
    print("\n  iter-9 aggregate OOS backtest")
    print(f"  csv:        {CSV_PATH}")
    print(f"  oos_dir:    {OOS_DIR}")
    print(f"  threshold:  |edge| > {THRESHOLD}")
    print(f"  bet_size:   ${BET_SIZE:.0f} @ -110")

    # Load all models we have.
    models: Dict[str, object] = {}
    pts_art = _load_pts_artifacts()
    have_pts = (pts_art["xgb"] is not None and pts_art["lgb"] is not None
                and pts_art["weights"] is not None)
    if have_pts:
        models["pts"] = pts_art
        print(f"  pts blend ready: weights={pts_art['weights']}")
    else:
        print("  pts blend NOT ready - skipping pts")
    for s in ("blk", "fg3m", "reb", "stl", "tov"):
        m, path = _load_qstat_model(s)
        if m is not None:
            models[s] = m
            print(f"  loaded {s:<5} from {os.path.basename(path)}")
        else:
            print(f"  missing {s:<5} ({path}) - skipping")

    # Note AST status.
    ast_path_xgb = os.path.join(OOS_DIR, "quantile_pergame_ast_q50.json")
    ast_path_lgb = os.path.join(OOS_DIR, "quantile_pergame_lgb_ast_q50.pkl")
    ast_path_blend = os.path.join(OOS_DIR, "props_pg_ast.json")
    have_ast = (os.path.exists(ast_path_xgb)
                or os.path.exists(ast_path_lgb)
                or os.path.exists(ast_path_blend))
    if have_ast:
        print("  ast OOS artifact found - attempting to load")
        # Best-effort: try q50 first.
        if os.path.exists(ast_path_xgb):
            import xgboost as xgb
            mm = xgb.XGBRegressor()
            mm.load_model(ast_path_xgb)
            models["ast"] = ("qstat_xgb_logp1", mm)
        elif os.path.exists(ast_path_lgb):
            import joblib
            models["ast"] = ("qstat_lgb_logp1", joblib.load(ast_path_lgb))
    else:
        print("  ast OOS artifact NOT found - AST will be excluded from totals")

    # Load CSV rows once.
    all_rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            stat = r.get("stat", "").lower()
            if stat in models:
                all_rows.append(r)
    print(f"  CSV rows for stats we can predict: {len(all_rows)}")

    # Resolve all unique names once.
    unique_names = sorted({r["player"] for r in all_rows})
    print(f"  resolving {len(unique_names)} unique players...")
    name2pid: Dict[str, Optional[int]] = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_resolved}/{len(unique_names)} players")

    # Per-stat result accumulator.
    per_stat: Dict[str, dict] = {}
    for s in models.keys():
        per_stat[s] = {
            "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "mae_actual": [], "mae_line": [],
            "skip": defaultdict(int),
        }
    # Edge-bucket accumulator (pooled across stats).
    bucket_acc: Dict[Tuple[float, float], dict] = {
        b: {"n_bets": 0, "wins": 0, "pushes": 0, "losses": 0} for b in EDGE_BUCKETS
    }

    # Cache asof rows: each unique (pid, date, venue, opp) -> features.
    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    t0 = time.time()
    for i, r in enumerate(all_rows):
        stat = r["stat"].lower()
        acc = per_stat[stat]
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            acc["skip"]["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            acc["skip"]["no_pid"] += 1
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
            acc["skip"]["no_history"] += 1
            continue

        try:
            if stat == "pts":
                pred = _predict_pts(models["pts"], feat)
                if pred is None:
                    acc["skip"]["model_missing"] += 1
                    continue
            elif stat == "ast" and isinstance(models.get("ast"), tuple):
                _, ast_model = models["ast"]
                # treat AST q50 as a log1p stat (same family as other counts).
                pred = _predict_qstat("ast", ast_model, feat)
            else:
                pred = _predict_qstat(stat, models[stat], feat)
        except Exception as e:
            acc["skip"][f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)

        acc["n_pred"] += 1
        acc["mae_actual"].append(abs(pred - actual))
        acc["mae_line"].append(abs(pred - line))

        if rec != "NO_BET":
            if actual_result == "PUSH":
                acc["pushes"] += 1
            else:
                acc["n_bets"] += 1
                win = (rec == actual_result)
                if win:
                    acc["wins"] += 1
                else:
                    acc["losses"] += 1
                b = _bucket_of(abs(edge))
                if b is not None:
                    bucket_acc[b]["n_bets"] += 1
                    if win:
                        bucket_acc[b]["wins"] += 1
                    else:
                        bucket_acc[b]["losses"] += 1

        if (i + 1) % 1000 == 0:
            print(f"   ...{i+1}/{len(all_rows)} ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s")

    profit_per_win = _odds_to_decimal_profit(-110)

    # Compute per-stat aggregates.
    per_stat_summary: Dict[str, dict] = {}
    for s, acc in per_stat.items():
        bets = acc["n_bets"]
        wins = acc["wins"]
        roi_u = wins * profit_per_win - (bets - wins) * 1.0
        hit = (wins / bets) if bets else 0.0
        roi_pct = (roi_u / bets * 100.0) if bets else 0.0
        pnl_dollars = roi_u * BET_SIZE
        per_stat_summary[s] = {
            "n_pred": acc["n_pred"],
            "n_bets": bets,
            "wins": wins,
            "losses": acc["losses"],
            "pushes": acc["pushes"],
            "hit_rate": hit,
            "roi_pct": roi_pct,
            "roi_units": roi_u,
            "pnl_dollars": pnl_dollars,
            "mae_actual": (sum(acc["mae_actual"]) / len(acc["mae_actual"])
                           if acc["mae_actual"] else 0.0),
            "mae_line": (sum(acc["mae_line"]) / len(acc["mae_line"])
                         if acc["mae_line"] else 0.0),
            "skip": dict(acc["skip"]),
        }

    # Pooled total.
    total_bets = sum(d["n_bets"] for d in per_stat_summary.values())
    total_wins = sum(d["wins"] for d in per_stat_summary.values())
    total_pushes = sum(d["pushes"] for d in per_stat_summary.values())
    total_losses = sum(d["losses"] for d in per_stat_summary.values())
    total_pred = sum(d["n_pred"] for d in per_stat_summary.values())
    total_roi_units = (total_wins * profit_per_win
                       - (total_bets - total_wins) * 1.0)
    total_hit = (total_wins / total_bets) if total_bets else 0.0
    total_roi_pct = (total_roi_units / total_bets * 100.0) if total_bets else 0.0
    total_pnl_dollars = total_roi_units * BET_SIZE
    pnl_delta_vs_iter4 = ITER4_TOTAL_PNL - total_pnl_dollars

    # Edge-bucket roll-up.
    bucket_summary = []
    for b in EDGE_BUCKETS:
        d = bucket_acc[b]
        bn = d["n_bets"]
        bw = d["wins"]
        bu = bw * profit_per_win - (bn - bw) * 1.0
        bh = (bw / bn) if bn else 0.0
        br = (bu / bn * 100.0) if bn else 0.0
        bucket_summary.append({
            "lo": b[0], "hi": b[1], "n_bets": bn, "wins": bw,
            "hit_rate": bh, "roi_pct": br, "roi_units": bu,
            "pnl_dollars": bu * BET_SIZE,
        })

    return {
        "per_stat": per_stat_summary,
        "totals": {
            "n_pred": total_pred,
            "n_bets": total_bets,
            "wins": total_wins,
            "losses": total_losses,
            "pushes": total_pushes,
            "hit_rate": total_hit,
            "roi_pct": total_roi_pct,
            "roi_units": total_roi_units,
            "pnl_dollars": total_pnl_dollars,
            "pnl_delta_vs_iter4": pnl_delta_vs_iter4,
        },
        "buckets": bucket_summary,
        "have_ast": have_ast,
        "elapsed_sec": elapsed,
    }


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def save_report(result: dict) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    per = result["per_stat"]
    tot = result["totals"]
    bkt = result["buckets"]

    L: List[str] = []
    L.append("# Honest Aggregate OOS Backtest - iter-9\n")
    L.append("Replays the 2024 NBA playoffs closing-line slate row-by-row using")
    L.append("only the leak-clean OOS artifacts (training cutoff 2024-04-21) for")
    L.append("each stat, then pools the results to produce the realistic")
    L.append("operational picture iter-4 was missing.\n")
    L.append(f"- threshold: |edge| > {THRESHOLD}")
    L.append(f"- bet sizing: flat ${BET_SIZE:.0f} per bet @ -110")
    L.append(f"- elapsed: {result['elapsed_sec']:.1f}s")
    L.append(f"- AST OOS artifact present: {result['have_ast']}\n")

    L.append("## Per-stat results (OOS)")
    L.append("| Stat | n_pred | n_bets | hit% | ROI@-110 | PnL @$100 | iter-4 IS hit% | Δ hit pp |")
    L.append("|------|------:|------:|-----:|---------:|----------:|---------------:|---------:|")
    order = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    for s in order:
        if s not in per:
            ref = IS_REF.get(s, {})
            iter4_hit = ref.get("hit", 0.0)
            L.append(f"| {s.upper()} | skipped | - | - | - | - | "
                     f"{iter4_hit*100:.2f}% | skipped |")
            continue
        d = per[s]
        ref = IS_REF.get(s, {})
        iter4_hit = ref.get("hit", 0.0)
        delta_pp = (d["hit_rate"] - iter4_hit) * 100
        L.append(
            f"| {s.upper()} | {d['n_pred']} | {d['n_bets']} | "
            f"{d['hit_rate']*100:.2f}% | {d['roi_pct']:+.2f}% | "
            f"${d['pnl_dollars']:+,.0f} | {iter4_hit*100:.2f}% | "
            f"{delta_pp:+.2f} |"
        )
    L.append(
        f"| **TOTAL** | **{tot['n_pred']}** | **{tot['n_bets']}** | "
        f"**{tot['hit_rate']*100:.2f}%** | **{tot['roi_pct']:+.2f}%** | "
        f"**${tot['pnl_dollars']:+,.0f}** | - | - |"
    )
    L.append("")

    L.append("## Aggregate vs iter-4 in-sample claim")
    L.append("| metric | iter-4 (in-sample, claimed) | iter-9 (honest OOS) | delta |")
    L.append("|--------|---:|---:|---:|")
    L.append(f"| n_bets | {ITER4_TOTAL_BETS} | {tot['n_bets']} | {tot['n_bets']-ITER4_TOTAL_BETS:+d} |")
    L.append(f"| ROI @-110 | {ITER4_TOTAL_ROI_PCT:+.2f}% | {tot['roi_pct']:+.2f}% | {tot['roi_pct']-ITER4_TOTAL_ROI_PCT:+.2f}pp |")
    L.append(f"| PnL @ $100 | ${ITER4_TOTAL_PNL:+,.0f} | ${tot['pnl_dollars']:+,.0f} | ${tot['pnl_dollars']-ITER4_TOTAL_PNL:+,.0f} |")
    L.append("")
    L.append(f"**Leak-inflation magnitude (iter-4 minus honest OOS PnL):** "
             f"${tot['pnl_delta_vs_iter4']:+,.0f}")
    L.append("")

    L.append("## Edge-magnitude stratification (pooled across stats)")
    L.append("| |edge| bucket | n_bets | wins | hit% | ROI@-110 | PnL @$100 |")
    L.append("|---|------:|----:|-----:|---------:|----------:|")
    for b in bkt:
        hi_label = "inf" if b["hi"] == float("inf") else f"{b['hi']:.2f}"
        L.append(
            f"| [{b['lo']:.2f}, {hi_label}) | {b['n_bets']} | {b['wins']} | "
            f"{b['hit_rate']*100:.2f}% | {b['roi_pct']:+.2f}% | "
            f"${b['pnl_dollars']:+,.0f} |"
        )
    L.append("")

    # Recommended bet menu.
    keep, cut = [], []
    for s in order:
        if s not in per:
            continue
        d = per[s]
        if d["n_bets"] < 30:
            cut.append((s, "INSUFFICIENT VOLUME (<30 bets)"))
            continue
        # Break-even @ -110 = 52.38%; >= 54% gives meaningful ROI cushion.
        if d["hit_rate"] >= 0.54 and d["roi_pct"] >= 3.0:
            keep.append((s, f"hit={d['hit_rate']*100:.2f}% ROI={d['roi_pct']:+.2f}%"))
        else:
            cut.append((s, f"hit={d['hit_rate']*100:.2f}% ROI={d['roi_pct']:+.2f}%"))

    L.append("## Recommended bet menu")
    L.append("**Keep:**")
    if keep:
        for s, reason in keep:
            L.append(f"- {s.upper()}: {reason}")
    else:
        L.append("- (none)")
    L.append("")
    L.append("**Cut:**")
    if cut:
        for s, reason in cut:
            L.append(f"- {s.upper()}: {reason}")
    else:
        L.append("- (none)")
    L.append("")

    # Key questions
    L.append("## Key questions")
    realistic = tot["roi_pct"]
    L.append(f"- **Realistic ROI on a similar slate today:** {realistic:+.2f}% "
             f"@-110 across {tot['n_bets']} bets, or "
             f"${tot['pnl_dollars']:+,.0f} at flat $100/bet.")
    # PTS + STL recommendation
    pts_hit = per.get("pts", {}).get("hit_rate", 0)
    stl_hit = per.get("stl", {}).get("hit_rate", 0)
    pts_roi = per.get("pts", {}).get("roi_pct", 0)
    stl_roi = per.get("stl", {}).get("roi_pct", 0)
    L.append(f"- **Cut PTS + STL?** PTS OOS hit={pts_hit*100:.2f}% ROI={pts_roi:+.2f}%; "
             f"STL OOS hit={stl_hit*100:.2f}% ROI={stl_roi:+.2f}%. "
             "See bet menu above for the rule (hit>=54% and ROI>=+3% to keep).")
    # High-conviction bucket.
    hi_bucket = bkt[-1]
    L.append(f"- **High-conviction (|edge| > 1.5) still profitable?** "
             f"n={hi_bucket['n_bets']}, hit={hi_bucket['hit_rate']*100:.2f}%, "
             f"ROI={hi_bucket['roi_pct']:+.2f}%.")
    L.append("")

    L.append("## Quirks / caveats")
    L.append("- AST has no OOS artifact in iter-9 (parallel agent in flight). "
             "Excluded from totals - the honest aggregate is naturally lower-bound on "
             "n_bets than the iter-4 in-sample claim's 2,065.")
    L.append("- PTS NNLS weights come from `meta_weights_pergame.json` written by the "
             "iter-8 OOS retrain (val_nnls_3way), NOT the production weights.")
    L.append("- TOV: canonical CSV contains TOV rows but iter-7 reported 0. iter-9 "
             "uses the same predict path - if n_bets is still 0 here it's a CSV "
             "thresholding effect (edges too small to clear |edge|>0.5).")
    L.append("- Predictions for q50 stats use the raw q50 inverse-transform (no "
             "garbage-time haircut/residual head). PTS receives the full cycle-96a "
             "stack to match production behavior.")
    L.append("- Skip reasons per stat:")
    for s, d in per.items():
        if d["skip"]:
            L.append(f"  - {s}: {d['skip']}")
    L.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  Report -> {REPORT_PATH}")


def main() -> None:
    result = run()
    # Print summary to stdout.
    tot = result["totals"]
    print("\n  AGGREGATE OOS:")
    print(f"    n_pred={tot['n_pred']}  n_bets={tot['n_bets']}  "
          f"hit={tot['hit_rate']*100:.2f}%  ROI={tot['roi_pct']:+.2f}%  "
          f"PnL=${tot['pnl_dollars']:+,.0f}")
    print(f"    iter-4 IS claim: {ITER4_TOTAL_BETS} bets / {ITER4_TOTAL_ROI_PCT:+.2f}% / ${ITER4_TOTAL_PNL:+,.0f}")
    print(f"    leak-inflation: ${result['totals']['pnl_delta_vs_iter4']:+,.0f}")
    save_report(result)


if __name__ == "__main__":
    main()
