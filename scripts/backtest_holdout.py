"""backtest_holdout.py — unified Wave-3 ship/revert gate for the loop.

Invocation:
    python scripts/backtest_holdout.py \
        --feature-source iter5_static_postfix \
        --season 2024-25 \
        --stats pts,ast,reb,fg3m,stl,blk,tov \
        [--update-baseline-if-improved] \
        [--per-stat-decisions-only]

What it does:
  1. Runs each per-stat OOS backtest (scripts/backtest_<stat>_oos.py) in a
     subprocess. The existing scripts replay closing lines from
     data/external/historical_lines/*canonical*.csv.
  2. Parses the printed ROI%, hit_rate, MAE, and n_bets from each run.
  3. Compares each stat against its OWN baseline row in holdout_baseline.json.
     Per-stat gate: delta_roi > 0.5 AND delta_mae < 0 AND delta_units >= -0.5
     New stats (not in baseline): decision = BASELINE_SET.
  4. Aggregate decision:
       SHIP  — any stat ships AND no stat has delta_roi < -2.0
       REVERT — 2+ stats have delta_roi < -1.0
       INCONCLUSIVE — otherwise
  5. Writes report to data/cache/holdout_metrics/{feature_source}_{ts}.json
     and prints JSON summary on stdout.
     Exit 0=SHIP, 1=REVERT, 2=INCONCLUSIVE/BASELINE_SET.

Baseline file format (per-stat nested):
  {"__global__": {"pts": {roi_pct, mae_actual, n_bets, ...},
                   "ast": {...}, ...},
   "__updated_at__": "..."}

Old single-aggregate format is auto-migrated on first read.
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

SOURCE_STATS: dict[str, list[str]] = {
    "defender_matchup": ["pts", "fg3m", "blk"],
    "player_profile": ["pts", "reb", "ast", "fg3m"],
    "quarter_features": ["pts", "ast"],
    "bbref_advanced": ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"],
    "contracts": ["pts", "reb", "ast"],
}

_ROI_RX = re.compile(r"ROI(?:@-?\d+)?=([+-]?\d+\.\d+)%")
_HIT_RX = re.compile(r"hit(?:_rate)?=([+-]?\d+\.\d+)%")
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
        cmd = [sys.executable, str(script_path)]
        if script_path.name == "backtest_qstat_oos.py":
            cmd.extend(["--stat", stat])
        proc = subprocess.run(
            cmd,
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
    """Build legacy aggregate blob (kept for report backwards-compat)."""
    ok = [r for r in stat_results if r.get("ok")]
    if not ok:
        return {"agg_ok": False, "n_stats": 0}
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


# ---------------------------------------------------------------------------
# Baseline I/O — per-stat nested format with old-format auto-migration
# ---------------------------------------------------------------------------

def _is_old_format(global_blob: Any) -> bool:
    """Old format: __global__ is a flat aggregate dict (has agg_ok key)."""
    return isinstance(global_blob, dict) and "agg_ok" in global_blob


def _migrate_old_baseline(old_global: dict[str, Any]) -> dict[str, Any]:
    """
    Convert old single-aggregate baseline into per-stat format.
    Old format only had PTS data (853 bets). We label it as pts only.
    """
    migrated: dict[str, Any] = {}
    # Best-effort: old global was PTS-seeded, map its metrics to pts
    if old_global.get("agg_ok") and old_global.get("n_stats", 0) >= 1:
        migrated["pts"] = {
            "roi_pct": old_global.get("roi_pct_weighted", 0.0),
            "hit_rate": old_global.get("hit_rate_weighted", 0.0),
            "mae_actual": old_global.get("mae_actual_avg", 0.0),
            "roi_units": old_global.get("roi_units_total", 0.0),
            "n_bets": old_global.get("n_bets_total", 0),
            "migrated_from_aggregate": True,
        }
    return migrated


def _load_baseline() -> dict[str, Any]:
    """Return per-stat baseline dict; auto-migrates old format transparently."""
    if not BASELINE_PATH.exists():
        return {}
    try:
        raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    global_blob = raw.get("__global__", {})
    if _is_old_format(global_blob):
        # Migrate in-place and persist
        migrated = _migrate_old_baseline(global_blob)
        print("[holdout] WARNING: migrating old aggregate baseline → per-stat format", flush=True)
        _save_baseline(migrated)
        return migrated
    return global_blob  # already per-stat


def _save_baseline(per_stat: dict[str, Any]) -> None:
    """Persist per-stat baseline dict."""
    existing: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        try:
            existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing["__global__"] = per_stat
    existing["__updated_at__"] = _now_iso()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-stat decision logic
# ---------------------------------------------------------------------------

_PER_STAT_GATE = "delta_roi > 0.5 AND delta_mae < 0 AND delta_units >= -0.5"


def _decide_stat(
    result: dict[str, Any],
    stat_baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return decision dict for a single stat."""
    stat = result["stat"]
    if not result.get("ok"):
        return {"stat": stat, "decision": "INCONCLUSIVE", "reason": result.get("reason", "run_failed")}
    if not stat_baseline:
        return {
            "stat": stat, "decision": "BASELINE_SET",
            "reason": "no_prior_baseline — recording as baseline",
            "delta_roi": None, "delta_mae": None, "delta_units": None,
        }
    d_roi = result["roi_pct"] - stat_baseline.get("roi_pct", 0.0)
    d_mae = (
        (result["mae_actual"] or 0.0) - stat_baseline.get("mae_actual", 0.0)
        if result.get("mae_actual") is not None else None
    )
    d_units = (
        (result["roi_units"] or 0.0) - stat_baseline.get("roi_units", 0.0)
        if result.get("roi_units") is not None else None
    )
    mae_ok = (d_mae is not None and d_mae < 0.0)
    units_ok = (d_units is None or d_units >= -0.5)
    ship = (d_roi > 0.5) and mae_ok and units_ok
    return {
        "stat": stat,
        "decision": "SHIP" if ship else "REVERT",
        "delta_roi": round(d_roi, 4),
        "delta_mae": round(d_mae, 4) if d_mae is not None else None,
        "delta_units": round(d_units, 4) if d_units is not None else None,
        "gate": _PER_STAT_GATE,
    }


