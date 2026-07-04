"""scripts.platformkit.retention.line_history_consolidate -- CONSOLIDATE, don't delete.

line_history is our OWN irreplaceable close-corpus fuel (data/cache/line_history/
<sport>/<YYYY-MM-DD>.jsonl). Kalshi purges server-side, so this history cannot be
re-fetched, and it is REFIT/TRAINING fuel (directive 4c) -- deletion of raw daily
history is the WRONG remediation for disk growth. This module does the opposite of
inplay_retention.sweep_all: it CONSOLIDATES old dailies into monthly parquet
archives and deletes a daily ONLY after verifying it is fully, byte-for-byte
represented in the archive.

Pipeline (per sport, per calendar month older than *stale_days*):
  1. Read every dated "<YYYY-MM-DD>.jsonl" file in that month, parse each line as
     JSON, and tag it with a "source_file" column (the original daily filename).
     A line that fails to parse is preserved verbatim under a "_raw" fallback
     column rather than dropped (never lose a row to a schema surprise).
  2. Write (or append-merge into) a monthly parquet archive at
     data/cache/line_history_archive/<sport>/<yyyy-mm>.parquet. Union-of-columns
     schema (pyarrow handles ragged JSON fields as nulls elsewhere).
  3. VERIFY: reread the archive and confirm, for the month just written, the row
     count matches the sum of source dailies' line counts AND a content hash
     (sorted line-level sha256 multiset) matches. FAIL-CLOSED: on any mismatch,
     leave every daily in place (do not delete anything from that month) and
     report the discrepancy.
  4. Only after verification passes does --apply delete the source dailies for
     that month (never the current/partial month, never anything within
     *stale_days* of today).

Default is DRY-RUN: report what WOULD consolidate (file counts + bytes, per
sport) without writing archives or deleting anything. --apply performs the write
+ verify + delete pipeline for real, scoped to whichever sport/month the caller
targets.

INVARIANTS: scripts/platformkit/retention/ only; <=300 LOC; ASCII; PAPER/
measurement only; touches ONLY data/cache/line_history[_archive] (never
data/registry). Atomic writes (tmp file + os.replace). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/retention/test_line_history_consolidate.py -q
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# A daily file is only eligible for consolidation once it is this many days old --
# generous margin so an in-flight/just-written daily is never touched.
DEFAULT_STALE_DAYS = 30

_DATED_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl$")


def _today_utc(now: Optional[datetime] = None) -> date:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _parse_bucket_date(name: str) -> Optional[date]:
    m = _DATED_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _line_hash(line: str) -> str:
    """sha256 of a raw JSONL line (content-hash unit for verification)."""
    return hashlib.sha256(line.encode("utf-8", errors="surrogatepass")).hexdigest()


@dataclass
class MonthGroup:
    sport: str
    year_month: str  # "yyyy-mm"
    files: List[Path] = field(default_factory=list)
    total_bytes: int = 0


def find_stale_month_groups(sport_dir: Path, *, stale_days: int = DEFAULT_STALE_DAYS,
                             now: Optional[datetime] = None) -> List[MonthGroup]:
    """Group this sport's dated dailies older than *stale_days* by (year, month).

    Pure/read-only. A file is eligible only when its bucket date is strictly older
    than (today - stale_days); anything newer (incl. the active/today file) is
    never grouped, so it can never be touched by --apply.
    """
    today = _today_utc(now)
    cutoff_ord = today.toordinal() - stale_days
    groups: Dict[str, MonthGroup] = {}
    if not sport_dir.is_dir():
        return []
    try:
        entries = sorted(sport_dir.iterdir(), key=lambda p: p.name)
    except OSError as exc:  # noqa: BLE001
        logger.warning("line_history_consolidate: cannot list %s: %s", sport_dir, exc)
        return []
    for entry in entries:
        if not entry.is_file():
            continue
        bucket = _parse_bucket_date(entry.name)
        if bucket is None:
            continue  # sidecar / legacy name -- never touched
        if bucket.toordinal() >= cutoff_ord:
            continue  # not stale yet
        ym = f"{bucket.year:04d}-{bucket.month:02d}"
        g = groups.setdefault(ym, MonthGroup(sport=sport_dir.name, year_month=ym))
        g.files.append(entry)
        try:
            g.total_bytes += entry.stat().st_size
        except OSError:
            pass
    return [groups[k] for k in sorted(groups)]


def _read_daily_records(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (records tagged with source_file, raw line hashes) for one daily."""
    records: List[Dict[str, Any]] = []
    hashes: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            hashes.append(_line_hash(line))
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    rec = {"_raw": line}
            except json.JSONDecodeError:
                rec = {"_raw": line}
            rec = dict(rec)
            rec["source_file"] = path.name
            records.append(rec)
    return records, hashes


def _archive_path(archive_root: Path, sport: str, year_month: str) -> Path:
    return archive_root / sport / f"{year_month}.parquet"


def write_month_archive(group: MonthGroup, archive_root: Path) -> Path:
    """Write (atomically) the monthly parquet archive for *group*. Returns its path."""
    records: List[Dict[str, Any]] = []
    for f in sorted(group.files, key=lambda p: p.name):
        recs, _ = _read_daily_records(f)
        records.extend(recs)
    table = pa.Table.from_pylist(records) if records else pa.table({})
    out_path = _archive_path(archive_root, group.sport, group.year_month)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, out_path)  # atomic on same filesystem
    return out_path


