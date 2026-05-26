"""daily_workflow.py — R26_S3 single-cron-able orchestrator.

Wraps the evening + morning operator workflow into one script so a single
Task Scheduler / cron entry can drive the whole thing.

Subcommands
-----------
evening    runs at ~7pm ET:
             1. live_rec_tracker --snapshot          (today's recs)
             2. refresh operator dashboard cache     (HTML snapshot)
             3. info alert: "evening recs ready"

morning    runs at ~8am ET:
             1. live_rec_tracker --settle <yesterday>
             2. reconcile_settlements --days 1
             3. refresh operator dashboard cache
             4. info alert: "morning summary" with W/L/ROI/mismatches

all        runs evening + morning back-to-back (catch-up).

CLI
---
    python scripts/daily_workflow.py evening
    python scripts/daily_workflow.py morning
    python scripts/daily_workflow.py all
    python scripts/daily_workflow.py --dry-run evening
    python scripts/daily_workflow.py --summary

Exit code
---------
    0  every step completed without raising
    1  at least one critical step raised — but the workflow still ran
       every remaining step (we never abort on one failure so partial
       progress is preserved).

Side effects
------------
    * Appends one block per run to ``vault/Improvements/daily_workflow.md``
      (auto-created — vault dir is allowed to be missing on a fresh clone).
    * On any step error, fires a `critical` alert via the R21_N3 layered
      alert() — which writes vault/Improvements/alerts.md + a critical
      stack JSON. Discord is silently skipped when DISCORD_WEBHOOK_URL is
      unset.
    * On --dry-run: prints what would run, exits 0, NO side effects.

Hard rules
----------
    * NEVER places real bets — only reads + writes operator artifacts.
    * All subprocess calls go through a list-form argv (no shell=True),
      so the orchestrator is shell-injection-safe by construction.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import date as _date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Default artifact paths (every one is overridable via kwargs for tests/probe).
DEFAULT_LOG_PATH = PROJECT_DIR / "vault" / "Improvements" / "daily_workflow.md"
DEFAULT_DASHBOARD_CACHE = (
    PROJECT_DIR / "data" / "cache" / "operator_dashboard_snapshot.html"
)
DEFAULT_SNAPSHOT_DIR = PROJECT_DIR / "data" / "cache" / "rec_tracker"
DEFAULT_SETTLED_PATH = DEFAULT_SNAPSHOT_DIR / "rec_settled.parquet"
DEFAULT_QB_DIR = PROJECT_DIR / "data" / "cache" / "quarter_box"
# R27_T7 — ledger insurance defaults.
DEFAULT_LEDGER_PATH = PROJECT_DIR / "data" / "pnl_ledger.csv"
DEFAULT_BACKUP_DIR  = PROJECT_DIR / "data" / "backups"
DEFAULT_BACKUP_KEEP = 30
# R27_T3 — feature drift detector defaults.
DEFAULT_DRIFT_CACHE = PROJECT_DIR / "data" / "cache" / "feature_drift_latest.json"
DEFAULT_DRIFT_WARN_THRESHOLD = 5
DEFAULT_DRIFT_CRITICAL_THRESHOLD = 15
# R28_U3 — nightly cleanup defaults.
DEFAULT_CLEANUP_ROOT = PROJECT_DIR
DEFAULT_CLEANUP_WORKTREE_AGE_DAYS = 3

# Stages this orchestrator knows how to run.
STAGES = ("evening", "morning", "all")


# ============================================================================ #
# Tiny helpers                                                                  #
# ============================================================================ #
def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return _date_cls.today().isoformat()


def _yesterday_iso() -> str:
    return (_date_cls.today() - timedelta(days=1)).isoformat()


def _fmt_dur(sec: float) -> str:
    if sec < 1.0:
        return f"{sec*1000:.0f}ms"
    if sec < 60.0:
        return f"{sec:.1f}s"
    return f"{sec/60.0:.1f}m"


def _safe_alert(
    message: str,
    *,
    level: str = "info",
    tag: str = "daily_workflow",
    fields: Optional[List[Dict[str, str]]] = None,
    alert_fn: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Fire an alert via the R21_N3 layered alert() helper.

    Never raises — even when the alert module is missing or its backend
    fails, we want the workflow to keep going. ``alert_fn`` is a test
    seam so tests can intercept fired alerts without touching the real
    vault.
    """
    fn = alert_fn
    if fn is None:
        try:
            from src.alerts.discord_webhook import alert as _alert  # noqa: PLC0415
            fn = _alert
        except Exception:  # noqa: BLE001
            return {"discord_sent": False, "file_written": False,
                    "vault_appended": False, "import_failed": True}
    try:
        return fn(message, level=level, tag=tag, source=tag, fields=fields) or {}
    except Exception as exc:  # noqa: BLE001
        return {"discord_sent": False, "file_written": False,
                "vault_appended": False, "alert_raised": repr(exc)}


