"""backtest_holdout.py — unified Wave-3 ship/revert gate for the loop.

Invocation:
    python scripts/backtest_holdout.py \
        --feature-source defender_matchup \
        --season 2024-25 \
        --against historical_lines \
        --metric roi_vs_close \
        [--stats pts,reb,ast,fg3m,stl,blk,tov] \
        [--update-baseline-if-improved]

What it does:
  1. Runs each per-stat OOS backtest (scripts/backtest_<stat>_oos.py) in a
     subprocess. The existing scripts replay closing lines from
     data/external/historical_lines/*canonical*.csv.
  2. Parses the printed ROI%, hit_rate, MAE, and n_bets from each run.
  3. Aggregates into a single metrics blob keyed on --feature-source.
  4. Compares to data/cache/holdout_baseline.json. The ship gate is:
        delta_ROI > +0.5  AND  brier improves (mae_actual decreases)
        AND  CLV not worse (roi_units must not drop > 0.5 units)
  5. Writes the per-run report to
        data/cache/holdout_metrics/{feature_source}_{ts}.json
     and prints a single-line JSON summary on stdout. Exit 0 if shipped,
     1 if reverted, 2 if inconclusive.

Designed to be safe to call repeatedly. Never crashes the loop — any
subprocess failure is logged into skip_reasons and the run continues.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
METRICS_DIR = ROOT / "data" / "cache" / "holdout_metrics"
BASELINE_PATH = ROOT / "data" / "cache" / "holdout_baseline.json"

STAT_BACKTEST: dict[str, str] = {
    "pts": "scripts/backtest_pts_oos.py",
    "ast": "scripts/backtest_ast_oos.py",
    "blk": "scripts/backtest_blk_oos.py",
    "reb": "scripts/backtest_qstat_oos.py",
    "fg3m": "scripts/backtest_qstat_oos.py",
    "stl": "scripts/backtest_qstat_oos.py",
    "tov": "scripts/backtest_qstat_oos.py",
}

# Stats affected by each feature source (priority hints — backtest still runs
# only stats the user passes via --stats, but if --stats is omitted we use
# this map to pick a sensible default).
SOURCE_STATS: dict[str, list[str]] = {
    "defender_matchup": ["pts", "fg3m", "blk"],
    "player_profile": ["pts", "reb", "ast", "fg3m"],
    "quarter_features": ["pts", "ast"],
    "bbref_advanced": ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"],
    "contracts": ["pts", "reb", "ast"],
}

_ROI_RX = re.compile(r"ROI@-?\d+=([+-]?\d+\.\d+)%")
_HIT_RX = re.compile(r"hit_rate=([+-]?\d+\.\d+)%")
_NBETS_RX = re.compile(r"n_bets=(\d+)")
_NPRED_RX = re.compile(r"n_pred=(\d+)")
_MAE_RX = re.compile(r"MAE_actual=([+-]?\d+\.\d+)")
_UNITS_RX = re.compile(r"units=([+-]?\d+\.\d+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dirs() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)


def _run_stat(stat: str, season: str, timeout_s: int = 900) -> dict[str, Any]:
    """Run one per-stat backtest and parse stdout. Always returns a dict."""
    script = STAT_BACKTEST.get(stat)
    if not script:
        return {"stat": stat, "ok": False, "reason": "no_script_mapped"}
    script_path = ROOT / script
    if not script_path.exists():
        return {"stat": stat, "ok": False, "reason": f"missing:{script}"}

    env = os.environ.copy()
    env.setdefault("NBA_INJURY_WIRE_DISABLE", "1")
    env["HOLDOUT_STAT"] = stat
    env["HOLDOUT_SEASON"] = season

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"stat": stat, "ok": False, "reason": "timeout", "elapsed_s": timeout_s}

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    roi = _ROI_RX.search(out)
    hit = _HIT_RX.search(out)
    nb = _NBETS_RX.search(out)
    npred = _NPRED_RX.search(out)
    mae = _MAE_RX.search(out)
    units = _UNITS_RX.search(out)
    elapsed = time.time() - t0

    if not (roi and hit and nb):
        tail = "\n".join(out.splitlines()[-20:])
        return {
            "stat": stat, "ok": False, "reason": "parse_failed",
            "exit": proc.returncode, "elapsed_s": elapsed, "tail": tail,
        }

    return {
        "stat": stat, "ok": True,
        "roi_pct": float(roi.group(1)),
        "hit_rate": float(hit.group(1)),
        "n_bets": int(nb.group(1)),
        "n_pred": int(npred.group(1)) if npred else None,
        "mae_actual": float(mae.group(1)) if mae else None,
        "roi_units": float(units.group(1)) if units else None,
        "elapsed_s": elapsed,
        "exit": proc.returncode,
    }


def _aggregate(stat_results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in stat_results if r.get("ok")]
    if not ok:
        return {"agg_ok": False, "n_stats": 0}
    # n_bets-weighted means for ROI / hit_rate. mae_actual averaged plain
    # because each stat has its own scale; we use it as a directional check.
    total_bets = sum(r["n_bets"] for r in ok) or 1
    roi_w = sum(r["roi_pct"] * r["n_bets"] for r in ok) / total_bets
    hit_w = sum(r["hit_rate"] * r["n_bets"] for r in ok) / total_bets
    mae_avg = (
        sum(r["mae_actual"] for r in ok if r["mae_actual"] is not None)
        / max(1, sum(1 for r in ok if r["mae_actual"] is not None))
    )
    units_total = sum(r["roi_units"] for r in ok if r["roi_units"] is not None)
    return {
        "agg_ok": True,
        "n_stats": len(ok),
        "n_bets_total": total_bets,
        "roi_pct_weighted": round(roi_w, 4),
        "hit_rate_weighted": round(hit_w, 4),
        "mae_actual_avg": round(mae_avg, 4),
        "roi_units_total": round(units_total, 4),
    }


def _load_baseline(source: str) -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        return {}
    try:
        all_baselines = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    # Use the "global" baseline as the prior state, NOT a per-source baseline
    # (we are measuring an improvement vs the current production line).
    return all_baselines.get("__global__", {})


def _decide(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if not current.get("agg_ok"):
        return {"decision": "INCONCLUSIVE", "reason": "no_stat_results"}
    if not baseline:
        return {
            "decision": "BASELINE_SET",
            "reason": "no_prior_baseline — recording current as baseline",
            "delta_roi": None, "delta_mae": None, "delta_units": None,
        }
    d_roi = current["roi_pct_weighted"] - baseline.get("roi_pct_weighted", 0.0)
    d_mae = current["mae_actual_avg"] - baseline.get("mae_actual_avg", 0.0)
    d_units = current["roi_units_total"] - baseline.get("roi_units_total", 0.0)
    ship = (d_roi > 0.5) and (d_mae < 0.0) and (d_units >= -0.5)
    return {
        "decision": "SHIP" if ship else "REVERT",
        "delta_roi": round(d_roi, 4),
        "delta_mae": round(d_mae, 4),
        "delta_units": round(d_units, 4),
        "ship_gate": "d_roi > 0.5 AND d_mae < 0 AND d_units >= -0.5",
    }


def _update_baseline(current: dict[str, Any]) -> None:
    all_baselines: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        try:
            all_baselines = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            all_baselines = {}
    all_baselines["__global__"] = current
    all_baselines["__updated_at__"] = _now_iso()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(all_baselines, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-source", required=True)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--against", default="historical_lines")
    parser.add_argument("--metric", default="roi_vs_close")
    parser.add_argument("--stats", default=None,
                        help="comma-separated stat keys; defaults from SOURCE_STATS map")
    parser.add_argument("--update-baseline-if-improved", action="store_true",
                        help="overwrite __global__ baseline with current metrics when SHIP")
    parser.add_argument("--seed-baseline", action="store_true",
                        help="record current metrics as baseline (only used once)")
    parser.add_argument("--timeout-per-stat-s", type=int, default=900)
    args = parser.parse_args()

    _ensure_dirs()

    stats = (
        [s.strip().lower() for s in args.stats.split(",") if s.strip()]
        if args.stats else SOURCE_STATS.get(args.feature_source, ["pts"])
    )

    print(f"[holdout] feature_source={args.feature_source} season={args.season} "
          f"stats={stats} against={args.against}")

    stat_results: list[dict[str, Any]] = []
    for stat in stats:
        print(f"[holdout] running stat={stat} ...", flush=True)
        stat_results.append(_run_stat(stat, args.season, timeout_s=args.timeout_per_stat_s))

    current = _aggregate(stat_results)
    baseline = _load_baseline(args.feature_source)
    decision = _decide(current, baseline)

    blob = {
        "feature_source": args.feature_source,
        "season": args.season,
        "against": args.against,
        "metric": args.metric,
        "stats_run": stats,
        "timestamp": _now_iso(),
        "current": current,
        "baseline": baseline,
        "decision": decision,
        "stat_results": stat_results,
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = METRICS_DIR / f"{args.feature_source}_{ts}.json"
    report_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    if args.seed_baseline and current.get("agg_ok"):
        _update_baseline(current)
        decision["baseline_action"] = "seeded"
    elif args.update_baseline_if_improved and decision.get("decision") == "SHIP":
        _update_baseline(current)
        decision["baseline_action"] = "updated_after_ship"

    print(json.dumps({
        "feature_source": args.feature_source,
        "decision": decision.get("decision"),
        "delta_roi": decision.get("delta_roi"),
        "delta_mae": decision.get("delta_mae"),
        "delta_units": decision.get("delta_units"),
        "report": str(report_path.relative_to(ROOT)),
    }))

    code = {"SHIP": 0, "REVERT": 1}.get(decision.get("decision", ""), 2)
    return code


if __name__ == "__main__":
    sys.exit(main())
