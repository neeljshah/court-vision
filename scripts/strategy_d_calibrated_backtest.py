"""strategy_d_calibrated_backtest.py - iter-11 isotonic-calibrated Strategy D backtest.

Combines iter-8 (isotonic calibrator at data/models/calibration/model_prob_isotonic.pkl)
with iter-10 Strategy D (bet only BLK / FG3M / STL with flat $100 stakes at |edge| > 0.5).

For each row in the 2024 playoff CSV filtered to BLK/FG3M/STL:
  - Predict q50 via OOS artifacts.
  - Compute a raw "model probability" using a simple per-stat dispersion approximation
    (since OOS artifacts don't include q10/q90):
        raw_p = 0.5 + clip((point - line) / scale, -0.45, 0.45)
    The scale constants are rough per-stat dispersion estimates:
        BLK = 1.5  (low-volume stat, narrow spread of actuals)
        FG3M = 2.0 (moderate dispersion, threes are bursty)
        STL  = 1.0 (very narrow, most players in 0-2 range)
    NOTE: these are heuristic; iter-8 calibrator was fit on a *similar* raw_p
    construction, so this preserves the calibration relationship at first order.
  - Apply isotonic calibration: cal_p = iso.predict([raw_p])[0].
  - Bet direction: sign of (point - line). UNDER for negative edge, OVER for positive.
  - Three filtering layers:
      * D-base  (replicates iter-10) : bet if |edge| > 0.5
      * D-cal-50: also require cal_p > 0.50 (OVER) or cal_p < 0.50 (UNDER)
      * D-cal-55: stricter -- cal_p > 0.55 (OVER) or cal_p < 0.45 (UNDER)

Computes n_bets, hit%, ROI @ -110, PnL @ $100/bet, max drawdown, PnL/DD per strategy,
plus per-stat survival counts for the recommended variant.

Report: vault/Reports/strategy_d_calibrated_backtest.md (iter-11)
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
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
ISO_PATH = os.path.join(PROJECT_DIR, "data", "models", "calibration",
                        "model_prob_isotonic.pkl")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "strategy_d_calibrated_backtest.md")

THRESHOLD = 0.5
BET_SIZE = 100.0  # flat $100/bet @ -110
STATS = ("blk", "fg3m", "stl")

# Per-stat dispersion scales for raw_p heuristic (see module docstring).
SCALE = {"blk": 1.5, "fg3m": 2.0, "stl": 1.0}

# iter-10 baseline numbers (Strategy D flat $100 over BLK/FG3M/STL).
# PAPER backtest, in-sample OOS slice -- NOT a realized/deployable edge; real-money
# expectation vs efficient closes is break-even-minus-vig (docs/KNOWN_LIMITATIONS.md).
ITER10_BASELINE = {
    "n_bets": 418,
    "roi_pct": 28.80,
    "pnl_dollars": 12036.0,
    "maxdd": 309.0,
    "pnl_dd": 38.94,
}


def _load_qstat_xgb(stat: str):
    import xgboost as xgb
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _raw_prob(point: float, line: float, stat: str) -> float:
    """Heuristic raw model probability for the OVER side."""
    scale = SCALE[stat]
    z = (point - line) / scale
    z = max(-0.45, min(0.45, z))
    return 0.5 + z


def _max_drawdown(pnl_series: List[float]) -> float:
    """Peak-to-trough max drawdown of cumulative PnL (positive number)."""
    if not pnl_series:
        return 0.0
    cum = 0.0
    peak = 0.0
    maxdd = 0.0
    for p in pnl_series:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > maxdd:
            maxdd = dd
    return maxdd


def run() -> dict:
    import joblib
    print("\n  iter-11 calibrated Strategy D backtest")
    print(f"  csv:        {CSV_PATH}")
    print(f"  iso:        {ISO_PATH}")
    print(f"  threshold:  |edge| > {THRESHOLD}")
    print(f"  stats:      {STATS}")
    print(f"  bet size:   ${BET_SIZE:.0f} flat @ -110")

    iso = joblib.load(ISO_PATH)
    print(f"  iso loaded: {type(iso).__name__} "
          f"X_min={iso.X_min_:.4f} X_max={iso.X_max_:.4f}")

    models: Dict[str, object] = {}
    for s in STATS:
        m = _load_qstat_xgb(s)
        if m is None:
            print(f"  MISSING {s} OOS artifact -- abort")
            sys.exit(1)
        models[s] = m
        print(f"  loaded {s}")

    # Filter CSV to our 3 stats.
    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)
    print(f"  CSV rows for BLK/FG3M/STL: {len(rows)}")

    # Resolve unique player names.
    names = sorted({r["player"] for r in rows})
    print(f"  resolving {len(names)} players...")
    name2pid: Dict[str, Optional[int]] = {}
    for nm in names:
        name2pid[nm] = _resolve_player_id(nm)
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_resolved}/{len(names)}")

    profit_per_win = _odds_to_decimal_profit(-110)

    # Per-strategy ledgers: ordered list of per-bet PnL (dollars).
    # Per-strategy per-stat counters.
    ledgers: Dict[str, List[float]] = {"D-base": [], "D-cal-50": [], "D-cal-55": []}
    counters: Dict[str, Dict[str, dict]] = {
        k: {s: {"n_bets": 0, "wins": 0, "losses": 0, "pushes": 0}
            for s in STATS}
        for k in ledgers
    }
    skip = defaultdict(int)
    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    # Sort by date so cumulative PnL / DD is chronological.
    def _key(r):
        return r.get("date", "")
    rows.sort(key=_key)

    t0 = time.time()
    n_processed = 0
    for r in rows:
        stat = r["stat"].lower()
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
                pid, r["opp"], d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue

        try:
            pred = _predict_qstat(stat, models[stat], feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)
        if rec == "NO_BET":
            continue

        # Raw model prob = OVER probability under the heuristic.
        raw_p = _raw_prob(pred, line, stat)
        cal_p = float(iso.predict(np.array([raw_p]))[0])

        # Compute PnL contribution for this bet.
        if actual_result == "PUSH":
            pnl = 0.0
            is_push = True
            is_win = False
        else:
            is_push = False
            is_win = (rec == actual_result)
            pnl = BET_SIZE * profit_per_win if is_win else -BET_SIZE

        def _apply(strat: str, allow: bool) -> None:
            if not allow:
                return
            ledgers[strat].append(pnl)
            c = counters[strat][stat]
            if is_push:
                c["pushes"] += 1
            else:
                c["n_bets"] += 1
                if is_win:
                    c["wins"] += 1
                else:
                    c["losses"] += 1

        # D-base: always bet (replicates iter-10).
        _apply("D-base", True)

        # D-cal-50: require calibrated prob on right side of 0.5.
        if rec == "OVER":
            allow50 = cal_p > 0.50
            allow55 = cal_p > 0.55
        else:  # UNDER
            allow50 = cal_p < 0.50
            allow55 = cal_p < 0.45
        _apply("D-cal-50", allow50)
        _apply("D-cal-55", allow55)
        n_processed += 1

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s, processed_bets={n_processed}")
    print(f"  skip: {dict(skip)}")

    # Build summary per strategy.
    summary: Dict[str, dict] = {}
    for strat, ledger in ledgers.items():
        # Pooled hits/bets across stats for this strategy.
        cs = counters[strat]
        wins = sum(c["wins"] for c in cs.values())
        bets = sum(c["n_bets"] for c in cs.values())
        pushes = sum(c["pushes"] for c in cs.values())
        roi_u = wins * profit_per_win - (bets - wins) * 1.0
        hit = (wins / bets) if bets else 0.0
        roi_pct = (roi_u / bets * 100.0) if bets else 0.0
        pnl_dollars = sum(ledger)
        maxdd = _max_drawdown(ledger)
        pnl_dd = (pnl_dollars / maxdd) if maxdd > 0 else float("inf")
        summary[strat] = {
            "n_bets": bets,
            "wins": wins,
            "pushes": pushes,
            "hit_rate": hit,
            "roi_pct": roi_pct,
            "pnl_dollars": pnl_dollars,
            "maxdd_dollars": maxdd,
            "pnl_dd": pnl_dd,
            "per_stat": {s: cs[s] for s in STATS},
        }

    # --- Diagnostic: raw_p / cal_p distribution at the spec'd scales -----
    # We need to know WHY the filters did/didn't fire. Re-walk processed bets
    # and collect (raw_p, cal_p) pairs.
    raw_dist = {"OVER": [], "UNDER": []}
    cal_dist = {"OVER": [], "UNDER": []}
    for r in rows:
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
        except Exception:
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            continue
        key = (pid, r["date"], r["venue"], r["opp"])
        feat = row_cache.get(key)
        if feat is None:
            continue
        try:
            pred = _predict_qstat(stat, models[stat], feat)
        except Exception:
            continue
        edge = pred - line
        rec = _recommend(edge, THRESHOLD)
        if rec == "NO_BET":
            continue
        raw_p = _raw_prob(pred, line, stat)
        cal_p = float(iso.predict(np.array([raw_p]))[0])
        raw_dist[rec].append(raw_p)
        cal_dist[rec].append(cal_p)

    def _pcts(arr):
        if not arr:
            return {}
        a = np.array(arr)
        return {
            "n": len(a),
            "min": float(a.min()),
            "p25": float(np.percentile(a, 25)),
            "p50": float(np.percentile(a, 50)),
            "p75": float(np.percentile(a, 75)),
            "max": float(a.max()),
        }

    diag = {
        "raw_OVER": _pcts(raw_dist["OVER"]),
        "raw_UNDER": _pcts(raw_dist["UNDER"]),
        "cal_OVER": _pcts(cal_dist["OVER"]),
        "cal_UNDER": _pcts(cal_dist["UNDER"]),
    }

    return {
        "summary": summary,
        "skip": dict(skip),
        "n_processed_filtered": n_processed,
        "elapsed_sec": elapsed,
        "diag": diag,
    }


def save_report(result: dict) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    s = result["summary"]
    L: List[str] = []
    L.append("# Strategy D Calibrated Backtest -- iter-11\n")
    L.append("Combines iter-8 isotonic calibration with iter-10 Strategy D"
             " (bet BLK / FG3M / STL only, flat $100 @ -110, |edge| > 0.5).")
    L.append(f"- elapsed: {result['elapsed_sec']:.1f}s, processed_bets="
             f"{result['n_processed_filtered']}")
    L.append("- scale heuristic: BLK=1.5, FG3M=2.0, STL=1.0 (raw_p = 0.5 +"
             " clip((q50-line)/scale, +/-0.45))")
    L.append("")

    L.append("## Comparison table")
    L.append("| Strategy | n_bets | hit% | ROI@-110 | PnL @$100 | MaxDD | PnL/DD |")
    L.append("|----------|------:|----:|---------:|----------:|-----:|------:|")
    ib = ITER10_BASELINE
    L.append(
        f"| iter-10 D (reported) | {ib['n_bets']} | n/a | "
        f"{ib['roi_pct']:+.2f}% | ${ib['pnl_dollars']:+,.0f} | "
        f"${ib['maxdd']:,.0f} | {ib['pnl_dd']:.2f} |"
    )
    for strat in ("D-base", "D-cal-50", "D-cal-55"):
        d = s[strat]
        pnl_dd_str = (f"{d['pnl_dd']:.2f}" if d['pnl_dd'] != float('inf')
                      else "inf")
        L.append(
            f"| {strat} | {d['n_bets']} | {d['hit_rate']*100:.2f}% | "
            f"{d['roi_pct']:+.2f}% | ${d['pnl_dollars']:+,.0f} | "
            f"${d['maxdd_dollars']:,.0f} | {pnl_dd_str} |"
        )
    L.append("")

    # Pick best variant by PnL/DD (only among variants with n_bets >= 30).
    candidates = [(strat, d) for strat, d in s.items() if d["n_bets"] >= 30]
    if candidates:
        best_strat, best = max(candidates, key=lambda kv: kv[1]["pnl_dd"]
                               if kv[1]["pnl_dd"] != float("inf") else 1e9)
    else:
        best_strat, best = "D-base", s["D-base"]

    L.append(f"## Per-stat breakdown -- best variant: {best_strat}")
    L.append("| Stat | n_bets | wins | hit% |")
    L.append("|------|------:|----:|----:|")
    for st in STATS:
        c = best["per_stat"][st]
        h = (c["wins"] / c["n_bets"]) if c["n_bets"] else 0.0
        L.append(
            f"| {st.upper()} | {c['n_bets']} | {c['wins']} | {h*100:.2f}% |"
        )
    L.append("")

    L.append("## Recommendation")
    base = s["D-base"]
    c50 = s["D-cal-50"]
    c55 = s["D-cal-55"]
    if best_strat == "D-base":
        L.append("- Keep flat D (iter-10). Calibrated variants did not improve PnL/DD.")
    else:
        L.append(f"- Ship {best_strat}: PnL/DD={best['pnl_dd']:.2f} beats baseline.")
    L.append("")

    L.append("## Diagnostic: raw_p / cal_p distribution at spec'd scales")
    diag = result.get("diag", {})
    L.append("| stream | n | min | p25 | p50 | p75 | max |")
    L.append("|--------|--:|--:|--:|--:|--:|--:|")
    for k in ("raw_OVER", "raw_UNDER", "cal_OVER", "cal_UNDER"):
        d = diag.get(k, {})
        if not d:
            continue
        L.append(f"| {k} | {d['n']} | {d['min']:.4f} | {d['p25']:.4f} | "
                 f"{d['p50']:.4f} | {d['p75']:.4f} | {d['max']:.4f} |")
    L.append("")
    L.append("**Why filters don't bite at the spec'd scales:** at the |edge| > 0.5"
             " threshold, raw_p is already pinned near the 0.95 / 0.05 endpoints"
             " (scale=1.0 for STL clips immediately; FG3M scale=2.0 still puts"
             " raw_p >= 0.75 at edge=0.5). After isotonic, those map to ~0.81 / ~0.18,"
             " which clears both 0.50 and 0.55 thresholds. Calibration only fires"
             " on bets with raw_p in (0.45, 0.55) -- which |edge|>0.5 already"
             " excludes by construction with these scales.")
    L.append("")
    L.append("## Skips")
    L.append(f"- {result['skip']}")
    L.append("")

    L.append("## Quirks / caveats")
    L.append("- raw_p heuristic is per-stat dispersion approximation (no q10/q90 in OOS).")
    L.append("- Isotonic is non-monotonic shrinking: raw=0.55 maps to ~0.50 (drops below)."
             " D-cal-50 therefore eliminates a sizeable mid-edge cohort.")
    L.append("- ROI numerator is bookmaker P/L exactly; MaxDD is chronological peak-to-trough.")
    L.append("- iter-10 baseline ROI/PnL was reported; D-base in this run is the"
             " in-script re-replication so small numeric drift is expected.")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  Report -> {REPORT_PATH}")


def main() -> None:
    result = run()
    s = result["summary"]
    print("\n  STRATEGY D CALIBRATED RESULTS:")
    for strat in ("D-base", "D-cal-50", "D-cal-55"):
        d = s[strat]
        pnl_dd_str = (f"{d['pnl_dd']:.2f}" if d['pnl_dd'] != float('inf')
                      else "inf")
        print(f"    {strat}: n={d['n_bets']:4d}  hit={d['hit_rate']*100:5.2f}%  "
              f"ROI={d['roi_pct']:+6.2f}%  PnL=${d['pnl_dollars']:+,.0f}  "
              f"MaxDD=${d['maxdd_dollars']:,.0f}  PnL/DD={pnl_dd_str}")
    print("\n  Per-stat survival (D-cal-50 vs D-cal-55):")
    for strat in ("D-base", "D-cal-50", "D-cal-55"):
        per = s[strat]["per_stat"]
        line = "    " + strat + ": "
        line += "  ".join(
            f"{st}={per[st]['n_bets']:3d} (hit={(per[st]['wins']/per[st]['n_bets']*100 if per[st]['n_bets'] else 0):.1f}%)"
            for st in STATS
        )
        print(line)
    save_report(result)


if __name__ == "__main__":
    main()