# ============================================================================ #
# Log append (vault/Improvements/daily_workflow.md)                              #
# ============================================================================ #
_LOG_HEADER = (
    "# Daily Workflow Runs\n\n"
    "Append-only log of every `scripts/daily_workflow.py` invocation.\n"
    "Each entry is a fenced YAML-ish block parsed by `--summary`.\n\n"
)


def _append_log_entry(
    *,
    stage: str,
    started_at: str,
    duration_sec: float,
    steps: List[Dict[str, Any]],
    n_critical_failures: int,
    log_path: Path = DEFAULT_LOG_PATH,
) -> bool:
    """Append one run record to the vault log. Auto-creates parents.

    Returns True on success, False on any IO error.
    """
    try:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not log_path.exists() or log_path.stat().st_size == 0
        lines: List[str] = []
        lines.append(f"## {started_at}  stage={stage}\n")
        lines.append(f"- duration: {_fmt_dur(duration_sec)}\n")
        lines.append(f"- critical_failures: {n_critical_failures}\n")
        lines.append("- steps:\n")
        for s in steps:
            ok_str = "OK" if s.get("ok") else "FAIL"
            err = s.get("error") or ""
            err_str = f" — {err}" if err else ""
            lines.append(
                f"  - {s.get('name','?')}: {ok_str}"
                f" ({_fmt_dur(float(s.get('duration_sec', 0.0)))})"
                f"{err_str}\n"
            )
        lines.append("\n")
        with open(log_path, "a", encoding="utf-8") as fh:
            if new_file:
                fh.write(_LOG_HEADER)
            fh.writelines(lines)
        return True
    except Exception:  # noqa: BLE001
        return False


# ============================================================================ #
# --summary parse                                                              #
# ============================================================================ #
_HEADER_RE = re.compile(
    r"^##\s*(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)\s+stage=(?P<stage>\w+)"
)
_DURATION_RE = re.compile(r"^- duration:\s*(?P<dur>.+)$")
_FAILS_RE = re.compile(r"^- critical_failures:\s*(?P<n>\d+)$")
_STEP_RE = re.compile(
    r"^\s+-\s+(?P<name>[\w\-]+):\s+(?P<status>OK|FAIL)\s*\((?P<dur>[^)]+)\)"
    r"(?:\s+—\s+(?P<err>.+))?$"
)


