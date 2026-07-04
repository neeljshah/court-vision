"""scripts.platformkit.ingame.sidecar_retention -- ENRICHMENT sidecar retention (LANE 3).

The enrichment sidecars this runner (m37_ingame_enrichment) and its sources write to
today have NO retention/rotation policy (per ENRICHMENT_PERSISTENCE_NOTE.md section 1):
gumbo_live/, espn_wp/, fotmob_live/, book_depth/ (+ the not-yet-materialized cdn_live/)
grow append-only forever. A future disk-prune of data/cache//data/domains/** could
silently drop the enrichment side of an as-of join with no warning.

This module is a DECLARATIVE, CONSERVATIVE policy + enforcement tick:
  * POLICY = one {dir, max_age_days, max_bytes} entry per sidecar tree (DEFAULT_POLICY).
  * plan_dir() computes (never applies) which files are "active" (kept in place) vs
    "stale" (older than max_age_days OR pushed over max_bytes by cumulative size,
    oldest-mtime-first) -- pure, side-effect-free, testable.
  * enforce_dir() / enforce_all() APPLY the plan by ARCHIVING stale files: each moves
    to <dir>/_archive/<relative-path> (mkdir -p as needed). NEVER deletes -- the charter
    binding invariant ("never delete data") applies to enrichment sidecars same as any
    other corpus. A future consumer can still read _archive/ (uncompressed, same jsonl
    shape) if an old as-of join is ever needed; a live consumer only reads the ACTIVE tree
    so archiving does not slow down normal reads.

SAFETY GUARDS (mirrors odds_provider.inplay_retention's paranoia):
  * The _archive/ subdirectory itself is NEVER re-swept (no double-archiving, no loop).
  * A file already under _archive/ is skipped by construction (walk excludes it).
  * mtime-based age (not filename parsing) so per-game-id files (e.g. gumbo_live's
    <pk>.jsonl, espn_wp's <event_id>.jsonl / _series.json) are covered without needing a
    dated-filename convention like inplay_history's.
  * A move failure (races, permissions) is logged and counted in "errors"; the file stays
    in place (retried next tick) -- never a partial/lost file.
  * Idempotent: re-running enforce_* on an already-archived file is a no-op (the walk
    never revisits _archive/); moving a file that no longer exists is swallowed.
  * max_bytes is a SOFT cap: only pushes the OLDEST-by-mtime active files into archive
    until under budget, never touches files within max_age_days regardless of size
    UNLESS over budget (age policy alone can already satisfy the byte budget).

Defaults (documented, not applied automatically -- caller passes a policy or uses
DEFAULT_POLICY): 30 days active-retention per sidecar tree, generous byte budgets sized
to the note's measured volumes (Section 2) with headroom. Sane, conservative, easy to
override per-tree.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII; stdlib only; never
deletes; never touches data/registry/; never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_sidecar_retention.py -q
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_ARCHIVE_SUBDIR = "_archive"

# Hard floor: even a misconfigured caller keeps at least this many days of ACTIVE
# history before a file becomes archive-eligible on age grounds alone.
MIN_ACTIVE_DAYS = 7


@dataclass(frozen=True)
class SidecarPolicy:
    """One retention entry: a sidecar directory + its active-retention limits.

    max_age_days: files whose mtime is STRICTLY older than (now - max_age_days) are
      archive-eligible on age grounds. None = no age-based archiving (bytes-only).
    max_bytes: soft cumulative-size budget for the ACTIVE (non-archived) tree; when the
      active total exceeds this, the OLDEST-mtime active files are pushed to archive
      (oldest-first) until under budget. None = no byte-based archiving (age-only).
    """
    name: str
    dir: Path
    max_age_days: Optional[int] = 30
    max_bytes: Optional[int] = None


# DEFAULT_POLICY -- the 5 enrichment sidecar trees named in the retention brief.
# 30-day active window is generous (well past any plausible as-of-join replay need) and
# matches the "sane defaults (e.g. 30d active + archive)" instruction. Byte budgets are
# sized with headroom over the note's MEASURED volumes (Section 2): book_depth is the
# highest-volume tree (kalshi+polymarket ticks), so it gets the largest budget.
DEFAULT_POLICY: List[SidecarPolicy] = [
    SidecarPolicy("fotmob_live", _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live",
                  max_age_days=30, max_bytes=500 * 1024 * 1024),
    SidecarPolicy("gumbo_live", _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live",
                  max_age_days=30, max_bytes=1024 * 1024 * 1024),
    SidecarPolicy("book_depth", _REPO_ROOT / "data" / "cache" / "book_depth",
                  max_age_days=30, max_bytes=2 * 1024 * 1024 * 1024),
    SidecarPolicy("espn_wp_mlb", _REPO_ROOT / "data" / "domains" / "mlb" / "espn_wp",
                  max_age_days=30, max_bytes=500 * 1024 * 1024),
    SidecarPolicy("cdn_live_wnba", _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_live",
                  max_age_days=30, max_bytes=500 * 1024 * 1024),
]


def _now_utc(now: Optional[datetime] = None) -> datetime:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _walk_active_files(base: Path) -> List[Path]:
    """All files under *base*, EXCLUDING anything under _archive/ (never re-swept)."""
    out: List[Path] = []
    if not base.is_dir():
        return out
    try:
        for root, dirs, files in os.walk(base):
            # prune _archive/ from the walk in-place so os.walk never descends into it.
            dirs[:] = [d for d in dirs if d != _ARCHIVE_SUBDIR]
            for f in files:
                out.append(Path(root) / f)
    except OSError as exc:  # noqa: BLE001 -- unreadable dir -> plan nothing
        logger.warning("sidecar_retention: cannot walk %s: %s", base, exc)
    return out


def plan_dir(policy: SidecarPolicy, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute (never apply) the archive plan for ONE sidecar policy.

    Returns {"dir", "cutoff_epoch", "active": [Path...], "stale": [Path...]} where
    stale = age-eligible files UNION the oldest-mtime files pushed over max_bytes.
    Pure + side-effect-free -- callers/tests can assert the plan before any move.
    """
    nowdt = _now_utc(now)
    max_age = max(int(policy.max_age_days), MIN_ACTIVE_DAYS) if policy.max_age_days else None
    cutoff_epoch = (nowdt.timestamp() - max_age * 86400.0) if max_age is not None else None
    plan: Dict[str, Any] = {
        "dir": str(policy.dir), "cutoff_epoch": cutoff_epoch, "active": [], "stale": [],
    }
    files = _walk_active_files(policy.dir)
    if not files:
        return plan

    stats: List[Any] = []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue  # vanished mid-scan -- skip, never guess
        stats.append((f, st.st_mtime, st.st_size))

    stale_set = set()
    # 1. age-based eligibility.
    if cutoff_epoch is not None:
        for f, mtime, _size in stats:
            if mtime < cutoff_epoch:
                stale_set.add(f)

    # 2. byte-budget eligibility: only ACTIVE (not already age-stale) files count toward
    #    the live budget; push the oldest-mtime ACTIVE files into stale until under budget.
    if policy.max_bytes is not None:
        active_now = [(f, m, s) for f, m, s in stats if f not in stale_set]
        total = sum(s for _f, _m, s in active_now)
        if total > policy.max_bytes:
            for f, _m, s in sorted(active_now, key=lambda t: t[1]):  # oldest mtime first
                if total <= policy.max_bytes:
                    break
                stale_set.add(f)
                total -= s

    for f, _m, _s in stats:
        (plan["stale"] if f in stale_set else plan["active"]).append(f)
    return plan