def _decide(
    stat_results: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """
    Return per-stat decisions and aggregate decision.

    Returns:
        {
          "per_stat": {"pts": {decision, delta_roi, ...}, ...},
          "aggregate": {decision, n_ship, n_revert, n_inconclusive, n_baseline_set}
        }
    """
    per_stat: dict[str, Any] = {}
    for r in stat_results:
        stat = r["stat"]
        stat_bl = baseline.get(stat) if baseline else None
        per_stat[stat] = _decide_stat(r, stat_bl)

    decisions = [v["decision"] for v in per_stat.values()]
    n_ship = decisions.count("SHIP")
    n_revert = decisions.count("REVERT")
    n_inc = decisions.count("INCONCLUSIVE")
    n_baseline = decisions.count("BASELINE_SET")

    # Aggregate logic
    revert_bad = sum(
        1 for v in per_stat.values()
        if v.get("delta_roi") is not None and v["delta_roi"] < -1.0
    )
    any_hard_revert = any(
        v.get("delta_roi") is not None and v["delta_roi"] < -2.0
        for v in per_stat.values()
    )

    if n_baseline == len(decisions):
        agg_decision = "BASELINE_SET"
    elif n_ship > 0 and not any_hard_revert:
        agg_decision = "SHIP"
    elif revert_bad >= 2:
        agg_decision = "REVERT"
    else:
        agg_decision = "INCONCLUSIVE"

    return {
        "per_stat": per_stat,
        "aggregate": {
            "decision": agg_decision,
            "n_ship": n_ship,
            "n_revert": n_revert,
            "n_inconclusive": n_inc,
            "n_baseline_set": n_baseline,
        },
    }


def _update_baseline_per_stat(
    stat_results: list[dict[str, Any]],
    per_stat_decisions: dict[str, Any],
    existing_baseline: dict[str, Any],
    shipped_only: bool = True,
) -> dict[str, Any]:
    """
    Update per-stat baseline entries.
    If shipped_only=True, only update stats whose individual decision == SHIP or BASELINE_SET.
    """
    updated = dict(existing_baseline)
    for r in stat_results:
        stat = r["stat"]
        dec = per_stat_decisions.get(stat, {}).get("decision", "INCONCLUSIVE")
        if shipped_only and dec not in ("SHIP", "BASELINE_SET"):
            continue
        if not r.get("ok"):
            continue
        updated[stat] = {
            "roi_pct": r["roi_pct"],
            "hit_rate": r["hit_rate"],
            "mae_actual": r.get("mae_actual"),
            "roi_units": r.get("roi_units"),
            "n_bets": r["n_bets"],
        }
    return updated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-source", required=True)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--against", default="historical_lines")
    parser.add_argument("--metric", default="roi_vs_close")
    parser.add_argument("--stats", default=None,
                        help="comma-separated stat keys; defaults from SOURCE_STATS map")
    parser.add_argument("--update-baseline-if-improved", action="store_true",
                        help="update per-stat baseline only for individually-shipped stats")
    parser.add_argument("--seed-baseline", action="store_true",
                        help="record all current stats as baseline (only used once)")
    parser.add_argument("--timeout-per-stat-s", type=int, default=900)
    parser.add_argument("--per-stat-decisions-only", action="store_true",
                        help="print per-stat decision table and exit; no aggregate ship/revert")
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

    baseline = _load_baseline()
    decision = _decide(stat_results, baseline)
    per_stat = decision["per_stat"]
    agg = decision["aggregate"]

    # --per-stat-decisions-only: print table and exit
    if args.per_stat_decisions_only:
        print(json.dumps({"per_stat": per_stat}, indent=2))
        return 2

    # Aggregate stats for report backwards-compat
    current_agg = _aggregate(stat_results)

    blob = {
        "feature_source": args.feature_source,
        "season": args.season,
        "against": args.against,
        "metric": args.metric,
        "stats_run": stats,
        "timestamp": _now_iso(),
        "current": current_agg,
        "baseline": baseline,
        "decision": decision,
        "stat_results": stat_results,
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = METRICS_DIR / f"{args.feature_source}_{ts}.json"
    report_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    baseline_action: str | None = None
    if args.seed_baseline:
        updated_bl = _update_baseline_per_stat(stat_results, per_stat, baseline, shipped_only=False)
        _save_baseline(updated_bl)
        baseline_action = "seeded_all_stats"
    elif args.update_baseline_if_improved:
        if agg["decision"] in ("SHIP", "BASELINE_SET") or agg["n_ship"] > 0:
            updated_bl = _update_baseline_per_stat(stat_results, per_stat, baseline, shipped_only=True)
            _save_baseline(updated_bl)
            shipped_stats = [s for s, v in per_stat.items() if v["decision"] in ("SHIP", "BASELINE_SET")]
            baseline_action = f"updated_for_stats:{','.join(shipped_stats)}"

    print(json.dumps({
        "feature_source": args.feature_source,
        "aggregate_decision": agg["decision"],
        "n_ship": agg["n_ship"],
        "n_revert": agg["n_revert"],
        "n_inconclusive": agg["n_inconclusive"],
        "n_baseline_set": agg["n_baseline_set"],
        "per_stat": {
            s: {
                "decision": v["decision"],
                "delta_roi": v.get("delta_roi"),
                "delta_mae": v.get("delta_mae"),
            }
            for s, v in per_stat.items()
        },
        "baseline_action": baseline_action,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
    }, indent=2))

    code = {"SHIP": 0, "REVERT": 1}.get(agg["decision"], 2)
    return code


if __name__ == "__main__":
    sys.exit(main())