def parse_log(log_path: Path = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    """Parse the markdown log into a list of run records."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    records: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = _HEADER_RE.match(line)
                if m:
                    if cur is not None:
                        records.append(cur)
                    cur = {
                        "started_at": m.group("ts"),
                        "stage": m.group("stage"),
                        "duration": "",
                        "critical_failures": 0,
                        "steps": [],
                    }
                    continue
                if cur is None:
                    continue
                m = _DURATION_RE.match(line)
                if m:
                    cur["duration"] = m.group("dur").strip()
                    continue
                m = _FAILS_RE.match(line)
                if m:
                    cur["critical_failures"] = int(m.group("n"))
                    continue
                m = _STEP_RE.match(line)
                if m:
                    cur["steps"].append({
                        "name":     m.group("name"),
                        "ok":       m.group("status") == "OK",
                        "duration": m.group("dur"),
                        "error":    (m.group("err") or "").strip(),
                    })
        if cur is not None:
            records.append(cur)
    except Exception:  # noqa: BLE001
        return records
    return records


def summary(
    log_path: Path = DEFAULT_LOG_PATH,
    days: int = 7,
) -> Dict[str, Any]:
    """Return + print the last `days` of run history."""
    records = parse_log(log_path)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=int(days))

    def _parse_ts(s: str) -> Optional[datetime]:
        try:
            txt = s.rstrip("Z") + "+00:00"
            return datetime.fromisoformat(txt)
        except ValueError:
            return None

    in_window: List[Dict[str, Any]] = []
    for r in records:
        ts = _parse_ts(r.get("started_at", ""))
        if ts is None or ts >= cutoff_dt:
            in_window.append(r)
    out = {
        "ok":             True,
        "log_path":       str(log_path),
        "n_total":        len(records),
        "n_in_window":    len(in_window),
        "days":           int(days),
        "runs":           in_window[-50:],   # cap so JSON stays small
    }
    return out


def _print_summary(s: Dict[str, Any]) -> None:
    print(f"daily_workflow log: {s['log_path']}")
    print(f"  total runs:      {s['n_total']}")
    print(f"  in last {s['days']}d:  {s['n_in_window']}")
    if not s["runs"]:
        print("  (no runs in window)")
        return
    print()
    print(f"{'when':<22} {'stage':<8} {'dur':<8} {'fails':>5}  steps")
    for r in s["runs"]:
        steps_str = ", ".join(
            f"{st['name']}={'OK' if st['ok'] else 'FAIL'}" for st in r["steps"]
        )
        print(
            f"{r['started_at']:<22} {r['stage']:<8} {r['duration']:<8} "
            f"{r['critical_failures']:>5}  {steps_str}"
        )


# ============================================================================ #
# Step runners — each returns (ok: bool, details: dict, error: str|None).      #
# ============================================================================ #
def _step_snapshot_recs(
    *,
    bankroll: float,
    top: int,
    min_edge: float,
    date_str: Optional[str],
    snapshot_dir: Path,
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Capture today's recs via R24_Q4 live_rec_tracker.run_snapshot()."""
    if dry_run:
        return True, {
            "would_call": "live_rec_tracker.run_snapshot",
            "date": date_str or _today_iso(),
            "snapshot_dir": str(snapshot_dir),
            "bankroll": bankroll, "top": top, "min_edge": min_edge,
        }, None
    try:
        from scripts import live_rec_tracker as lrt  # noqa: PLC0415
        out = lrt.run_snapshot(
            bankroll=float(bankroll), top=int(top),
            date_str=date_str, snapshot_dir=str(snapshot_dir),
            min_edge=float(min_edge),
        )
        return True, out, None
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"snapshot raised: {exc!r}"


def _step_refresh_dashboard(
    *,
    cache_path: Path,
    dry_run: bool,
    collect_fn: Optional[Callable[..., str]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Render the R22_O5 operator HTML to disk so the snapshot survives even
    when no aiohttp server is running.

    A test seam (``collect_fn``) is exposed so tests can substitute a stub
    instead of importing pandas + the full dashboard helpers.
    """
    if dry_run:
        return True, {
            "would_call": "operator_dashboard.collect_and_render",
            "cache_path": str(cache_path),
        }, None
    fn = collect_fn
    if fn is None:
        try:
            from scripts.operator_dashboard import collect_and_render as _car  # noqa: PLC0415
            fn = _car
        except Exception as exc:  # noqa: BLE001
            return False, {}, f"dashboard import failed: {exc!r}"
    try:
        html = fn()
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(html)
        os.replace(tmp, cache_path)
        return True, {"cache_path": str(cache_path),
                       "html_bytes": len(html)}, None
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"dashboard render raised: {exc!r}"


def _step_ledger_backup(
    *,
    ledger_path: Path,
    backup_dir: Path,
    keep: int,
    today: Optional[str],
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """R27_T7 — snapshot data/pnl_ledger.csv to data/backups/.

    Runs BEFORE reconcile in the morning stage so a bad reconcile (or any
    other downstream mutation) can never wipe the only copy of the ledger.

    Failure-mode contract:
        * On --dry-run: never touches the disk.
        * On real run: a backup failure returns ok=False so the stage's
          existing critical-alert path fires (with R26_S5 dedup). The
          workflow keeps going — never blocks evening/morning on a
          backup hiccup.
        * Ledger missing on a fresh clone is reported but NOT critical
          (returns ok=True with a 'no_ledger' reason) — fresh dev boxes
          shouldn't alarm.
    """
    if dry_run:
        return True, {
            "would_call":  "ledger_insurance.backup",
            "ledger_path": str(ledger_path),
            "backup_dir":  str(backup_dir),
            "keep":        int(keep),
            "today":       today,
        }, None
    try:
        from scripts.ledger_insurance import backup as _backup  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"ledger_insurance import failed: {exc!r}"
    try:
        res = _backup(
            ledger_path=Path(ledger_path), backup_dir=Path(backup_dir),
            keep=int(keep), today=today,
        )
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"backup raised: {exc!r}"
    if res.get("ok"):
        return True, {
            "date":       res.get("date"),
            "gz_path":    res.get("gz_path"),
            "size_bytes": res.get("size_bytes"),
            "sha256":     (res.get("sha256") or "")[:16],
            "n_rotated":  len(res.get("rotated") or []),
        }, None
    # Distinguish "no ledger yet on a fresh clone" from a real failure.
    reason = res.get("reason", "")
    if "ledger missing" in reason:
        return True, {"skipped": True, "reason": reason}, None
    return False, {"reason": reason}, f"backup not-ok: {reason}"


def _step_settle_recs(
    *,
    date_str: str,
    snapshot_dir: Path,
    settled_path: Path,
    qb_dir: Path,
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Settle yesterday's recs via R24_Q4 live_rec_tracker.settle()."""
    if dry_run:
        return True, {
            "would_call": "live_rec_tracker.settle",
            "date": date_str,
            "snapshot_dir": str(snapshot_dir),
            "settled_path": str(settled_path),
        }, None
    try:
        from scripts import live_rec_tracker as lrt  # noqa: PLC0415
        out = lrt.settle(
            date_str=date_str,
            snapshot_dir=str(snapshot_dir),
            settled_path=str(settled_path),
            qb_dir=str(qb_dir),
        )
        # "snapshot not found" is OK — no recs were captured that day.
        # Only treat unexpected raises as critical.
        reason = out.get("reason", "")
        soft_ok = (
            bool(out.get("ok"))
            or (not bool(out.get("ok")) and "snapshot not found" in reason)
        )
        return soft_ok, out, (
            None if soft_ok else (reason or "settle returned not-ok")
        )
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"settle raised: {exc!r}"


def _step_reconcile(
    *,
    days: int,
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Re-derive settlements vs boxscore via R24_Q8 reconcile_settlements."""
    if dry_run:
        return True, {
            "would_call": "reconcile_settlements.reconcile",
            "days": int(days),
        }, None
    try:
        from scripts.reconcile_settlements import reconcile  # noqa: PLC0415
        rep = reconcile(days=int(days))
        return True, {
            "n_real_settled": int(rep.get("n_real_settled", 0)),
            "n_verified":     int(rep.get("n_verified", 0)),
            "n_matched":      int(rep.get("n_matched", 0)),
            "n_mismatched":   int(rep.get("n_mismatched", 0)),
            "categories":     rep.get("mismatch_categories", {}),
            "all_synthetic":  bool(rep.get("all_synthetic", False)),
        }, None
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"reconcile raised: {exc!r}"


def _step_report_recs(
    *,
    settled_path: Path,
    days: int,
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Compute the W/L/ROI summary to feed into the morning alert."""
    if dry_run:
        return True, {
            "would_call": "live_rec_tracker.report",
            "settled_path": str(settled_path),
            "days": int(days),
        }, None
    try:
        from scripts import live_rec_tracker as lrt  # noqa: PLC0415
        rpt = lrt.report(settled_path=str(settled_path), days=int(days))
        if not rpt.get("ok"):
            return True, rpt, None    # no data is not a critical failure
        return True, rpt, None
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"report raised: {exc!r}"


def _step_feature_drift(
    *,
    cache_path: Path,
    feature_set: str,
    current_days: int,
    warn_threshold: int,
    critical_threshold: int,
    dry_run: bool,
    alert_fn: Optional[Callable[..., Any]] = None,
    run_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """R27_T3 — run drift detector + fire warn/critical when thresholds breach.

    Always writes its JSON report to ``cache_path`` so the operator dashboard's
    ``fetch_feature_drift`` picks it up. Uses the R26_S5 layered alert helper
    (dedup-aware) so daily firing on the same persistent drift won't spam.
    """
    if dry_run:
        return True, {
            "would_call": "feature_drift_detector.run",
            "feature_set": feature_set,
            "current_days": int(current_days),
            "out": str(cache_path),
        }, None
    try:
        if run_fn is None:
            from scripts.feature_drift_detector import run as run_fn  # noqa: PLC0415
        report = run_fn(
            feature_set=feature_set,
            current_days=int(current_days),
        )
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"drift detector raised: {exc!r}"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return False, {"report": report}, f"failed to persist report: {exc!r}"

    n_major = int(report.get("n_drift_major", 0) or 0)
    n_minor = int(report.get("n_drift_minor", 0) or 0)
    n_stable = int(report.get("n_stable", 0) or 0)
    top = list((report.get("features") or [])[:5])
    top_names = [str(r.get("feature", "")) for r in top]
    fields = [
        {"name": "feature_set", "value": str(feature_set)},
        {"name": "n_major",     "value": str(n_major)},
        {"name": "n_minor",     "value": str(n_minor)},
        {"name": "n_stable",    "value": str(n_stable)},
        {"name": "top_drifted", "value": ", ".join(top_names)[:200]},
    ]
    level: Optional[str] = None
    if n_major > int(critical_threshold):
        level = "critical"
    elif n_major > int(warn_threshold):
        level = "warn"
    fire_res: Dict[str, Any] = {"fired": False}
    if level is not None and report.get("status") == "OK":
        msg = (
            f"R27_T3 feature drift {feature_set}: "
            f"n_major={n_major} (threshold warn>{warn_threshold} "
            f"crit>{critical_threshold})"
        )
        fire_res = _safe_alert(msg, level=level, tag="feature_drift",
                               fields=fields, alert_fn=alert_fn)
        fire_res["fired"] = True
        fire_res["level"] = level
    details = {
        "feature_set":         feature_set,
        "status":              report.get("status"),
        "blocked_reason":      report.get("blocked_reason", ""),
        "n_features_analyzed": int(report.get("n_features_analyzed", 0) or 0),
        "n_stable":            n_stable,
        "n_drift_minor":       n_minor,
        "n_drift_major":       n_major,
        "top_drifted":         top_names,
        "cache_path":          str(cache_path),
        "alert":               fire_res,
    }
    return True, details, None


def _step_nightly_cleanup(
    *,
    cleanup_root: Path,
    enable_cleanup: bool,
    worktree_age_days: int,
    dry_run: bool,
    run_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """R28_U3 — nightly disk cleanup. --commit only if `enable_cleanup` and not dry-run."""
    if dry_run:
        return True, {
            "would_call": "nightly_cleanup.run_cleanup",
            "commit":     bool(enable_cleanup),
            "root":       str(cleanup_root),
        }, None
    commit = bool(enable_cleanup)
    try:
        if run_fn is None:
            from scripts.nightly_cleanup import run_cleanup as run_fn  # noqa: PLC0415
        res = run_fn(
            root=Path(cleanup_root), commit=commit,
            worktree_age_days=int(worktree_age_days),
        )
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"nightly_cleanup raised: {exc!r}"
    return True, {
        "commit":            bool(res.get("commit")),
        "total_n_eligible":  int(res.get("total_n_eligible", 0) or 0),
        "total_mb_eligible": float(res.get("total_mb_eligible", 0.0) or 0.0),
        "n_warnings":        len(res.get("warnings", []) or []),
    }, None


def _step_alert(
    *,
    message: str,
    level: str,
    fields: Optional[List[Dict[str, str]]],
    dry_run: bool,
    alert_fn: Optional[Callable[..., Any]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Fire an info/critical alert through the R21_N3 layered helper."""
    if dry_run:
        return True, {
            "would_call": "alert",
            "level": level, "message": message,
            "fields": fields or [],
        }, None
    res = _safe_alert(message, level=level, fields=fields, alert_fn=alert_fn)
    return True, res, None


# ============================================================================ #
# Stage orchestration                                                          #
# ============================================================================ #
def _run_step(
    name: str,
    fn: Callable[..., Tuple[bool, Dict[str, Any], Optional[str]]],
    /,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute one step, time it, never let it abort the workflow."""
    started = time.monotonic()
    try:
        ok, details, err = fn(**kwargs)
    except Exception as exc:  # noqa: BLE001 — last-resort safety net
        traceback.print_exc()
        ok, details, err = False, {}, f"unhandled: {exc!r}"
    duration = time.monotonic() - started
    return {
        "name":         name,
        "ok":           bool(ok),
        "duration_sec": duration,
        "details":      details,
        "error":        err,
    }


def run_evening(
    *,
    bankroll: float = 1000.0,
    top: int = 10,
    min_edge: float = 0.05,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    dashboard_cache: Path = DEFAULT_DASHBOARD_CACHE,
    log_path: Path = DEFAULT_LOG_PATH,
    dry_run: bool = False,
    today: Optional[str] = None,
    alert_fn: Optional[Callable[..., Any]] = None,
    collect_fn: Optional[Callable[..., str]] = None,
) -> Dict[str, Any]:
    """Run the evening workflow. Returns a result dict (always; never raises)."""
    started_at = _iso_now()
    started = time.monotonic()
    steps: List[Dict[str, Any]] = []
    today = today or _today_iso()

    # 1. Snapshot today's recs.
    steps.append(_run_step(
        "snapshot_recs", _step_snapshot_recs,
        bankroll=bankroll, top=top, min_edge=min_edge,
        date_str=today, snapshot_dir=snapshot_dir, dry_run=dry_run,
    ))

    # 2. Refresh operator dashboard cache.
    steps.append(_run_step(
        "refresh_dashboard", _step_refresh_dashboard,
        cache_path=dashboard_cache, dry_run=dry_run, collect_fn=collect_fn,
    ))

    # 3. Fire info alert + a critical alert per failing step.
    snap_step = steps[0]
    snap_details = snap_step.get("details") or {}
    n_recs = snap_details.get("n_recs", 0)
    fields = [
        {"name": "date",    "value": str(today)},
        {"name": "n_recs",  "value": str(n_recs)},
        {"name": "dry_run", "value": str(bool(dry_run))},
    ]
    steps.append(_run_step(
        "alert_evening", _step_alert,
        message=f"R26_S3 evening recs ready (n={n_recs}, date={today})",
        level="info", fields=fields,
        dry_run=dry_run, alert_fn=alert_fn,
    ))

    # Critical alerts for any failed step.
    n_critical_failures = sum(1 for s in steps if not s["ok"])
    if n_critical_failures and not dry_run:
        for s in steps:
            if s["ok"]:
                continue
            _safe_alert(
                f"R26_S3 evening step FAILED: {s['name']} — {s.get('error','')}",
                level="critical",
                fields=[
                    {"name": "step",  "value": s["name"]},
                    {"name": "error", "value": (s.get("error") or "")[:200]},
                ],
                alert_fn=alert_fn,
            )

    duration = time.monotonic() - started
    if not dry_run:
        _append_log_entry(
            stage="evening", started_at=started_at,
            duration_sec=duration, steps=steps,
            n_critical_failures=n_critical_failures, log_path=log_path,
        )
    return {
        "stage":               "evening",
        "started_at":          started_at,
        "duration_sec":        duration,
        "n_critical_failures": n_critical_failures,
        "steps":               steps,
        "dry_run":             bool(dry_run),
    }


def run_morning(
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    settled_path: Path = DEFAULT_SETTLED_PATH,
    qb_dir: Path = DEFAULT_QB_DIR,
    dashboard_cache: Path = DEFAULT_DASHBOARD_CACHE,
    log_path: Path = DEFAULT_LOG_PATH,
    reconcile_days: int = 1,
    report_days: int = 1,
    dry_run: bool = False,
    yesterday: Optional[str] = None,
    alert_fn: Optional[Callable[..., Any]] = None,
    collect_fn: Optional[Callable[..., str]] = None,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    backup_keep: int = DEFAULT_BACKUP_KEEP,
    drift_cache: Path = DEFAULT_DRIFT_CACHE,
    drift_feature_set: str = "m2",
    drift_current_days: int = 14,
    drift_warn_threshold: int = DEFAULT_DRIFT_WARN_THRESHOLD,
    drift_critical_threshold: int = DEFAULT_DRIFT_CRITICAL_THRESHOLD,
    drift_run_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    cleanup_root: Path = DEFAULT_CLEANUP_ROOT,
    cleanup_worktree_age_days: int = DEFAULT_CLEANUP_WORKTREE_AGE_DAYS,
    enable_cleanup: bool = False,
    cleanup_run_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the morning workflow. Returns a result dict (never raises)."""
    started_at = _iso_now()
    started = time.monotonic()
    steps: List[Dict[str, Any]] = []
    yesterday = yesterday or _yesterday_iso()

    # 0. R27_T7 ledger insurance — snapshot pnl_ledger.csv BEFORE
    #    anything downstream can touch it. If this step fails the
    #    critical-alert path below will fire (with R26_S5 dedup),
    #    but the rest of the workflow still runs.
    steps.append(_run_step(
        "ledger_backup", _step_ledger_backup,
        ledger_path=ledger_path, backup_dir=backup_dir,
        keep=int(backup_keep), today=None, dry_run=dry_run,
    ))

    # 1. Settle yesterday.
    steps.append(_run_step(
        "settle_recs", _step_settle_recs,
        date_str=yesterday, snapshot_dir=snapshot_dir,
        settled_path=settled_path, qb_dir=qb_dir, dry_run=dry_run,
    ))

    # 2. Reconcile.
    steps.append(_run_step(
        "reconcile_settlements", _step_reconcile,
        days=int(reconcile_days), dry_run=dry_run,
    ))

    # 3. Compute the report for the morning alert.
    steps.append(_run_step(
        "report_recs", _step_report_recs,
        settled_path=settled_path, days=int(report_days), dry_run=dry_run,
    ))

    # 3b. R27_T3 — feature drift detector (writes cache, fires warn/critical).
    steps.append(_run_step(
        "feature_drift", _step_feature_drift,
        cache_path=drift_cache,
        feature_set=str(drift_feature_set),
        current_days=int(drift_current_days),
        warn_threshold=int(drift_warn_threshold),
        critical_threshold=int(drift_critical_threshold),
        dry_run=dry_run,
        alert_fn=alert_fn,
        run_fn=drift_run_fn,
    ))

    # 4. Refresh dashboard.
    steps.append(_run_step(
        "refresh_dashboard", _step_refresh_dashboard,
        cache_path=dashboard_cache, dry_run=dry_run, collect_fn=collect_fn,
    ))

    # 4b. R28_U3 — nightly cleanup (runs LAST so it can prune everything
    #     earlier steps produced). --commit only when `enable_cleanup` is on.
    steps.append(_run_step(
        "nightly_cleanup", _step_nightly_cleanup,
        cleanup_root=cleanup_root,
        enable_cleanup=bool(enable_cleanup),
        worktree_age_days=int(cleanup_worktree_age_days),
        dry_run=dry_run,
        run_fn=cleanup_run_fn,
    ))

    # 5. Morning info alert with summary fields.
    # Step order: [0]=ledger_backup (R27_T7), [1]=settle, [2]=reconcile,
    # [3]=report, [4]=feature_drift (R27_T3), [5]=refresh_dashboard,
    # [6]=nightly_cleanup (R28_U3).
    settle_d = steps[1].get("details") or {}
    recon_d  = steps[2].get("details") or {}
    rep_d    = steps[3].get("details") or {}
    drift_d  = steps[4].get("details") or {}
    n_settled    = int(settle_d.get("n_settled", 0) or 0)
    win_rate     = float(rep_d.get("win_rate", 0.0) or 0.0)
    roi          = float(rep_d.get("roi", 0.0) or 0.0)
    n_mismatched = int(recon_d.get("n_mismatched", 0) or 0)
    n_drift_major = int(drift_d.get("n_drift_major", 0) or 0)
    fields = [
        {"name": "date",          "value": str(yesterday)},
        {"name": "n_recs_settled","value": str(n_settled)},
        {"name": "win_rate",      "value": f"{win_rate*100:.2f}%"},
        {"name": "roi",           "value": f"{roi*100:+.2f}%"},
        {"name": "n_mismatched",  "value": str(n_mismatched)},
        {"name": "n_drift_major", "value": str(n_drift_major)},
        {"name": "dry_run",       "value": str(bool(dry_run))},
    ]
    msg = (
        f"R26_S3 morning summary {yesterday}: "
        f"settled={n_settled} win_rate={win_rate*100:.1f}% "
        f"roi={roi*100:+.2f}% mismatched={n_mismatched} "
        f"drift_major={n_drift_major}"
    )
    steps.append(_run_step(
        "alert_morning", _step_alert,
        message=msg, level="info", fields=fields,
        dry_run=dry_run, alert_fn=alert_fn,
    ))

    n_critical_failures = sum(1 for s in steps if not s["ok"])
    if n_critical_failures and not dry_run:
        for s in steps:
            if s["ok"]:
                continue
            _safe_alert(
                f"R26_S3 morning step FAILED: {s['name']} — {s.get('error','')}",
                level="critical",
                fields=[
                    {"name": "step",  "value": s["name"]},
                    {"name": "error", "value": (s.get("error") or "")[:200]},
                ],
                alert_fn=alert_fn,
            )

    duration = time.monotonic() - started
    if not dry_run:
        _append_log_entry(
            stage="morning", started_at=started_at,
            duration_sec=duration, steps=steps,
            n_critical_failures=n_critical_failures, log_path=log_path,
        )
    return {
        "stage":               "morning",
        "started_at":          started_at,
        "duration_sec":        duration,
        "n_critical_failures": n_critical_failures,
        "steps":               steps,
        "dry_run":             bool(dry_run),
    }


def run_all(**kwargs: Any) -> Dict[str, Any]:
    """Run evening + morning back-to-back. Returns a combined record."""
    # Distinct kwargs for each — accept only kwargs they recognize.
    evening_kwargs = {
        k: v for k, v in kwargs.items()
        if k in run_evening.__code__.co_varnames
    }
    morning_kwargs = {
        k: v for k, v in kwargs.items()
        if k in run_morning.__code__.co_varnames
    }
    ev = run_evening(**evening_kwargs)
    mo = run_morning(**morning_kwargs)
    return {
        "stage":               "all",
        "evening":             ev,
        "morning":             mo,
        "n_critical_failures": ev["n_critical_failures"] + mo["n_critical_failures"],
    }


# ============================================================================ #
# CLI                                                                          #
# ============================================================================ #
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="R26_S3 — daily cron-able workflow orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "stage", nargs="?", default=None,
        help="Which stage to run: evening | morning | all. Required unless --summary.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would run; never write any side effect.")
    ap.add_argument("--summary", action="store_true",
                    help="Print last N days of run history (defaults --days 7).")
    ap.add_argument("--days", type=int, default=7,
                    help="--summary lookback window (default 7).")

    # Tunable knobs — most callers leave defaults.
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-edge", type=float, default=0.05)
    ap.add_argument("--reconcile-days", type=int, default=1)
    ap.add_argument("--report-days", type=int, default=1)
    ap.add_argument("--today", type=str, default=None,
                    help="Override snapshot date (YYYY-MM-DD).")
    ap.add_argument("--yesterday", type=str, default=None,
                    help="Override settle date (YYYY-MM-DD).")

    # Path overrides — used by the probe + tests.
    ap.add_argument("--snapshot-dir", type=str, default=str(DEFAULT_SNAPSHOT_DIR))
    ap.add_argument("--settled-path", type=str, default=str(DEFAULT_SETTLED_PATH))
    ap.add_argument("--qb-dir",       type=str, default=str(DEFAULT_QB_DIR))
    ap.add_argument("--dashboard-cache", type=str, default=str(DEFAULT_DASHBOARD_CACHE))
    ap.add_argument("--log-path",     type=str, default=str(DEFAULT_LOG_PATH))
    # R27_T7 — ledger insurance knobs.
    ap.add_argument("--ledger-path",  type=str, default=str(DEFAULT_LEDGER_PATH))
    ap.add_argument("--backup-dir",   type=str, default=str(DEFAULT_BACKUP_DIR))
    ap.add_argument("--backup-keep",  type=int, default=DEFAULT_BACKUP_KEEP)
    # R28_U3 — nightly cleanup knobs.
    ap.add_argument("--enable-cleanup", action="store_true",
                    help="Actually delete eligible files (else dry-run inventory only).")
    ap.add_argument("--cleanup-root", type=str, default=str(DEFAULT_CLEANUP_ROOT))
    ap.add_argument("--cleanup-worktree-age-days", type=int,
                    default=DEFAULT_CLEANUP_WORKTREE_AGE_DAYS)
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON result instead of human text.")
    return ap.parse_args(argv)


def _print_result(result: Dict[str, Any]) -> None:
    print(f"stage={result.get('stage')} "
          f"dry_run={result.get('dry_run', False)} "
          f"duration={_fmt_dur(float(result.get('duration_sec', 0.0)))} "
          f"failures={result.get('n_critical_failures', 0)}")
    for s in result.get("steps", []):
        ok = "OK  " if s["ok"] else "FAIL"
        err = f" — {s['error']}" if s.get("error") else ""
        print(f"  [{ok}] {s['name']:<22} "
              f"{_fmt_dur(float(s.get('duration_sec', 0.0))):<8}{err}")


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    if args.summary:
        s = summary(log_path=Path(args.log_path), days=int(args.days))
        if args.json:
            print(json.dumps(s, indent=2, default=str))
        else:
            _print_summary(s)
        return 0

    if args.stage is None:
        print("error: stage is required (evening|morning|all) unless --summary",
              file=sys.stderr)
        return 2
    if args.stage not in STAGES:
        print(f"error: unknown stage {args.stage!r} — pick one of "
              f"{', '.join(STAGES)}", file=sys.stderr)
        return 2

    common_kwargs: Dict[str, Any] = {
        "snapshot_dir":    Path(args.snapshot_dir),
        "dashboard_cache": Path(args.dashboard_cache),
        "log_path":        Path(args.log_path),
        "dry_run":         bool(args.dry_run),
    }

    if args.stage == "evening":
        result = run_evening(
            bankroll=args.bankroll, top=args.top, min_edge=args.min_edge,
            today=args.today, **common_kwargs,
        )
    elif args.stage == "morning":
        result = run_morning(
            settled_path=Path(args.settled_path),
            qb_dir=Path(args.qb_dir),
            reconcile_days=args.reconcile_days,
            report_days=args.report_days,
            yesterday=args.yesterday,
            ledger_path=Path(args.ledger_path),
            backup_dir=Path(args.backup_dir),
            backup_keep=int(args.backup_keep),
            cleanup_root=Path(args.cleanup_root),
            cleanup_worktree_age_days=int(args.cleanup_worktree_age_days),
            enable_cleanup=bool(args.enable_cleanup),
            **common_kwargs,
        )
    elif args.stage == "all":
        result = run_all(
            bankroll=args.bankroll, top=args.top, min_edge=args.min_edge,
            today=args.today, yesterday=args.yesterday,
            settled_path=Path(args.settled_path),
            qb_dir=Path(args.qb_dir),
            reconcile_days=args.reconcile_days,
            report_days=args.report_days,
            ledger_path=Path(args.ledger_path),
            backup_dir=Path(args.backup_dir),
            backup_keep=int(args.backup_keep),
            cleanup_root=Path(args.cleanup_root),
            cleanup_worktree_age_days=int(args.cleanup_worktree_age_days),
            enable_cleanup=bool(args.enable_cleanup),
            **common_kwargs,
        )
    else:
        print(f"error: unknown stage {args.stage!r}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if args.stage == "all":
            for sub in ("evening", "morning"):
                if sub in result:
                    _print_result(result[sub])
        else:
            _print_result(result)

    return 0 if result.get("n_critical_failures", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
