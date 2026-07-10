"""scripts.platformkit.autoloop.execution_cadence_job -- wires the three
TESTED-but-orphaned execution stages (composer -> dryrun -> reconcile) plus
the entry-timing policy refresh into the autoloop cadence. No new math: each
stage is called via its OWN public entrypoint, the way its own test/__main__
already does (test_composer.py, test_dryrun_reconcile.py, test_entry_timing.py).
This module adds only a time-based cadence gate (same elapsed-hours shape as
data_frontier.frontier_probe_job's _CADENCE_HOURS guard).

M13 execution_stages (hourly-ish -- watermarks["M13_execution_stages"]):
  composer.cli.run()        -> writes bestbets_composed.jsonl (+ board)
  executor.dryrun.run_dryrun() -> consumes it, appends dryrun_orders.jsonl
  executor.reconcile.run_reconcile() -> consumes it, writes dryrun_reconcile.json
One gate covers all three -- dryrun/reconcile are only meaningful right after
a fresh compose. Each sub-stage isolated: one stage's failure never blocks
the others or the report.

M14 entry_timing_refresh (weekly -- watermarks["M14_entry_timing_refresh"]):
  entry_timing.cli.run() -> refreshes timing_policy.json, the composer's
  OPERATIONAL entry-hint input (stale policy degrades the hint; the composer
  tolerates a missing/stale file already -- see composer/cli.py:_load_timing_policies).

run_all() is the ONE hook point autoloop_runner.run_cycle() calls (mirrors
maintenance_templates.run_all()'s single-hook-point shape).

Actual real-world cadence is bounded below by the runner's own tick interval
(default 86400s/daily) -- the gate here just stops it firing MORE often than
hourly/weekly if ticks ever run tighter than that.

PENDING-RESTART: the live m38 autoloop daemon does not hot-reload; wiring
this module into autoloop_runner.py takes effect on the daemon's next restart.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_execution_cadence_job.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

_HOURLY_CADENCE_H = 1.0
_WEEKLY_CADENCE_H = 168.0
_WM_STAGES = "M13_execution_stages"
_WM_TIMING = "M14_entry_timing_refresh"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _due(watermarks: Dict[str, Any], key: str, cadence_h: float) -> bool:
    """Elapsed-hours cadence guard (frontier_probe_job's own pattern, reused
    inline since this module owns its two watermark keys). Absent/unparsable
    watermark -> due (never blocks a first run)."""
    last = (watermarks.get(key) or {}).get("last_run_ts")
    if not last:
        return True
    try:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                 ).total_seconds() / 3600.0
        return age_h >= cadence_h
    except ValueError:
        return True


def run_execution_stages(watermarks: Dict[str, Any], *,
                         compose_fn: Optional[Callable[[], Any]] = None,
                         dryrun_fn: Optional[Callable[[], Any]] = None,
                         reconcile_fn: Optional[Callable[[], Any]] = None
                         ) -> Dict[str, Any]:
    """M13: hourly-ish compose -> dryrun -> reconcile chain, each stage
    calling the pinned module's own public entrypoint (no reimplementation)."""
    if not _due(watermarks, _WM_STAGES, _HOURLY_CADENCE_H):
        return {"status": "skipped_cadence"}
    out: Dict[str, Any] = {"status": "ran"}
    try:
        if compose_fn is not None:
            out["composer"] = compose_fn()
        else:
            from scripts.platformkit.execution.composer import cli as CCLI
            out["composer"] = CCLI.run()
    except Exception as exc:  # noqa: BLE001 -- one stage's failure isolated
        out["composer"] = {"status": "error", "error": str(exc)[:200]}
    try:
        if dryrun_fn is not None:
            out["dryrun"] = dryrun_fn()
        else:
            from scripts.platformkit.execution.executor import dryrun as DCLI
            out["dryrun"] = DCLI.run_dryrun()
    except Exception as exc:  # noqa: BLE001
        out["dryrun"] = {"status": "error", "error": str(exc)[:200]}
    try:
        if reconcile_fn is not None:
            out["reconcile"] = reconcile_fn()
        else:
            from scripts.platformkit.execution.executor import reconcile as RCLI
            report = RCLI.run_reconcile()
            RCLI.DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
            RCLI.DEFAULT_OUT.write_text(
                json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
            out["reconcile"] = report
    except Exception as exc:  # noqa: BLE001
        out["reconcile"] = {"status": "error", "error": str(exc)[:200]}
    watermarks[_WM_STAGES] = {"last_run_ts": _now_iso()}
    return out


def run_entry_timing_refresh(watermarks: Dict[str, Any], *,
                             timing_fn: Optional[Callable[[], Any]] = None
                             ) -> Dict[str, Any]:
    """M14: weekly refresh of timing_policy.json (composer's entry-hint
    input; stale policy degrades the hint, the composer already tolerates a
    missing/malformed file so nothing hard-fails on staleness)."""
    if not _due(watermarks, _WM_TIMING, _WEEKLY_CADENCE_H):
        return {"status": "skipped_cadence"}
    if timing_fn is not None:
        result = timing_fn()
    else:
        from scripts.platformkit.execution.entry_timing import cli as ETCLI
        result = ETCLI.run(list(ETCLI.SPORTS), list(ETCLI.GAME_MARKETS), None,
                           ETCLI.REPORT, ETCLI.POLICY)
    watermarks[_WM_TIMING] = {"last_run_ts": _now_iso()}
    return {"status": "ran", "sports_covered": sorted((result or {}).get("policies", {}).keys())
                                              if isinstance(result, dict) else None}


def run_all(watermarks: Dict[str, Any]) -> Dict[str, Any]:
    """The one hook point autoloop_runner.run_cycle() calls (mirrors
    maintenance_templates.run_all()'s single-call-site, per-job-isolated shape)."""
    out: Dict[str, Any] = {}
    try:
        out["execution_stages"] = run_execution_stages(watermarks)
    except Exception as exc:  # noqa: BLE001
        out["execution_stages"] = {"status": "error", "error": str(exc)[:200]}
    try:
        out["entry_timing_refresh"] = run_entry_timing_refresh(watermarks)
    except Exception as exc:  # noqa: BLE001
        out["entry_timing_refresh"] = {"status": "error", "error": str(exc)[:200]}
    return out


__all__ = ["run_execution_stages", "run_entry_timing_refresh", "run_all"]