def enforce_dir(policy: SidecarPolicy, *, now: Optional[datetime] = None,
               dry_run: bool = False) -> Dict[str, Any]:
    """Apply ONE policy's plan: move each stale file to <dir>/_archive/<relpath>.

    NEVER deletes. A move failure is logged + counted in "errors" and the file is left
    in place (retried next tick). Idempotent: an already-missing source is a no-op.
    Result: {"name", "dir", "kept", "archived", "errors", "archived_paths"}.
    """
    plan = plan_dir(policy, now=now)
    archived: List[str] = []
    errors = 0
    archive_root = policy.dir / _ARCHIVE_SUBDIR
    if not dry_run:
        for src in plan["stale"]:
            try:
                rel = src.relative_to(policy.dir)
            except ValueError:
                rel = Path(src.name)
            dest = archive_root / rel
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not src.is_file():
                    continue  # already gone -- idempotent no-op
                shutil.move(str(src), str(dest))
                archived.append(str(dest))
            except OSError as exc:  # noqa: BLE001 -- never sink the tick
                errors += 1
                logger.warning("sidecar_retention: archive failed for %s: %s", src, exc)
    else:
        archived = [str(p) for p in plan["stale"]]
    return {
        "name": policy.name, "dir": str(policy.dir),
        "kept": len(plan["active"]), "archived": len(archived),
        "errors": errors, "archived_paths": archived,
    }


def enforce_all(policies: Optional[List[SidecarPolicy]] = None, *,
                now: Optional[datetime] = None,
                dry_run: bool = False) -> Dict[str, Any]:
    """Run enforce_dir over every policy (default DEFAULT_POLICY). Per-tree ISOLATED --
    one tree's failure never stops the others. Never raises. Result: {"trees": [...],
    "total_archived", "total_errors"}."""
    pols = policies if policies is not None else DEFAULT_POLICY
    out: Dict[str, Any] = {"trees": [], "total_archived": 0, "total_errors": 0}
    for pol in pols:
        try:
            summary = enforce_dir(pol, now=now, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 -- isolate one tree's failure
            logger.warning("sidecar_retention: enforce_dir(%s) failed: %s", pol.name, exc)
            out["trees"].append({"name": pol.name, "dir": str(pol.dir),
                                 "kept": 0, "archived": 0, "errors": 1, "archived_paths": []})
            out["total_errors"] += 1
            continue
        out["trees"].append(summary)
        out["total_archived"] += summary.get("archived", 0)
        out["total_errors"] += summary.get("errors", 0)
    return out


__all__ = [
    "MIN_ACTIVE_DAYS", "SidecarPolicy", "DEFAULT_POLICY",
    "plan_dir", "enforce_dir", "enforce_all",
]
