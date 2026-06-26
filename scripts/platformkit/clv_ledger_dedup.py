"""scripts.platformkit.clv_ledger_dedup -- status-keyed dedup + idempotent append guard.

Public surfaces:
  sanitize_rows(rows) -> (kept_rows, dropped_count)  -- pure function, zero I/O.
  append_if_new(record, path) -> bool                -- dup-guard conditional append.
  dedup_ledger(path, dry_run=True)  -> status dict   -- atomic idempotent rewrite.

Dedup key = "<bet_id>|<status>": open + settled twin of the same bet -> DISTINCT
keys -> BOTH kept.  Same bet_id AND same status -> dup -> second dropped.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; UNITS ONLY.
Per-file test: python -m pytest scripts/platformkit/test_clv_ledger_dedup.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id, load_ledger
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

# ---------------------------------------------------------------------------
# Status-aware dedup key (mirrors governance._row_key)
# ---------------------------------------------------------------------------

_DEFAULT_STATUS = "open"


def _row_key(row: Dict[str, Any]) -> str:
    """Return "<bet_id>|<status>" dedup key. Different status -> distinct keys.
    Falls back to _DEFAULT_STATUS ("open") when "status" is absent.
    """
    bid = str(row.get("bet_id") or bet_id(row))
    status = str(row.get("status") or _DEFAULT_STATUS).strip().lower()
    return "%s|%s" % (bid, status)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _seen_row_keys(path: Path) -> Set[str]:
    """Return the set of (bet_id|status) keys already present in the ledger.

    Missing file -> empty set. Blank lines and malformed JSON are skipped.
    """
    rows = load_ledger(path)
    return {_row_key(r) for r in rows}


def _first_occurrence_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (deduped_rows, n_dups_removed) keeping FIRST occurrence per key.

    Key is (bet_id|status) so open+settled twins are both retained.
    Stable order. Rows without a bet_id are assigned one via the bet_id formula.
    """
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    dups = 0
    for r in rows:
        key = _row_key(r)
        if key in seen:
            dups += 1
        else:
            seen.add(key)
            out.append(r)
    return out, dups


def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with all banned dollar/pnl/roi keys removed."""
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


# ---------------------------------------------------------------------------
# Public surface 1: pure sanitizer (no I/O -- safe for human-review dry-run)
# ---------------------------------------------------------------------------

def sanitize_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Collapse dup rows by status-folded key (<bet_id>|<status>). Pure; zero I/O.

    open -> keep FIRST; settled -> keep LAST; open+settled twin -> BOTH kept.
    BANNED_KEYS stripped from every output row. DEFAULT_LEDGER never touched.
    Returns (kept_rows, dropped_count).
    """
    first_open: "Dict[str, int]" = {}    # key -> first seen index (open)
    last_settled: "Dict[str, int]" = {}  # key -> last  seen index (settled)
    other_first: "Dict[str, int]" = {}   # key -> first seen index (other)

    for idx, row in enumerate(rows):
        key = _row_key(row)
        status = str(row.get("status") or _DEFAULT_STATUS).strip().lower()
        if status == "open":
            if key not in first_open:
                first_open[key] = idx
        elif status == "settled":
            last_settled[key] = idx          # always overwrite -> last wins
        else:
            if key not in other_first:
                other_first[key] = idx

    # Collect the winning indexes and sort to preserve original order.
    winning: Set[int] = set()
    winning.update(first_open.values())
    winning.update(last_settled.values())
    winning.update(other_first.values())

    kept = [_strip_dollar_keys(rows[i]) for i in sorted(winning)]
    dropped = len(rows) - len(kept)
    return kept, dropped


# ---------------------------------------------------------------------------
# Public surface 2: append guard
# ---------------------------------------------------------------------------

