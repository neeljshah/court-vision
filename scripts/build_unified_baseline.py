"""build_unified_baseline.py — Iter-15 unified 4-slice baseline seeder.

Combines 4 OOS eval slices, runs per-stat backtests with the new Iter-15
per-stat edge thresholds (STL@0.10, BLK@0.40), and writes
data/cache/holdout_baseline.json with the unified per-stat metrics under
__global__ plus a __source__ metadata key.

Slices:
  1. data/external/historical_lines/playoffs_2024_canonical.csv
  2. data/external/historical_lines/regular_season_2024_25_oddsapi.csv
  3. data/external/historical_lines/regular_season_2025_26_oddsapi.csv
  4. data/external/historical_lines/playoffs_2025_26_oddsapi.csv

Usage:
    python scripts/build_unified_baseline.py [--dry-run]

Exit 0 on success. Idempotent — re-running overwrites with fresh numbers.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

BASELINE_PATH = ROOT / "data" / "cache" / "holdout_baseline.json"
LINES_DIR = ROOT / "data" / "external" / "historical_lines"
GAMELOG_DIR = str(ROOT / "data" / "nba")

SLICE_FILES = [
    LINES_DIR / "playoffs_2024_canonical.csv",
    LINES_DIR / "regular_season_2024_25_oddsapi.csv",
    LINES_DIR / "regular_season_2025_26_oddsapi.csv",
    LINES_DIR / "playoffs_2025_26_oddsapi.csv",
]
SLICE_LABELS = [
    "playoffs_2024",
    "regular_season_2024_25",
    "regular_season_2025_26",
    "playoffs_2025_26",
]

ALL_STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]
OOS_DIR = str(ROOT / "data" / "models" / "oos_pre_playoffs")
# Stats handled by backtest_qstat_oos.py (q50 path)
QSTAT_STATS = {"reb", "fg3m", "stl", "tov"}
# BLK has its own script; pts/ast have their own scripts too
QSTAT_LGB_STATS = {"reb"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _merge_csvs(paths: list[Path]) -> list[dict]:
    """Return all rows across all slice CSVs as a flat list."""
    all_rows: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"  [WARN] slice file missing, skipping: {p}", flush=True)
            continue
        with open(str(p), encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                all_rows.append(r)
    return all_rows


def _write_merged_csv(rows: list[dict], path: str) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _run_stat_subprocess(stat: str, merged_csv: str) -> dict[str, Any]:
    """Run the appropriate backtest script for *stat* with CSV override."""
    env = os.environ.copy()
    env["NBA_INJURY_WIRE_DISABLE"] = "1"
    env["HOLDOUT_STAT"] = stat
    env["NBA_BACKTEST_CSV_OVERRIDE"] = merged_csv

    if stat == "pts":
        script = ROOT / "scripts" / "backtest_pts_oos.py"
    elif stat == "ast":
        script = ROOT / "scripts" / "backtest_ast_oos.py"
    elif stat == "blk":
        script = ROOT / "scripts" / "backtest_blk_oos.py"
    else:
        script = ROOT / "scripts" / "backtest_qstat_oos.py"

    cmd = [sys.executable, str(script)]
    if stat in QSTAT_STATS:
        cmd += ["--stat", stat]

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), env=env,
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        return {"stat": stat, "ok": False, "reason": "timeout"}

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    elapsed = time.time() - t0

    # Parse from stdout
    import re
    roi_m = re.search(r"ROI(?:@-?\d+)?=([+-]?\d+\.\d+)%", out)
    hit_m = re.search(r"hit(?:_rate)?=([+-]?\d+\.\d+)%", out)
    nb_m  = re.search(r"n_bets=(\d+)", out)
    np_m  = re.search(r"n_pred=(\d+)", out)
    mae_m = re.search(r"MAE_actual=([+-]?\d+\.\d+)", out)
    u_m   = re.search(r"units=([+-]?\d+\.\d+)", out)

    if not (roi_m and hit_m and nb_m):
        tail = "\n".join(out.splitlines()[-30:])
        print(f"  [WARN] parse failed for {stat}:\n{tail}", flush=True)
        return {"stat": stat, "ok": False, "reason": "parse_failed",
                "exit": proc.returncode, "elapsed_s": elapsed}

    return {
        "stat": stat, "ok": True,
        "roi_pct": float(roi_m.group(1)),
        "hit_rate": float(hit_m.group(1)),
        "n_bets": int(nb_m.group(1)),
        "n_pred": int(np_m.group(1)) if np_m else None,
        "mae_actual": float(mae_m.group(1)) if mae_m else None,
        "roi_units": float(u_m.group(1)) if u_m else None,
        "elapsed_s": elapsed,
    }


def _run_stat_inline_qstat(stat: str, rows: list[dict]) -> dict[str, Any]:
    """Inline OOS backtest for q50 stats (reb, fg3m, stl, tov)."""
    import numpy as np
    from src.prediction.bet_thresholds import edge_threshold_for
    from src.prediction.prop_pergame import feature_columns_for
    from src.prediction.prop_quantiles import _inverse
    from scripts.backtest_closing_lines_2024_playoffs import (
        _build_asof_row, _resolve_player_id, _season_for_date,
        _classify_result, _recommend, _odds_to_decimal_profit,
    )

    threshold = edge_threshold_for(stat)
    stat_rows = [r for r in rows if r.get("stat", "").lower() == stat]
    print(f"  {stat.upper()}: {len(stat_rows)} rows, threshold={threshold}", flush=True)
    if not stat_rows:
        return {"stat": stat, "ok": False, "reason": "no_rows"}

    # Load model
    try:
        if stat in QSTAT_LGB_STATS:
            import joblib
            model_path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
            if not os.path.exists(model_path):
                return {"stat": stat, "ok": False, "reason": f"model_missing:{model_path}"}
            model = joblib.load(model_path)
        else:
            import xgboost as xgb
            model_path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
            if not os.path.exists(model_path):
                return {"stat": stat, "ok": False, "reason": f"model_missing:{model_path}"}
            model = xgb.XGBRegressor()
            model.load_model(model_path)
    except Exception as e:
        return {"stat": stat, "ok": False, "reason": f"load_err:{e}"}

    cols = feature_columns_for(stat, OOS_DIR)
    name2pid = {nm: _resolve_player_id(nm)
                for nm in sorted({r["player"] for r in stat_rows})}
    row_cache: dict = {}
    skip: dict[str, int] = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: list[float] = []

    t0 = time.time()
    for r in stat_rows:
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
            X = [[float(feat.get(c, 0.0) or 0.0) for c in cols]]
            pred_t = float(model.predict(X)[0])
            pred = float(_inverse(stat, [pred_t])[0])
            pred = max(0.0, pred)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, threshold)
        n_pred += 1
        mae_a.append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    elapsed = time.time() - t0
    profit = _odds_to_decimal_profit(-110)
    roi_units = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0
    mae_avg = sum(mae_a) / len(mae_a) if mae_a else 0.0

    print(f"    n_pred={n_pred} n_bets={n_bets} hit={hit*100:.2f}% "
          f"ROI@-110={roi_pct:+.2f}% units={roi_units:+.2f}", flush=True)
    return {
        "stat": stat, "ok": True,
        "roi_pct": round(roi_pct, 4),
        "hit_rate": round(hit * 100.0, 4),
        "n_bets": n_bets,
        "n_pred": n_pred,
        "mae_actual": round(mae_avg, 4),
        "roi_units": round(roi_units, 4),
        "elapsed_s": elapsed,
    }


def _run_stat_inline_blk(rows: list[dict]) -> dict[str, Any]:
    """Inline OOS backtest for BLK q50 (uses blk-specific XGB artifact)."""
    import numpy as np
    import xgboost as xgb
    from src.prediction.bet_thresholds import edge_threshold_for
    from src.prediction.prop_pergame import feature_columns_for
    from src.prediction.prop_quantiles import _inverse
    from scripts.backtest_closing_lines_2024_playoffs import (
        _build_asof_row, _resolve_player_id, _season_for_date,
        _classify_result, _recommend, _odds_to_decimal_profit,
    )

    stat = "blk"
    threshold = edge_threshold_for(stat)
    stat_rows = [r for r in rows if r.get("stat", "").lower() == stat]
    print(f"  BLK: {len(stat_rows)} rows, threshold={threshold}", flush=True)
    if not stat_rows:
        return {"stat": stat, "ok": False, "reason": "no_rows"}

    model_path = os.path.join(OOS_DIR, "quantile_pergame_blk_q50.json")
    if not os.path.exists(model_path):
        return {"stat": stat, "ok": False, "reason": f"model_missing:{model_path}"}
    model = xgb.XGBRegressor()
    model.load_model(model_path)

    cols = feature_columns_for(stat, OOS_DIR)
    name2pid = {nm: _resolve_player_id(nm)
                for nm in sorted({r["player"] for r in stat_rows})}
    row_cache: dict = {}
    skip: dict[str, int] = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: list[float] = []

    t0 = time.time()
    for r in stat_rows:
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
            X = [[float(feat.get(c, 0.0) or 0.0) for c in cols]]
            pred_t = float(model.predict(X)[0])
            pred = float(_inverse(stat, [pred_t])[0])
            pred = max(0.0, pred)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, threshold)
        n_pred += 1
        mae_a.append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    elapsed = time.time() - t0
    profit = _odds_to_decimal_profit(-110)
    roi_units = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0
    mae_avg = sum(mae_a) / len(mae_a) if mae_a else 0.0

    print(f"    n_pred={n_pred} n_bets={n_bets} hit={hit*100:.2f}% "
          f"ROI@-110={roi_pct:+.2f}% units={roi_units:+.2f}", flush=True)
    return {
        "stat": stat, "ok": True,
        "roi_pct": round(roi_pct, 4),
        "hit_rate": round(hit * 100.0, 4),
        "n_bets": n_bets,
        "n_pred": n_pred,
        "mae_actual": round(mae_avg, 4),
        "roi_units": round(roi_units, 4),
        "elapsed_s": elapsed,
    }


def _run_blend_stat(stat: str, rows: list[dict]) -> dict[str, Any]:
    """Inline OOS backtest for blend stats (pts, ast) via subprocess with merged CSV."""
    import re, tempfile as tf
    from src.prediction.bet_thresholds import edge_threshold_for

    threshold = edge_threshold_for(stat)
    stat_rows = [r for r in rows if r.get("stat", "").lower() == stat]
    print(f"  {stat.upper()}: {len(stat_rows)} rows (blend path), threshold={threshold}",
          flush=True)

    # Write a per-stat temp CSV so the backtest script can find it
    with tf.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                               encoding="utf-8", newline="") as fh:
        tmp_path = fh.name
        if stat_rows:
            fieldnames = list(stat_rows[0].keys())
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in stat_rows:
                w.writerow(r)

    env = os.environ.copy()
    env["NBA_INJURY_WIRE_DISABLE"] = "1"
    env["NBA_BACKTEST_CSV_OVERRIDE"] = tmp_path

    script = ROOT / "scripts" / f"backtest_{stat}_oos.py"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        os.unlink(tmp_path)
        return {"stat": stat, "ok": False, "reason": "timeout"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    elapsed = time.time() - t0

    roi_m = re.search(r"ROI(?:@-?\d+)?=([+-]?\d+\.\d+)%", out)
    hit_m = re.search(r"hit(?:_rate)?=([+-]?\d+\.\d+)%", out)
    nb_m  = re.search(r"n_bets=(\d+)", out)
    np_m  = re.search(r"n_pred=(\d+)", out)
    mae_m = re.search(r"MAE_actual=([+-]?\d+\.\d+)", out)
    u_m   = re.search(r"units=([+-]?\d+\.\d+)", out)

    if not (roi_m and hit_m and nb_m):
        tail = "\n".join(out.splitlines()[-30:])
        print(f"  [WARN] {stat.upper()} subprocess parse failed:\n{tail}", flush=True)
        return {"stat": stat, "ok": False, "reason": "parse_failed",
                "exit": proc.returncode, "elapsed_s": elapsed}

    return {
        "stat": stat, "ok": True,
        "roi_pct": round(float(roi_m.group(1)), 4),
        "hit_rate": round(float(hit_m.group(1)), 4),
        "n_bets": int(nb_m.group(1)),
        "n_pred": int(np_m.group(1)) if np_m else None,
        "mae_actual": round(float(mae_m.group(1)), 4) if mae_m else None,
        "roi_units": round(float(u_m.group(1)), 4) if u_m else None,
        "elapsed_s": elapsed,
    }


def _print_table(results: list[dict[str, Any]]) -> None:
    print("\n  stat | n_bets | roi_pct | hit_rate", flush=True)
    print("  -----|-------:|--------:|--------:", flush=True)
    total_bets = 0
    weighted_roi = 0.0
    for r in results:
        s = r["stat"]
        if r.get("ok"):
            nb = r["n_bets"]
            roi = r["roi_pct"]
            hit = r["hit_rate"]
            print(f"  {s:<4} | {nb:>6} | {roi:>+7.2f}% | {hit:>7.2f}%", flush=True)
            total_bets += nb
            weighted_roi += roi * nb
        else:
            print(f"  {s:<4} | FAILED ({r.get('reason','?')})", flush=True)
    if total_bets:
        pool_roi = weighted_roi / total_bets
        print(f"\n  POOL: {total_bets} bets  weighted ROI={pool_roi:+.2f}%", flush=True)


def _save_baseline(results: list[dict[str, Any]], dry_run: bool = False) -> None:
    per_stat: dict[str, Any] = {}
    for r in results:
        if r.get("ok"):
            per_stat[r["stat"]] = {
                "roi_pct": r["roi_pct"],
                "hit_rate": r["hit_rate"],
                "mae_actual": r.get("mae_actual"),
                "roi_units": r.get("roi_units"),
                "n_bets": r["n_bets"],
            }

    source = {
        "__source__": {
            "slices": SLICE_LABELS,
            "files": [str(p) for p in SLICE_FILES],
            "generated_at": _now_iso(),
            "iter": "iter15",
            "thresholds": {"stl": 0.10, "blk": 0.40, "others": 0.5},
        }
    }

    if dry_run:
        print("\n  [dry-run] would write:", flush=True)
        print(json.dumps({"__global__": per_stat, **source}, indent=2)[:2000], flush=True)
        return

    existing: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        try:
            existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    existing["__global__"] = per_stat
    existing["__updated_at__"] = _now_iso()
    existing.update(source)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\n  Baseline written -> {BASELINE_PATH}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", default=",".join(ALL_STATS),
                    help="Comma-separated stat list to run (default: all)")
    args = ap.parse_args()

    stats = [s.strip().lower() for s in args.stats.split(",")]
    print(f"\nbuild_unified_baseline — iter-15", flush=True)
    print(f"  stats: {stats}", flush=True)
    print(f"  slices:", flush=True)
    for lbl, p in zip(SLICE_LABELS, SLICE_FILES):
        rows_n = sum(1 for _ in csv.DictReader(open(str(p), encoding="utf-8"))) if p.exists() else 0
        print(f"    {lbl}: {rows_n} rows", flush=True)

    # Merge all CSVs
    print("\n  Merging CSVs...", flush=True)
    all_rows = _merge_csvs(SLICE_FILES)
    print(f"  Total rows: {len(all_rows)}", flush=True)

    results: list[dict[str, Any]] = []
    for stat in stats:
        print(f"\n--- {stat.upper()} ---", flush=True)
        if stat in QSTAT_STATS:
            r = _run_stat_inline_qstat(stat, all_rows)
        elif stat == "blk":
            r = _run_stat_inline_blk(all_rows)
        elif stat in ("pts", "ast"):
            # pts/ast use blend models — run via subprocess with CSV override
            # (the backtest scripts check NBA_BACKTEST_CSV_OVERRIDE if present)
            r = _run_blend_stat(stat, all_rows)
        else:
            print(f"  [SKIP] no handler for stat={stat}", flush=True)
            r = {"stat": stat, "ok": False, "reason": "no_handler"}
        results.append(r)

    print("\n\n===== UNIFIED BASELINE =====", flush=True)
    _print_table(results)
    _save_baseline(results, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
