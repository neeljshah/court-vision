"""threshold_sweep_extended.py — iter-25 |edge| threshold sweep on EXTENDED OOS pool.

Replicates iter-18's threshold sweep but on `extended_oos_canonical.csv`
(10,927 rows from iter-24; spans 2024 playoffs + 2026 regular season).
Strategy D filter (BLK / FG3M / STL).

Decomposes results by era:
  - playoffs:  date <= 2024-05-23
  - regseason: date >= 2026-01-28

Quirks:
  - benashkar_2026 (2026 portion) has no BLK/STL — only FG3M can compare
    eras meaningfully.

Outputs:
  vault/Reports/iter25_threshold_sweep_extended.md
  data/cache/iter25_threshold_sweep_extended.json

Constraints respected:
  - Reuses iter-6 leak-safe `_build_asof_row`.
  - Does NOT modify production OOS models or canonical CSVs.
  - LOCAL only.
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
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "extended_oos_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "iter25_threshold_sweep_extended.md")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                          "iter25_threshold_sweep_extended.json")

STATS = ("blk", "fg3m", "stl")
BET_SIZE = 100.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)

THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(27)]  # 0.20..1.50

# iter-18 reference table (canonical playoffs CSV, n=5,108)
ITER18_REF = {
    0.30: {"n_bets": 1984, "pnl": 39473.0},
    0.35: {"n_bets": 1897, "pnl": 39200.0},
    0.40: {"n_bets": 1742, "pnl": 36800.0},
    0.45: {"n_bets": 1545, "pnl": 32700.0},
    0.50: {"n_bets": 418,  "pnl": 12036.0},
    0.55: {"n_bets": 363,  "pnl": 10500.0},
    0.60: {"n_bets": 305,  "pnl": 8900.0},
}

PLAYOFFS_CUTOFF = "2024-05-23"
REGSEASON_START = "2026-01-28"


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


def _era_of(date_str: str) -> str:
    if date_str <= PLAYOFFS_CUTOFF:
        return "playoffs"
    if date_str >= REGSEASON_START:
        return "regseason"
    return "other"


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


def _build_predictions() -> List[dict]:
    print(f"  oos_dir:   {OOS_DIR}")
    print(f"  csv:       {CSV_PATH}")
    print(f"  stats:     {STATS}")
    print(f"  bet size:  ${BET_SIZE:.0f} flat @ -110 "
          f"(profit ratio {PROFIT_RATIO_AT_M110:.4f})")

    models: Dict[str, object] = {}
    for s in STATS:
        m = _load_qstat_xgb(s)
        if m is None:
            print(f"  FATAL: missing OOS artifact for {s}")
            sys.exit(1)
        models[s] = m
    print(f"  loaded models: {list(models.keys())}")

    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)
    print(f"  CSV rows for BLK/FG3M/STL: {len(rows)}")
    era_counts = defaultdict(int)
    for r in rows:
        era_counts[_era_of(r["date"])] += 1
    print(f"  by era: {dict(era_counts)}")

    names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in names:
        name2pid[nm] = _resolve_player_id(nm)
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_resolved}/{len(names)} players")

    preds: List[dict] = []
    skips: Dict[str, int] = defaultdict(int)
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
            pred = _predict_qstat(stat, models[stat], feat)
        except Exception as e:
            skips[f"err:{type(e).__name__}"] += 1
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
            "era": _era_of(r["date"]),
            "player": r["player"],
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


def _pnl(stake: float, outcome: str,
         profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0


def _sweep_one(preds: List[dict], threshold: float,
               era_filter: Optional[str] = None,
               stat_filter: Optional[str] = None) -> dict:
    pnl_chrono: List[Tuple[str, float]] = []
    n_bets = wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    for p in preds:
        if era_filter is not None and p["era"] != era_filter:
            continue
        if stat_filter is not None and p["stat"] != stat_filter:
            continue
        if p["outcome"] == "skip":
            continue
        if p["abs_edge"] <= threshold:
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
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0
                                              else 0.0)
    return {
        "threshold": threshold,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2),
        "roi_pct": round(roi, 2),
        "pnl_dollars": round(total_pnl, 2),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 2) if pnl_dd != float("inf") else None),
    }


def _pick_optimum(sweep: List[dict]) -> Optional[dict]:
    candidates = [r for r in sweep if r["n_bets"] >= 50]
    if not candidates:
        candidates = [r for r in sweep if r["n_bets"] > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x["pnl_dollars"])


def _fmt_pnl_dd(v) -> str:
    if v is None:
        return "inf"
    return f"{v:.2f}"


def run() -> dict:
    print("\n  iter-25 EXTENDED Strategy D threshold sweep\n")
    preds = _build_predictions()

    sweep_pooled = [_sweep_one(preds, thr) for thr in THRESHOLDS]
    sweep_playoffs = [_sweep_one(preds, thr, era_filter="playoffs")
                      for thr in THRESHOLDS]
    sweep_regseason = [_sweep_one(preds, thr, era_filter="regseason")
                       for thr in THRESHOLDS]
    sweep_per_stat: Dict[str, List[dict]] = {}
    for s in STATS:
        sweep_per_stat[s] = [_sweep_one(preds, thr, stat_filter=s)
                             for thr in THRESHOLDS]

    optimum = _pick_optimum(sweep_pooled)
    optimum_po = _pick_optimum(sweep_playoffs)
    optimum_rs = _pick_optimum(sweep_regseason)

    return {
        "sweep_pooled": sweep_pooled,
        "sweep_playoffs": sweep_playoffs,
        "sweep_regseason": sweep_regseason,
        "sweep_per_stat": sweep_per_stat,
        "optimum_pooled": optimum,
        "optimum_playoffs": optimum_po,
        "optimum_regseason": optimum_rs,
        "n_preds": len(preds),
        "thresholds": THRESHOLDS,
    }


def save_report(out: dict) -> None:
    L: List[str] = []
    L.append("# Iter-25 — Threshold Sweep on EXTENDED OOS Pool\n")
    L.append(f"Pool: extended_oos_canonical.csv ({out['n_preds']} predictable rows "
             "from 10,927 total).")
    L.append("Stats: BLK / FG3M / STL. Bet size: $100 flat @ -110.")
    L.append("Era split: playoffs (date <= 2024-05-23) vs "
             "regseason (date >= 2026-01-28).\n")

    # iter-18 vs iter-25 head-to-head
    L.append("## Pooled sweep vs iter-18 (canonical 5,108-row playoffs CSV)\n")
    L.append("| threshold | iter-18 n | iter-18 PnL | iter-25 n | iter-25 PnL "
             "| ROI% | hit% | MaxDD | PnL/DD | Δ PnL |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    by_thr = {r["threshold"]: r for r in out["sweep_pooled"]}
    for thr in THRESHOLDS:
        r = by_thr[thr]
        ref = ITER18_REF.get(thr)
        ref_n = f"{ref['n_bets']}" if ref else "—"
        ref_pnl = f"${ref['pnl']:+,.0f}" if ref else "—"
        d_pnl = (f"${r['pnl_dollars'] - ref['pnl']:+,.0f}"
                 if ref else "—")
        L.append(f"| {thr:.2f} | {ref_n} | {ref_pnl} | "
                 f"{r['n_bets']} | ${r['pnl_dollars']:+,.0f} | "
                 f"{r['roi_pct']:+.2f}% | {r['hit_pct']:.2f}% | "
                 f"${r['maxdd_dollars']:,.0f} | {_fmt_pnl_dd(r['pnl_dd'])} | "
                 f"{d_pnl} |")
    L.append("")

    # Per-era decomposition
    L.append("## Per-era decomposition (selected thresholds)\n")
    L.append("| threshold | Playoffs n | Playoffs PnL | Playoffs ROI% | "
             "RegSeason n | RegSeason PnL | RegSeason ROI% |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|")
    sel = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.75, 1.00]
    po = {r["threshold"]: r for r in out["sweep_playoffs"]}
    rs = {r["threshold"]: r for r in out["sweep_regseason"]}
    for thr in sel:
        a = po[thr]
        b = rs[thr]
        L.append(f"| {thr:.2f} | {a['n_bets']} | "
                 f"${a['pnl_dollars']:+,.0f} | {a['roi_pct']:+.2f}% | "
                 f"{b['n_bets']} | ${b['pnl_dollars']:+,.0f} | "
                 f"{b['roi_pct']:+.2f}% |")
    L.append("")

    # Per-stat sweep (selected thresholds)
    L.append("## Per-stat sweep on extended pool (selected thresholds)\n")
    L.append("| stat | thr | n_bets | hit% | ROI% | PnL |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for s in STATS:
        for thr in [0.30, 0.35, 0.45, 0.50]:
            r = next(x for x in out["sweep_per_stat"][s]
                     if abs(x["threshold"] - thr) < 1e-6)
            L.append(f"| {s.upper()} | {thr:.2f} | {r['n_bets']} | "
                     f"{r['hit_pct']:.2f}% | {r['roi_pct']:+.2f}% | "
                     f"${r['pnl_dollars']:+,.0f} |")
    L.append("")

    # Optima
    L.append("## Optima\n")
    op = out["optimum_pooled"]
    if op:
        L.append(f"- **Pooled optimum (max PnL, n_bets>=50):** "
                 f"|edge| > {op['threshold']:.2f}  "
                 f"n={op['n_bets']}  hit={op['hit_pct']:.2f}%  "
                 f"ROI={op['roi_pct']:+.2f}%  PnL=${op['pnl_dollars']:+,.0f}  "
                 f"DD=${op['maxdd_dollars']:,.0f}  "
                 f"PnL/DD={_fmt_pnl_dd(op['pnl_dd'])}.")
    op = out["optimum_playoffs"]
    if op:
        L.append(f"- **Playoffs optimum:** |edge| > {op['threshold']:.2f}  "
                 f"n={op['n_bets']}  ROI={op['roi_pct']:+.2f}%  "
                 f"PnL=${op['pnl_dollars']:+,.0f}.")
    op = out["optimum_regseason"]
    if op:
        L.append(f"- **RegSeason optimum:** |edge| > {op['threshold']:.2f}  "
                 f"n={op['n_bets']}  ROI={op['roi_pct']:+.2f}%  "
                 f"PnL=${op['pnl_dollars']:+,.0f}.")
    L.append("")

    # Quirks
    L.append("## Quirks / caveats\n")
    L.append("- benashkar_2026 (the regular-season contributor) has only "
             "PTS / REB / AST / FG3M lines — STL and BLK are entirely absent "
             "in the 2026 portion. So the regular-season subset reduces to "
             "FG3M-only for Strategy D.")
    L.append("- iter-18 reference PnL/n_bets sourced from "
             "`vault/Reports/iter18_threshold_sweep.md` (canonical 5,108-row "
             "playoffs CSV; -110 odds; $100 flat).")
    L.append("- Walk-forward leak safety: features built via iter-6 "
             "`_build_asof_row` with `asof` = game date.")
    L.append("- Strict `>` comparison on |edge|: exact-threshold bets are "
             "EXCLUDED from each cut.")

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
    print("\n  ===== ITER-25 EXTENDED SWEEP SUMMARY =====")
    op = out["optimum_pooled"]
    if op:
        print(f"  Pooled optimum: |edge| > {op['threshold']:.2f} | "
              f"n={op['n_bets']} hit={op['hit_pct']:.2f}% "
              f"ROI={op['roi_pct']:+.2f}% PnL=${op['pnl_dollars']:+,.0f}")
    op = out["optimum_playoffs"]
    if op:
        print(f"  Playoffs optimum:  |edge| > {op['threshold']:.2f} | "
              f"n={op['n_bets']} ROI={op['roi_pct']:+.2f}% "
              f"PnL=${op['pnl_dollars']:+,.0f}")
    op = out["optimum_regseason"]
    if op:
        print(f"  RegSeason optimum: |edge| > {op['threshold']:.2f} | "
              f"n={op['n_bets']} ROI={op['roi_pct']:+.2f}% "
              f"PnL=${op['pnl_dollars']:+,.0f}")
    sweep = out["sweep_pooled"]
    print("\n  Pooled selected:")
    for thr in [0.30, 0.35, 0.40, 0.45, 0.50]:
        r = next(x for x in sweep if abs(x["threshold"] - thr) < 1e-6)
        print(f"    {thr:.2f}: n={r['n_bets']:5d}  ROI={r['roi_pct']:+.2f}%  "
              f"PnL=${r['pnl_dollars']:+,.0f}")


if __name__ == "__main__":
    main()
