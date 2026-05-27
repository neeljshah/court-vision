"""backtest_blk_oos.py — iter-6 honest OOS backtest for BLK vs 2024 closing lines.

Loads the leak-clean BLK q50 artifact from data/models/oos_pre_playoffs/ (trained
on rows STRICTLY before 2024-04-21) and runs the iter-4 closing-line backtest
using ONLY that artifact for BLK predictions.

This is identical to backtest_closing_lines_2024_playoffs.py except:
  - Filters CSV to stat == "blk" only
  - Predicts via the OOS model directly (NOT the production predict_pergame).
  - Applies the same log1p inverse + zero clip (no garbage-time haircut /
    residual head — we want the raw OOS q50 number for the leak comparison).

Outputs vault/Reports/blk_oos_backtest.md with hit_rate, ROI, MAE_actual,
MAE_line, plus edge-magnitude breakdown.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Match iter-4: disable injury wire for retro fetches.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Reuse the iter-4 helpers directly so the leak-safety guarantees match exactly.
from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns, feature_columns_for  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402
from src.prediction.bet_thresholds import edge_threshold_for  # noqa: E402


STAT = "blk"
CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs",
                              "quantile_pergame_blk_q50.json")
META_PATH = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs",
                         "_meta.json")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports", "blk_oos_backtest.md")
# Iter-15: threshold loaded from central config (bet_thresholds.py)
THRESHOLD = edge_threshold_for(STAT)  # 0.40 as of iter-15


def _load_oos_blk_model():
    import xgboost as xgb
    if not os.path.exists(OOS_MODEL_PATH):
        raise SystemExit(f"  [abort] OOS BLK artifact missing: {OOS_MODEL_PATH}\n"
                         f"          run scripts/retrain_blk_q50_oos.py first")
    m = xgb.XGBRegressor()
    m.load_model(OOS_MODEL_PATH)
    return m


def _predict_blk_oos(model, feature_row: Dict[str, float]) -> float:
    OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
    cols = feature_columns_for(STAT, OOS_DIR)
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    # log1p inverse — BLK is in _LOG_TRANSFORM_STATS.
    pred = float(_inverse(STAT, np.array([pred_t]))[0])
    return max(0.0, pred)


def run() -> dict:
    print(f"\n  iter-6 OOS BLK backtest")
    print(f"  csv:        {CSV_PATH}")
    print(f"  model:      {OOS_MODEL_PATH}")
    print(f"  threshold:  {THRESHOLD}")

    # Load meta for the report.
    meta: Dict = {}
    if os.path.exists(META_PATH):
        meta = json.load(open(META_PATH, encoding="utf-8"))
        _val_mae = meta.get('val_mae')
        _val_mae_str = f"{_val_mae:.4f}" if _val_mae is not None else "N/A"
        print(f"  meta:       cutoff={meta.get('cutoff_date')}  n_train={meta.get('n_train')}  "
              f"val_MAE={_val_mae_str}")

    model = _load_oos_blk_model()

    # Filter to BLK rows only.
    all_rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get("stat", "").lower() == STAT:
                all_rows.append(r)
    print(f"  BLK rows in CSV: {len(all_rows)}")

    unique_names = sorted({r["player"] for r in all_rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Player id resolution: {resolved}/{len(unique_names)} resolved")

    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}
    skip_reasons: Dict[str, int] = defaultdict(int)
    preview_rows: List[Tuple[str, str, float, float, float]] = []

    n_pred = 0
    n_bets = 0
    wins = 0
    losses = 0
    pushes = 0
    abs_err_actual: List[float] = []
    abs_err_line: List[float] = []

    # Edge-magnitude buckets.
    bucket_thresholds = [0.5, 0.75, 1.0]
    buckets = {t: {"n_bets": 0, "wins": 0} for t in bucket_thresholds}

    t0 = time.time()
    for idx, r in enumerate(all_rows):
        player = r["player"]
        opp = r["opp"]
        venue = r["venue"]
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
        except (TypeError, ValueError):
            skip_reasons["bad_numeric"] += 1
            continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_reasons["bad_date"] += 1
            continue
        pid = name2pid.get(player)
        if pid is None:
            skip_reasons["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (venue == "home")
        key = (pid, r["date"], venue, opp)
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, opp, d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat_row = row_cache[key]
        if feat_row is None:
            skip_reasons["no_history"] += 1
            continue

        try:
            pred = _predict_blk_oos(model, feat_row)
        except SystemExit:
            raise
        except Exception as e:
            skip_reasons[f"predict_err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)

        n_pred += 1
        abs_err_actual.append(abs(pred - actual))
        abs_err_line.append(abs(pred - line))

        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                win = (rec == actual_result)
                if win:
                    wins += 1
                else:
                    losses += 1
                # Buckets — count this bet in every bucket whose threshold it clears.
                for bt in bucket_thresholds:
                    if abs(edge) > bt:
                        buckets[bt]["n_bets"] += 1
                        if win:
                            buckets[bt]["wins"] += 1

        if len(preview_rows) < 10:
            preview_rows.append((player, r["date"], pred, line, actual))

        if (idx + 1) % 200 == 0:
            print(f"  ...{idx+1}/{len(all_rows)} processed ({time.time() - t0:.1f}s)")

    elapsed = time.time() - t0
    profit_per_win = _odds_to_decimal_profit(-110)
    roi_units = wins * profit_per_win - (n_bets - wins) * 1.0
    hit_rate = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0
    mae_a = (sum(abs_err_actual) / len(abs_err_actual)) if abs_err_actual else 0.0
    mae_l = (sum(abs_err_line) / len(abs_err_line)) if abs_err_line else 0.0

    print(f"\n  Backtest finished in {elapsed:.1f}s")
    print(f"  Skip reasons: {dict(skip_reasons)}")
    print(f"\n  BLK OOS results:")
    print(f"    n_pred={n_pred} n_bets={n_bets} hit_rate={hit_rate*100:.2f}%"
          f" ROI@-110={roi_pct:+.2f}% units={roi_units:+.2f}")
    print(f"    wins / losses / pushes: {wins} / {losses} / {pushes}")
    print(f"    MAE_actual={mae_a:.4f} MAE_line={mae_l:.4f}")
    print(f"\n  Edge-magnitude buckets:")
    for bt in bucket_thresholds:
        b = buckets[bt]
        bn = b["n_bets"]; bw = b["wins"]
        bh = (bw / bn) if bn else 0.0
        br_units = bw * profit_per_win - (bn - bw) * 1.0
        br_pct = (br_units / bn * 100.0) if bn else 0.0
        print(f"    |edge| > {bt:.2f}: n_bets={bn:4d} wins={bw:4d} hit={bh*100:5.2f}% ROI={br_pct:+.2f}%")

    return {
        "n_pred": n_pred,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": hit_rate,
        "roi_pct": roi_pct,
        "roi_units": roi_units,
        "mae_actual": mae_a,
        "mae_line": mae_l,
        "skip_reasons": dict(skip_reasons),
        "buckets": buckets,
        "preview": preview_rows,
        "meta": meta,
        "elapsed_sec": elapsed,
    }


def _verdict(hit_rate: float, n_bets: int) -> str:
    if n_bets < 30:
        return "INCONCLUSIVE — fewer than 30 bets, can't distinguish from noise"
    if hit_rate >= 0.55:
        return "VALIDATED — leak was small, edge is real"
    if hit_rate >= 0.52:
        return "PARTIAL — some leak inflation, marginal edge"
    return "COLLAPSED — most of iter-4 BLK ROI was leakage"


def save_report(result: dict) -> None:
    iter4_hit = 0.678
    iter4_roi = 29.4
    iter4_bets = 59
    delta_hit_pp = (result["hit_rate"] - iter4_hit) * 100
    delta_roi_pp = result["roi_pct"] - iter4_roi
    verdict = _verdict(result["hit_rate"], result["n_bets"])

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    L: List[str] = []
    L.append("# BLK OOS Backtest — iter-6\n")
    L.append("Honest out-of-sample BLK closing-line backtest vs the 2024 NBA playoffs,")
    L.append("using a q50 artifact trained STRICTLY on rows before 2024-04-21.")
    L.append("")
    L.append("## Training metadata")
    m = result.get("meta") or {}
    L.append(f"- cutoff_date: `{m.get('cutoff_date')}`")
    L.append(f"- n_train: {m.get('n_train')}")
    L.append(f"- n_val: {m.get('n_val')}")
    L.append(f"- val_pinball@0.5: {m.get('val_pinball_q50'):.4f}" if m.get('val_pinball_q50') is not None else "- val_pinball@0.5: n/a")
    L.append(f"- val_MAE (raw): {m.get('val_mae'):.4f}" if m.get('val_mae') is not None else "- val_MAE: n/a")
    L.append(f"- training_timestamp: `{m.get('training_timestamp')}`")
    L.append("")
    L.append("## OOS backtest results")
    L.append(f"- n_pred: **{result['n_pred']}**")
    L.append(f"- n_bets: **{result['n_bets']}** (threshold |edge| > {THRESHOLD})")
    L.append(f"- wins / losses / pushes: {result['wins']} / {result['losses']} / {result['pushes']}")
    L.append(f"- hit_rate: **{result['hit_rate']*100:.2f}%**")
    L.append(f"- ROI @ -110: **{result['roi_pct']:+.2f}%** ({result['roi_units']:+.2f} units)")
    L.append(f"- MAE_actual: {result['mae_actual']:.4f}")
    L.append(f"- MAE_line: {result['mae_line']:.4f}")
    L.append("")
    L.append("## Comparison vs iter-4 (in-sample)")
    L.append("| metric | iter-4 (in-sample) | iter-6 (OOS) | delta |")
    L.append("|--------|------------------:|-------------:|------:|")
    L.append(f"| hit_rate | {iter4_hit*100:.2f}% | {result['hit_rate']*100:.2f}% | {delta_hit_pp:+.2f}pp |")
    L.append(f"| ROI @ -110 | {iter4_roi:+.2f}% | {result['roi_pct']:+.2f}% | {delta_roi_pp:+.2f}pp |")
    L.append(f"| n_bets | {iter4_bets} | {result['n_bets']} | {result['n_bets'] - iter4_bets:+d} |")
    L.append("")
    L.append("## Edge-magnitude buckets")
    L.append("| |edge| > | n_bets | wins | hit% | ROI |")
    L.append("|--------:|-------:|-----:|-----:|----:|")
    profit_per_win = _odds_to_decimal_profit(-110)
    for bt, b in result["buckets"].items():
        bn = b["n_bets"]; bw = b["wins"]
        bh = (bw / bn) if bn else 0.0
        br_units = bw * profit_per_win - (bn - bw) * 1.0
        br_pct = (br_units / bn * 100.0) if bn else 0.0
        L.append(f"| {bt:.2f} | {bn} | {bw} | {bh*100:.2f}% | {br_pct:+.2f}% |")
    L.append("")
    L.append("## Verdict")
    L.append(f"**{verdict}**")
    L.append("")
    L.append("Decision rule:")
    L.append("- hit_rate >= 55% on >= 30 bets → VALIDATED — leak was small, edge is real")
    L.append("- 52% <= hit_rate < 55% on >= 30 bets → PARTIAL — some leak inflation, marginal edge")
    L.append("- hit_rate < 52% → COLLAPSED — most of iter-4 BLK ROI was leakage")
    L.append("")
    L.append("## Skip reasons")
    for k, v in sorted(result["skip_reasons"].items(), key=lambda kv: -kv[1]):
        L.append(f"- `{k}`: {v}")
    L.append("")
    L.append("## Preview (first 10)")
    L.append("| player | date | pred | line | actual |")
    L.append("|--------|------|-----:|-----:|------:|")
    for (p_, d_, pr_, ln_, ac_) in result["preview"]:
        L.append(f"| {p_} | {d_} | {pr_:.2f} | {ln_:.2f} | {ac_:.2f} |")
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  Report saved -> {REPORT_PATH}")
    print(f"\n  VERDICT: {verdict}")


def main() -> None:
    result = run()
    save_report(result)


if __name__ == "__main__":
    main()
