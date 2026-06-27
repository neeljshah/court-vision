"""scripts.platformkit.odds_provider.inplay_retention -- in-play history rotation.

The in-play snapshot daemon appends one dated JSONL file per sport per UTC day:

    data/cache/inplay_history/<sport>/<YYYY-MM-DD>.jsonl

A single busy day (e.g. a World Cup soccer_intl slate) can write hundreds of MB,
and the daemon NEVER rotates -- so on a disk-constrained box the tree grows without
bound (~750 MB observed, ~460 MB for one soccer_intl day) until disk is exhausted.

This module adds a CONSERVATIVE retention sweep: per sport, KEEP the last
*keep_days* UTC day-buckets (default 7, counting today as day 0) and prune ONLY
clearly-older dated .jsonl files. It is deliberately paranoid:

  SAFETY GUARDS (a wrong delete overnight is unacceptable)
  -------------------------------------------------------
  * Only files whose name is EXACTLY "<YYYY-MM-DD>.jsonl" are ever considered;
    a malformed/parse-failing name is SKIPPED (never deleted).
  * The freshness sidecar (_freshness.json) and ANY non-dated file are NEVER touched.
  * TODAY's file (and any future-dated file -- clock skew) is ALWAYS kept.
  * The ACTIVE file -- the day-bucket the daemon is currently appending to (== today)
    -- is therefore always kept by construction.
  * A file is pruned ONLY when its bucket date is STRICTLY OLDER than the cutoff
    (today - keep_days + 1). With keep_days=7 that keeps 7 distinct day-buckets.
  * keep_days is clamped to >= MIN_KEEP_DAYS (3) so a bad caller can't set it to 0
    and wipe recent history. When unsure we keep MORE days, never fewer.
  * Deletion is idempotent: a missing file is a no-op; an unlink error is swallowed
    (the next sweep retries). The sweep NEVER raises.

This is a CHEAP periodic check (a directory listing + a handful of date parses),
designed to be folded into the daemon's existing loop (see sweep cadence in
inplay_snapshot_daemon.serve_inplay_forever) -- NO new always-on daemon.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; stdlib only; PAPER/
measurement only; prunes ONLY old CACHE files under data/cache/inplay_history
(never data/registry). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_retention.py -q
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default kept window (today + 6 prior days = 7 distinct UTC day-buckets). Generous
# on purpose: in-play CLV replay only needs a few recent days, and keeping more is
# always the safe error.
DEFAULT_KEEP_DAYS = 7

# Hard floor: even a misconfigured caller keeps at least this many day-buckets, so
# a 0/negative keep_days can NEVER wipe recent (incl. today's) history.
MIN_KEEP_DAYS = 3

# A dated in-play file is EXACTLY ten chars "YYYY-MM-DD" + ".jsonl"; nothing else
# is eligible for pruning (the freshness sidecar and any legacy file are skipped).
_DATED_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl$")


def _today_utc(now: Optional[datetime] = None) -> date:
    """UTC calendar date for *now* (defaults to wall-clock UTC)."""
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _parse_bucket_date(name: str) -> Optional[date]:
    """Return the bucket date for a "<YYYY-MM-DD>.jsonl" file, else None.

    None when the name is not the exact dated shape OR the y/m/d do not form a real
    calendar date -- in BOTH cases the caller must NOT prune the file.
    """
    m = _DATED_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def plan_sport_sweep(sport_dir: Path, *, keep_days: int = DEFAULT_KEEP_DAYS,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute (DO NOT apply) the retention plan for ONE sport directory.

    Returns {"cutoff": <date|None>, "keep": [Path...], "prune": [Path...],
    "skip": [Path...]} where:
      * prune -- dated files STRICTLY older than the cutoff (today-keep_days+1).
      * keep  -- dated files on/after the cutoff (incl. today + any future-dated).
      * skip  -- everything else (the freshness sidecar, sub-dirs, legacy/odd names).

    Pure + side-effect-free so a test (or a dry run) can assert the plan before any
    unlink happens. *keep_days* is clamped to >= MIN_KEEP_DAYS.
    """
    plan: Dict[str, Any] = {"cutoff": None, "keep": [], "prune": [], "skip": []}
    kd = max(int(keep_days), MIN_KEEP_DAYS)
    today = _today_utc(now)
    # Oldest day-bucket we keep: today minus (kd-1) days. Anything strictly older
    # than this is prunable. Using an ordinal makes the comparison clock-safe.
    cutoff_ord = today.toordinal() - (kd - 1)
    plan["cutoff"] = date.fromordinal(cutoff_ord)
    if not sport_dir.is_dir():
        return plan
    try:
        entries = sorted(sport_dir.iterdir(), key=lambda p: p.name)
    except OSError as exc:  # noqa: BLE001 -- unreadable dir -> sweep nothing
        logger.warning("inplay_retention: cannot list %s: %s", sport_dir, exc)
        return plan
    for entry in entries:
        if not entry.is_file():
            plan["skip"].append(entry)        # sub-dirs are never pruned
            continue
        bucket = _parse_bucket_date(entry.name)
        if bucket is None:                    # sidecar / legacy / odd name
            plan["skip"].append(entry)
            continue
        # STRICTLY-older test; today (and future-dated -> clock skew) always kept.
        if bucket.toordinal() < cutoff_ord:
            plan["prune"].append(entry)
        else:
            plan["keep"].append(entry)
    return plan


