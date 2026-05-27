"""probe_ensemble_oos.py — iter-21 median-of-3 ensemble vs seed-42 single.

iter-20 verified that the OOS BLK/FG3M/STL XGB-q50 models are seed-robust
across seeds {42, 7, 13}: best-threshold cluster [0.30, 0.40], PnL @ 0.35
variance <1.6%. Open question: does a *median-of-3* ensemble materially
outperform the single seed-42 model? Or do the seeds essentially agree?

Pipeline (LOCAL only, no API mutations, no model edits):
  - For each row in playoffs_2024_canonical.csv with stat in {blk,fg3m,stl}
  - Build leak-safe asof feature row via iter-6 `_build_asof_row`
  - Predict with seed=42 OOS XGB, seed=7 OOS XGB, seed=13 OOS XGB
  - In TRANSFORMED space (log1p), take median across 3 seeds
  - Inverse log1p, clip at 0 -> ensemble prediction
  - Sweep |edge| thresholds {0.30, 0.35, 0.40, 0.45, 0.50} comparing
    single-seed-42 vs ensemble: n_bets, hit%, ROI%, PnL, ΔROI
  - Also compute MAE vs actual_value for seed-42 and ensemble per stat
  - Bonus: tonight's WCF G7 slate — ensemble predictions for the 6
    BLK/FG3M/STL bets (predictions_cache_2026-05-27.parquet rows)

Output:
  data/cache/iter21_ensemble_probe.json
  console-print summary table

Verdict:
  - ensemble ROI > seed-42 ROI by >=1pp at the same threshold -> SHIP ensemble
  - else -> KEEP seed-42 (no compute cost benefit)
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
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                          "iter21_ensemble_probe.json")
WCF_G7_CSV = os.path.join(PROJECT_DIR, "data", "cache",
                          "wcf_g7_lines_2026-05-27.csv")

SEED_DIRS = {
    42: os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs"),
    7:  os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs_seed7"),
    13: os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs_seed13"),
}
STATS = ("blk", "fg3m", "stl")
THRESHOLDS = (0.30, 0.35, 0.40, 0.45, 0.50)
BET_SIZE = 100.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)


def _load_xgb(path: str):
    import xgboost as xgb
    if not os.path.exists(path):
        return None
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _load_seed_models() -> Dict[int, Dict[str, object]]:
    out: Dict[int, Dict[str, object]] = {}
    for seed, d in SEED_DIRS.items():
        seed_models: Dict[str, object] = {}
        for stat in STATS:
            p = os.path.join(d, f"quantile_pergame_{stat}_q50.json")
            m = _load_xgb(p)
            if m is None:
                print(f"  FATAL: missing seed={seed} {stat} at {p}")
                sys.exit(1)
            seed_models[stat] = m
        out[seed] = seed_models
        print(f"  seed={seed:>2}: loaded {list(seed_models.keys())} from {d}")
    return out


def _predict_raw_transformed(model, feat_row: Dict[str, float],
                             feat_cols: List[str]) -> float:
    """Predict in TRANSFORMED (log1p) space — no inverse, no clip."""
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in feat_cols]],
                 dtype=float)
    return float(model.predict(X)[0])


def _inverse_clip(stat: str, pred_t: float) -> float:
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _classify_rec(edge: float) -> str:
    if edge > 0:
        return "OVER"
    if edge < 0:
        return "UNDER"
    return "PUSH_LINE"


def _pnl(outcome: str) -> float:
    if outcome == "win":
        return BET_SIZE * PROFIT_RATIO_AT_M110
    if outcome == "loss":
        return -BET_SIZE
    return 0.0


def _build_predictions(seed_models: Dict[int, Dict[str, object]]) -> List[dict]:
    feat_cols = feature_columns()

    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)
    print(f"  CSV rows for BLK/FG3M/STL: {len(rows)}")

    names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in names:
        name2pid[nm] = _resolve_player_id(nm)
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_res}/{len(names)} players")

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
            pred_t = {seed: _predict_raw_transformed(seed_models[seed][stat],
                                                     feat, feat_cols)
                      for seed in (42, 7, 13)}
        except Exception as e:
            skips[f"err:{type(e).__name__}"] += 1
            continue

        # Single-seed-42 prediction (inverse + clip).
        pred_42 = _inverse_clip(stat, pred_t[42])
        # Median in transformed space, then inverse + clip.
        pred_ens_t = float(np.median([pred_t[42], pred_t[7], pred_t[13]]))
        pred_ens = _inverse_clip(stat, pred_ens_t)

        actual_result = _classify_result(actual, line)
        edge_42 = pred_42 - line
        edge_ens = pred_ens - line
        rec_42 = _classify_rec(edge_42)
        rec_ens = _classify_rec(edge_ens)

        def _outcome(rec: str) -> str:
            if rec == "PUSH_LINE":
                return "skip"
            if actual_result == "PUSH":
                return "push"
            return "win" if rec == actual_result else "loss"

        preds.append({
            "date": r["date"], "player": r["player"], "stat": stat,
            "line": line, "actual": actual,
            "pred_42": pred_42, "pred_7": _inverse_clip(stat, pred_t[7]),
            "pred_13": _inverse_clip(stat, pred_t[13]), "pred_ens": pred_ens,
            "edge_42": edge_42, "edge_ens": edge_ens,
            "rec_42": rec_42, "rec_ens": rec_ens,
            "out_42": _outcome(rec_42), "out_ens": _outcome(rec_ens),
        })
        if (i + 1) % 500 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s) "
                  f"preds={len(preds)}")
    print(f"  predicted {len(preds)} rows in {time.time()-t0:.1f}s. "
          f"skips: {dict(skips)}")
    return preds


def _sweep(preds: List[dict], thr: float, who: str) -> dict:
    """who in {'42','ens'}. Returns n_bets/wins/losses/hit/roi/pnl."""
    edge_key = f"edge_{who}"
    out_key = f"out_{who}"
    n_bets = wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    for p in preds:
        if p[out_key] == "skip":
            continue
        if abs(p[edge_key]) <= thr:
            continue
        n_bets += 1
        total_staked += BET_SIZE
        pnl = _pnl(p[out_key])
        total_pnl += pnl
        if p[out_key] == "win":
            wins += 1
        elif p[out_key] == "loss":
            losses += 1
        else:
            pushes += 1
    decisive = wins + losses
    hit = (wins / decisive) if decisive else 0.0
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    return {
        "threshold": thr, "n_bets": n_bets, "wins": wins,
        "losses": losses, "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2),
        "roi_pct": round(roi, 2),
        "pnl_dollars": round(total_pnl, 2),
    }


def _mae_stats(preds: List[dict]) -> Dict[str, Dict[str, float]]:
    by_stat: Dict[str, Dict[str, List[float]]] = {
        s: {"42": [], "ens": []} for s in STATS
    }
    for p in preds:
        by_stat[p["stat"]]["42"].append(abs(p["pred_42"] - p["actual"]))
        by_stat[p["stat"]]["ens"].append(abs(p["pred_ens"] - p["actual"]))
    out: Dict[str, Dict[str, float]] = {}
    for s in STATS:
        a42 = by_stat[s]["42"]; aen = by_stat[s]["ens"]
        m42 = (sum(a42)/len(a42)) if a42 else 0.0
        men = (sum(aen)/len(aen)) if aen else 0.0
        out[s] = {
            "n": len(a42), "mae_42": round(m42, 4),
            "mae_ens": round(men, 4),
            "delta_pct": (round((men - m42) / m42 * 100.0, 3)
                          if m42 > 0 else 0.0),
        }
    return out


def _bet_set_diff(preds: List[dict], thr: float) -> Dict[str, int]:
    """How does the bet SET differ at threshold thr?
    Returns:
        common — bet by both with same rec
        only_42 — bet by 42 only
        only_ens — bet by ens only
        flipped — both bet but disagree on OVER/UNDER
    """
    common = only_42 = only_ens = flipped = 0
    for p in preds:
        bet_42 = (abs(p["edge_42"]) > thr) and (p["out_42"] != "skip")
        bet_en = (abs(p["edge_ens"]) > thr) and (p["out_ens"] != "skip")
        if bet_42 and bet_en:
            if p["rec_42"] == p["rec_ens"]:
                common += 1
            else:
                flipped += 1
        elif bet_42 and not bet_en:
            only_42 += 1
        elif bet_en and not bet_42:
            only_ens += 1
    return {"common": common, "only_42": only_42,
            "only_ens": only_ens, "flipped": flipped}


def _wcf_g7_ensemble(seed_models: Dict[int, Dict[str, object]]) -> List[dict]:
    """Run ensemble predictions on tonight's WCF G7 slate (BLK/FG3M/STL only)."""
    if not os.path.exists(WCF_G7_CSV):
        print(f"  [warn] WCF G7 csv missing at {WCF_G7_CSV}; skipping bonus.")
        return []
    feat_cols = feature_columns()
    rows: List[dict] = []
    with open(WCF_G7_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)
    print(f"  WCF G7 BLK/FG3M/STL rows: {len(rows)}")

    names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in names:
        name2pid[nm] = _resolve_player_id(nm)

    d = datetime.fromisoformat("2026-05-27")
    season = _season_for_date(d)
    out: List[dict] = []
    for r in rows:
        stat = r["stat"].lower()
        try:
            line = float(r["line"])
        except Exception:
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            continue
        is_home = (r["venue"] == "home")
        feat = _build_asof_row(
            pid, r["opp"], d, season, is_home=is_home,
            rest_days=2.0, gamelog_dir=GAMELOG_DIR,
        )
        if feat is None:
            continue
        try:
            pt = {seed: _predict_raw_transformed(seed_models[seed][stat],
                                                 feat, feat_cols)
                  for seed in (42, 7, 13)}
        except Exception:
            continue
        pred_42 = _inverse_clip(stat, pt[42])
        pred_ens = _inverse_clip(stat, float(np.median(list(pt.values()))))
        edge_42 = pred_42 - line
        edge_ens = pred_ens - line
        rec_42 = _classify_rec(edge_42)
        rec_ens = _classify_rec(edge_ens)
        flipped = (rec_42 != rec_ens) and (rec_42 != "PUSH_LINE") \
                  and (rec_ens != "PUSH_LINE")
        out.append({
            "player": r["player"], "stat": stat, "line": line,
            "pred_42": round(pred_42, 3), "pred_ens": round(pred_ens, 3),
            "edge_42": round(edge_42, 3), "edge_ens": round(edge_ens, 3),
            "rec_42": rec_42, "rec_ens": rec_ens,
            "flipped": flipped,
        })
    return out