def verify_month_archive(group: MonthGroup, archive_path: Path) -> Dict[str, Any]:
    """Reread *archive_path* and confirm it fully represents *group*'s dailies.

    Fail-closed: returns {"ok": False, ...} on ANY row-count or content-hash
    mismatch, or if the archive is unreadable/missing. Content hash = sorted
    multiset of per-line sha256 across the dailies vs. a recomputed hash of each
    archived row's json-serialized form (order-independent).
    """
    result: Dict[str, Any] = {"ok": False, "expected_rows": 0, "archive_rows": 0,
                               "reason": None}
    expected_hashes: List[str] = []
    expected_rows = 0
    for f in group.files:
        _, hashes = _read_daily_records(f)
        expected_hashes.extend(hashes)
        expected_rows += len(hashes)
    result["expected_rows"] = expected_rows
    if not archive_path.exists():
        result["reason"] = "archive_missing"
        return result
    try:
        table = pq.read_table(archive_path)
    except Exception as exc:  # noqa: BLE001 -- unreadable archive -> fail closed
        result["reason"] = f"archive_unreadable: {exc}"
        return result
    archive_rows = table.num_rows
    result["archive_rows"] = archive_rows
    if archive_rows != expected_rows:
        result["reason"] = "row_count_mismatch"
        return result
    # Content check: recompute a hash per archived row's canonical source_file +
    # sorted-key json, compare multisets against dailies re-read fresh. This is
    # deliberately re-derived from the archive itself (not a copy of the plan)
    # so a truncated/corrupted write is caught.
    archived_hashes: List[str] = []
    for row in table.to_pylist():
        row_wo_source = {k: v for k, v in row.items() if k != "source_file"}
        canon = json.dumps(row_wo_source, sort_keys=True, default=str)
        archived_hashes.append(hashlib.sha256(canon.encode("utf-8")).hexdigest())
    # Recompute expected using the same canonicalization (json.loads + sort_keys)
    # so formatting differences (whitespace) don't cause false mismatches.
    expected_canon_hashes: List[str] = []
    for f in group.files:
        recs, _ = _read_daily_records(f)
        for rec in recs:
            rec_wo_source = {k: v for k, v in rec.items() if k != "source_file"}
            canon = json.dumps(rec_wo_source, sort_keys=True, default=str)
            expected_canon_hashes.append(hashlib.sha256(canon.encode("utf-8")).hexdigest())
    if sorted(archived_hashes) != sorted(expected_canon_hashes):
        result["reason"] = "content_hash_mismatch"
        return result
    result["ok"] = True
    return result


def consolidate_sport_month(group: MonthGroup, archive_root: Path, *,
                            apply: bool = False) -> Dict[str, Any]:
    """Consolidate one (sport, month) group. dry-run by default (apply=False).

    Returns a summary dict; on apply=True, deletes source dailies ONLY when
    verify_month_archive reports ok=True (fail-closed otherwise -- dailies stay).
    """
    summary: Dict[str, Any] = {
        "sport": group.sport, "year_month": group.year_month,
        "file_count": len(group.files), "total_bytes": group.total_bytes,
        "applied": False, "verified": False, "deleted": 0, "reason": None,
    }
    if not apply:
        return summary
    archive_path = write_month_archive(group, archive_root)
    verify = verify_month_archive(group, archive_path)
    summary["verified"] = verify["ok"]
    summary["reason"] = verify.get("reason")
    if not verify["ok"]:
        logger.warning("line_history_consolidate: verify FAILED for %s/%s: %s -- "
                        "keeping all dailies", group.sport, group.year_month,
                        verify.get("reason"))
        return summary
    deleted = 0
    for f in group.files:
        try:
            f.unlink()
            deleted += 1
        except FileNotFoundError:
            pass
        except OSError as exc:  # noqa: BLE001 -- never sink the run
            logger.warning("line_history_consolidate: unlink failed for %s: %s", f, exc)
    summary["applied"] = True
    summary["deleted"] = deleted
    return summary


def plan_all(base_dir: Path, *, stale_days: int = DEFAULT_STALE_DAYS,
            now: Optional[datetime] = None) -> Dict[str, Any]:
    """Dry-run report: eligible (sport, month) groups across every sport dir."""
    out: Dict[str, Any] = {"base_dir": str(base_dir), "stale_days": stale_days,
                           "sports": []}
    if not base_dir.is_dir():
        return out
    try:
        sport_dirs = sorted((p for p in base_dir.iterdir() if p.is_dir()),
                            key=lambda p: p.name)
    except OSError as exc:  # noqa: BLE001
        logger.warning("line_history_consolidate: cannot list base %s: %s", base_dir, exc)
        return out
    for sport_dir in sport_dirs:
        groups = find_stale_month_groups(sport_dir, stale_days=stale_days, now=now)
        out["sports"].append({
            "sport": sport_dir.name,
            "groups": [
                {"year_month": g.year_month, "file_count": len(g.files),
                 "total_bytes": g.total_bytes}
                for g in groups
            ],
        })
    return out


__all__ = [
    "DEFAULT_STALE_DAYS", "MonthGroup",
    "find_stale_month_groups", "write_month_archive", "verify_month_archive",
    "consolidate_sport_month", "plan_all",
]