def sweep_sport(sport_dir: Path, *, keep_days: int = DEFAULT_KEEP_DAYS,
                now: Optional[datetime] = None,
                dry_run: bool = False) -> Dict[str, Any]:
    """Apply the retention plan for ONE sport dir. Returns a result summary.

    Idempotent + never raises: a missing file is a no-op; an unlink error is logged
    and counted in "errors" (the next sweep retries). When *dry_run* the plan is
    computed but NOTHING is deleted (used by the test + by a safety preview).
    Result: {"sport_dir", "cutoff", "kept", "pruned", "skipped", "errors",
    "pruned_paths"}.
    """
    plan = plan_sport_sweep(sport_dir, keep_days=keep_days, now=now)
    pruned_paths: List[str] = []
    errors = 0
    if not dry_run:
        for path in plan["prune"]:
            try:
                path.unlink()
                pruned_paths.append(str(path))
            except FileNotFoundError:
                pass                          # already gone -> idempotent no-op
            except OSError as exc:  # noqa: BLE001 -- never sink the sweep
                errors += 1
                logger.warning("inplay_retention: unlink failed for %s: %s",
                               path, exc)
    else:
        pruned_paths = [str(p) for p in plan["prune"]]
    return {
        "sport_dir": str(sport_dir),
        "cutoff": plan["cutoff"].isoformat() if plan["cutoff"] else None,
        "kept": len(plan["keep"]),
        "pruned": len(pruned_paths),
        "skipped": len(plan["skip"]),
        "errors": errors,
        "pruned_paths": pruned_paths,
    }


def sweep_all(base_dir: Path, *, keep_days: int = DEFAULT_KEEP_DAYS,
              now: Optional[datetime] = None,
              dry_run: bool = False) -> Dict[str, Any]:
    """Sweep EVERY sport sub-directory under *base_dir* (the inplay_history root).

    Only immediate sub-directories are swept (each is one sport). Loose files in the
    root (e.g. a legacy top-level fixture) are NEVER touched. Per-sport isolation: a
    failure in one sport dir cannot stop the others. Never raises.
    Result: {"base_dir", "keep_days", "sports": [<per-sport summary>...],
    "total_pruned"}.
    """
    kd = max(int(keep_days), MIN_KEEP_DAYS)
    out: Dict[str, Any] = {
        "base_dir": str(base_dir), "keep_days": kd, "sports": [], "total_pruned": 0,
    }
    if not base_dir.is_dir():
        return out
    try:
        sport_dirs = sorted(
            (p for p in base_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError as exc:  # noqa: BLE001
        logger.warning("inplay_retention: cannot list base %s: %s", base_dir, exc)
        return out
    for sport_dir in sport_dirs:
        try:
            summary = sweep_sport(sport_dir, keep_days=kd, now=now, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 -- isolate one sport's failure
            logger.warning("inplay_retention: sweep_sport(%s) failed: %s",
                           sport_dir, exc)
            continue
        out["sports"].append(summary)
        out["total_pruned"] += summary.get("pruned", 0)
    return out


__all__ = [
    "DEFAULT_KEEP_DAYS", "MIN_KEEP_DAYS",
    "plan_sport_sweep", "sweep_sport", "sweep_all",
]