def main() -> None:
    print(f"\n  iter-21 ensemble probe — median-of-3 vs seed-42\n")
    seed_models = _load_seed_models()

    preds = _build_predictions(seed_models)

    # Sweep at THRESHOLDS for both who={42, ens}, pooled BLK+FG3M+STL.
    sweep_pooled: List[dict] = []
    for thr in THRESHOLDS:
        s42 = _sweep(preds, thr, "42")
        sen = _sweep(preds, thr, "ens")
        bsd = _bet_set_diff(preds, thr)
        sweep_pooled.append({
            "threshold": thr,
            "seed42": s42,
            "ensemble": sen,
            "delta_roi_pp": round(sen["roi_pct"] - s42["roi_pct"], 2),
            "delta_n_bets": sen["n_bets"] - s42["n_bets"],
            "delta_pnl": round(sen["pnl_dollars"]
                               - s42["pnl_dollars"], 2),
            "bet_set_diff": bsd,
        })

    # Per-stat sweep at the iter-18 optimum 0.35.
    by_stat: Dict[str, Dict[str, dict]] = {}
    THR_FOCUS = 0.35
    for s in STATS:
        sub = [p for p in preds if p["stat"] == s]
        by_stat[s] = {
            "seed42": _sweep(sub, THR_FOCUS, "42"),
            "ensemble": _sweep(sub, THR_FOCUS, "ens"),
        }

    mae_block = _mae_stats(preds)

    wcf_bonus = _wcf_g7_ensemble(seed_models)

    # Verdict: at the iter-18 optimum thr=0.35, is ensemble ROI >= seed42 ROI + 1pp?
    iter18_optimum = next(x for x in sweep_pooled
                          if abs(x["threshold"] - 0.35) < 1e-6)
    delta_at_035 = iter18_optimum["delta_roi_pp"]
    if delta_at_035 >= 1.0:
        verdict = "SHIP_ENSEMBLE"
    elif delta_at_035 <= -1.0:
        verdict = "KEEP_SEED_42_ENSEMBLE_HURTS"
    else:
        verdict = "KEEP_SEED_42_ENSEMBLE_NEUTRAL"

    out = {
        "iter": 21,
        "n_preds": len(preds),
        "thresholds_swept": list(THRESHOLDS),
        "sweep_pooled": sweep_pooled,
        "per_stat_at_0_35": by_stat,
        "mae_per_stat": mae_block,
        "wcf_g7_bonus": wcf_bonus,
        "verdict": verdict,
        "delta_roi_pp_at_035": delta_at_035,
    }
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\n  cache -> {CACHE_PATH}")

    # ────── console summary ──────
    print("\n  ===== MAE per stat (lower=better) =====")
    print(f"  {'stat':<6}{'n':>6}  {'mae_42':>9}  {'mae_ens':>9}  {'delta%':>9}")
    for s in STATS:
        m = mae_block[s]
        print(f"  {s:<6}{m['n']:>6}  {m['mae_42']:>9.4f}  {m['mae_ens']:>9.4f}  "
              f"{m['delta_pct']:>+9.3f}")

    print("\n  ===== threshold sweep (pooled BLK+FG3M+STL) =====")
    print(f"  {'thr':>5}  {'s42_n':>6} {'s42_hit%':>9} {'s42_ROI%':>9} "
          f"{'ens_n':>6} {'ens_hit%':>9} {'ens_ROI%':>9} {'ΔROI':>8} "
          f"{'flip':>5}")
    for row in sweep_pooled:
        a = row["seed42"]; b = row["ensemble"]
        bsd = row["bet_set_diff"]
        print(f"  {row['threshold']:>5.2f}  "
              f"{a['n_bets']:>6} {a['hit_pct']:>9.2f} {a['roi_pct']:>+9.2f} "
              f"{b['n_bets']:>6} {b['hit_pct']:>9.2f} {b['roi_pct']:>+9.2f} "
              f"{row['delta_roi_pp']:>+8.2f} {bsd['flipped']:>5}")

    print("\n  ===== per-stat @ thr=0.35 =====")
    for s in STATS:
        a = by_stat[s]["seed42"]; b = by_stat[s]["ensemble"]
        print(f"  {s:<6} seed42: n={a['n_bets']:>4} hit={a['hit_pct']:.2f}% "
              f"ROI={a['roi_pct']:+.2f}%   "
              f"ens: n={b['n_bets']:>4} hit={b['hit_pct']:.2f}% "
              f"ROI={b['roi_pct']:+.2f}%")

    print(f"\n  ===== verdict: {verdict} =====")
    print(f"  ΔROI at thr=0.35: {delta_at_035:+.2f}pp")

    if wcf_bonus:
        print("\n  ===== WCF G7 ensemble predictions (BLK/FG3M/STL only) =====")
        print(f"  {'player':<30} {'stat':>5} {'line':>5} {'p42':>6} "
              f"{'pens':>6} {'e42':>6} {'eens':>6} {'r42':>5} {'rens':>5} flip")
        any_flip = False
        for w in wcf_bonus:
            flag = "FLIP" if w["flipped"] else ""
            if w["flipped"]:
                any_flip = True
            print(f"  {w['player']:<30} {w['stat']:>5} {w['line']:>5.1f} "
                  f"{w['pred_42']:>6.2f} {w['pred_ens']:>6.2f} "
                  f"{w['edge_42']:>+6.2f} {w['edge_ens']:>+6.2f} "
                  f"{w['rec_42']:>5} {w['rec_ens']:>5} {flag}")
        print(f"\n  WCF G7 flips (OVER<->UNDER): {sum(1 for w in wcf_bonus if w['flipped'])}/{len(wcf_bonus)}")


if __name__ == "__main__":
    main()