def append_if_new(
    record: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> bool:
    """Append *record* only if its (bet_id|status) key is absent. Returns True/False.

    *_seen* is an optional pre-built key set to avoid re-scanning on every batch
    call -- it is updated in-place when a row is written. Never raises.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    try:
        key = _row_key(record)
        existing: Set[str] = _seen if _seen is not None else _seen_row_keys(target)
        if key in existing:
            return False
        # Strip any dollar keys before writing (belt-and-suspenders).
        clean = _strip_dollar_keys(record)
        if not clean.get("bet_id"):
            clean["bet_id"] = str(record.get("bet_id") or bet_id(record))
        # Funnel through the lock-guarded primitive when available.
        try:
            from scripts.platformkit.clv_ledger_io import append_row as _append_row
        except Exception:  # noqa: BLE001
            _append_row = None  # type: ignore[assignment]
        if _append_row is not None:
            try:
                _append_row(clean, path=target)
                if _seen is not None:
                    _seen.add(key)
                return True
            except Exception:  # noqa: BLE001 - fall through to direct write
                pass
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(clean, default=str) + "\n")
        if _seen is not None:
            _seen.add(key)
        return True
    except Exception:  # noqa: BLE001
        return False  # never let the guard crash the caller


# ---------------------------------------------------------------------------
# Public surface 2: idempotent dedup rewrite
# ---------------------------------------------------------------------------

def dedup_ledger(
    path: Optional[Path] = None,
    *,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Idempotent dedup rewrite; dry_run=True (default) never touches the file.

    Returns {status, rows_in, rows_out, dups_removed, path, dry_run}.
    status: "ok" | "dry_run" | "no_change" | "no_file" | "error: <Type>".
    Atomic (tmp+replace) + backed-up (.bak). Dollar keys stripped from all rows.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    result: Dict[str, Any] = {
        "status": "ok",
        "rows_in": 0,
        "rows_out": 0,
        "dups_removed": 0,
        "path": str(target),
        "dry_run": dry_run,
    }
    if not target.exists():
        result["status"] = "no_file"
        return result
    try:
        rows = load_ledger(target)
        result["rows_in"] = len(rows)
        # Strip dollar keys from every row before dedup so the result is clean.
        rows_clean = [_strip_dollar_keys(r) for r in rows]
        deduped, dups = _first_occurrence_rows(rows_clean)
        result["rows_out"] = len(deduped)
        result["dups_removed"] = dups
        if dups == 0:
            result["status"] = "no_change"
            return result
        # Dry-run: report what WOULD change but leave the file untouched.
        if dry_run:
            result["status"] = "dry_run"
            return result
        # Backup the original (overwrite any prior .bak so re-runs stay clean).
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        # Atomic rewrite: write to a tmp file in the same directory, then replace.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=target.name + ".", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for r in deduped:
                    fh.write(json.dumps(r, default=str) + "\n")
            os.replace(tmp_name, str(target))
        finally:
            if Path(tmp_name).exists():
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 - dedup must never crash the box
        result["status"] = "error: %s" % type(exc).__name__
    return result


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "Dedup the CLV ledger keyed on (bet_id|status): keeps first "
            "occurrence, open+settle twins both retained, idempotent, atomic. "
            "Read-safe by default: pass --apply to commit the rewrite."
        )
    )
    ap.add_argument("--ledger", default=None, help="override ledger path")
    ap.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="commit the dedup rewrite (default is dry-run only)",
    )
    a = ap.parse_args(list(argv) if argv is not None else None)
    res = dedup_ledger(
        Path(a.ledger) if a.ledger else None,
        dry_run=not a.apply,
    )
    print(json.dumps(res, default=str))
    status = str(res.get("status", ""))
    return 0 if status in ("ok", "no_change", "no_file", "dry_run") else 1


# Public surface 4: truly-open bet helpers (pure, zero I/O)

def open_unsettled_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return rows that are "open" AND have no "settled" twin in *rows*.
    Preserves input order.  Pure; zero I/O.
    """
    settled_bids: Set[str] = {
        str(r.get("bet_id") or bet_id(r))
        for r in rows
        if str(r.get("status") or _DEFAULT_STATUS).strip().lower() == "settled"
    }
    return [
        r for r in rows
        if str(r.get("status") or _DEFAULT_STATUS).strip().lower() == "open"
        and str(r.get("bet_id") or bet_id(r)) not in settled_bids
    ]


def count_open_unsettled(rows: List[Dict[str, Any]]) -> int:
    """Return len(open_unsettled_rows(rows)).  Pure; zero I/O."""
    return len(open_unsettled_rows(rows))


__all__ = [
    "sanitize_rows",
    "append_if_new",
    "dedup_ledger",
    "_row_key",
    "open_unsettled_rows",
    "count_open_unsettled",
]

if __name__ == "__main__":
    raise SystemExit(_main())
