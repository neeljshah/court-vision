"""scripts.platformkit.clv_ledger_sanity -- CLV ledger health + guarded purge.

scan_ledger  -- read-only report (synthetic / malformed / dup / CLV honesty).
scan_assert  -- CI assertion: raises AssertionError when ledger is dirty.
purge_ledger -- EXPLICIT CLI ONLY; drops synthetic+malformed rows; backs up first.

STATUS SEMANTICS (binding)
  "INSUFFICIENT_DATA" -- missing/empty ledger; cannot assess.
  "dirty"             -- any synthetic, malformed, or dup-key row.
  "clean"             -- zero of all three.

HONESTY INVARIANTS
  * scan_ledger / scan_assert are READ-ONLY; never mutate ledger.
  * purge_ledger is NEVER auto-run (no tick / import side-effect).
  * No $ / pnl / profit / bankroll / roi key in any output.
  * status is NEVER "clean" when synthetic or malformed rows exist.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_sanity.py -q
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_MIN_GAME_ID_LEN: int = 3
_REQUIRED_KEYS: Tuple[str, ...] = ("sport", "status", "side")


def _default_ledger() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"


def _raw_load(path: Path) -> List[Dict[str, Any]]:
    """Load all parseable rows WITHOUT the synthetic read-time filter."""
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _is_synthetic(row: Dict[str, Any]) -> bool:
    sport = str(row.get("sport") or "")
    bid = str(row.get("bet_id") or "")
    return sport.startswith("test_") or bid.startswith("test_")


def _is_malformed(row: Dict[str, Any]) -> bool:
    for k in _REQUIRED_KEYS:
        if k not in row:
            return True
    gid = row.get("game_id")
    if gid is not None and len(str(gid)) < _MIN_GAME_ID_LEN:
        return True
    return False


def _dup_key(row: Dict[str, Any]) -> str:
    game = str(row.get("game_id") or row.get("matchup") or row.get("event_id") or "")
    market = str(row.get("market") or row.get("market_type") or "")
    side = str(row.get("side") or "")
    venue = str(row.get("taken_book") or row.get("venue") or row.get("book") or "")
    date = str(row.get("game_date") or row.get("date") or "")[:10]
    return "|".join([game, market, side, str(row.get("status") or ""), venue, date])


def _count_dups(rows: List[Dict[str, Any]]) -> Tuple[int, Set[str]]:
    counts: Dict[str, int] = {}
    for r in rows:
        k = _dup_key(r)
        counts[k] = counts.get(k, 0) + 1
    extra, dup_keys = 0, set()
    for k, cnt in counts.items():
        if cnt > 1:
            extra += cnt - 1
            dup_keys.add(k)
    return extra, dup_keys


def _canonical_dup_count(rows: List[Dict[str, Any]]) -> Optional[int]:
    """Read through the canonical-identity index: dup_count = GENUINE collisions
    (same bet_id/edge_key), not coarse matchup-fallback false positives (a
    recurring team matchup across a season). None -> fall back to coarse count.
    Never raises, never mutates the ledger."""
    try:
        from scripts.platformkit.clv_ledger_canonical_index import (
            _canonical_key, _completeness_score,
        )
    except Exception:  # noqa: BLE001 -- read-through is best-effort
        return None
    by_canon: Dict[Any, List[int]] = {}
    for idx, row in enumerate(rows):
        by_canon.setdefault(_canonical_key(row), []).append(idx)
    extra = 0
    for idxs in by_canon.values():
        if len(idxs) > 1:
            extra += len(idxs) - 1
    return extra


def _insuf(reason: str) -> Dict[str, Any]:
    return {
        "status": "INSUFFICIENT_DATA",
        "total_rows": 0,
        "synthetic": {"count": 0, "label": ""},
        "malformed": {"count": 0, "label": ""},
        "duplicates": {"count": 0, "label": ""},
        "honest_clv": {
            "settled_with_clv": 0,
            "settled_without_clv": 0,
            "no_close_label": "INSUFFICIENT_DATA: " + reason,
        },
        "honest_note": (
            "calibration not edge; read-only scan; no $ field; INSUFFICIENT_DATA -- %s"
            % reason
        ),
    }


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def scan_ledger(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only health scan. Never mutates. No $ key in output."""
    p = Path(path) if path is not None else _default_ledger()
    if not p.exists() or p.stat().st_size == 0:
        return _insuf("missing or empty file")
    rows = _raw_load(p)
    if not rows:
        return _insuf("no parseable rows")

    n_syn = sum(1 for r in rows if _is_synthetic(r))
    n_mal = sum(1 for r in rows if _is_malformed(r))
    n_dup_coarse, _ = _count_dups(rows)
    n_dup_canonical = _canonical_dup_count(rows)  # true identity, reconciles false positives
    n_dup = n_dup_canonical if n_dup_canonical is not None else n_dup_coarse

    settled = [r for r in rows if str(r.get("status") or "").lower() == "settled"]
    with_clv = sum(1 for r in settled if r.get("clv_pct") is not None)
    without_clv = len(settled) - with_clv

    status = "dirty" if (n_syn or n_mal or n_dup) else "clean"
    return {
        "status": status,
        "total_rows": len(rows),
        "synthetic": {
            "count": n_syn,
            "label": "rows whose sport or bet_id starts with 'test_'",
        },
        "malformed": {
            "count": n_mal,
            "label": (
                "rows with game_id shorter than %d chars or missing sport|status|side"
                % _MIN_GAME_ID_LEN
            ),
        },
        "duplicates": {
            "count": n_dup,
            "label": (
                "genuine collisions on canonical identity (bet_id|status else "
                "edge_key|status else coarse key); coarse matches with distinct "
                "canonical identity (recurring matchup) are NOT counted"
                if n_dup_canonical is not None else
                "extra copies beyond first per (game|market|side|venue|date|status) "
                "key (coarse fallback -- canonical index unavailable)"
            ),
        },
        "honest_clv": {
            "settled_with_clv": with_clv,
            "settled_without_clv": without_clv,
            "no_close_label": (
                "INSUFFICIENT_DATA: closing line not yet captured for %d settled row(s)"
                % without_clv
                if without_clv > 0
                else "all settled rows have a closing-line CLV value"
            ),
        },
        "honest_note": (
            "calibration not edge; read-only scan; no $ field; "
            "status=dirty when synthetic or malformed rows are present; "
            "settled-without-clv is INSUFFICIENT_DATA; NEVER green when synthetic/malformed exist"
        ),
    }


def scan_assert(path: Optional[Path] = None) -> None:
    """CI assertion: raises AssertionError when ledger is dirty. READ-ONLY.

    Passes silently on 'clean'. Raises on 'dirty' or 'INSUFFICIENT_DATA'.
    Never mutates the ledger. Safe to call from automated checks.
    """
    p = Path(path) if path is not None else _default_ledger()
    report = scan_ledger(p)
    status = report["status"]
    if status == "INSUFFICIENT_DATA":
        raise AssertionError(
            "scan_assert: INSUFFICIENT_DATA at %s -- cannot confirm clean" % p
        )
    if status == "dirty":
        syn = report["synthetic"]["count"]
        mal = report["malformed"]["count"]
        dup = report["duplicates"]["count"]
        raise AssertionError(
            "scan_assert: DIRTY at %s -- synthetic=%d malformed=%d duplicates=%d; "
            "run purge_ledger --purge (CLI only) to remove synthetic/malformed rows; "
            "duplicate rows must be resolved manually" % (p, syn, mal, dup)
        )


def purge_ledger(path: Optional[Path] = None, *, dry_run: bool = True) -> Dict[str, Any]:
    """Drop synthetic and malformed rows. EXPLICIT CLI ONLY -- never auto-run.

    dry_run=True (default): preview; no file changes.
    dry_run=False: backs up original to <path>.bak then overwrites with kept rows.
    Duplicate rows are NOT purged (ambiguous -- resolve manually).
    No $ / pnl / profit key in output.
    """
    p = Path(path) if path is not None else _default_ledger()
    if not p.exists() or p.stat().st_size == 0:
        return {
            "status": "INSUFFICIENT_DATA", "dry_run": dry_run,
            "rows_before": 0, "rows_removed": 0, "rows_kept": 0,
            "backup_path": None,
            "honest_note": "calibration not edge; no $ field; ledger missing or empty",
        }

    rows = _raw_load(p)
    kept = [r for r in rows if not (_is_synthetic(r) or _is_malformed(r))]
    removed = len(rows) - len(kept)

    backup_path: Optional[str] = None
    if not dry_run and removed > 0:
        bak = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, bak)
        backup_path = str(bak)
        with p.open("w", encoding="utf-8") as fh:
            for r in kept:
                fh.write(json.dumps(r, ensure_ascii=True) + "\n")

    return {
        "status": "dry_run" if dry_run else "purged",
        "dry_run": dry_run,
        "rows_before": len(rows),
        "rows_removed": removed,
        "rows_kept": len(kept),
        "backup_path": backup_path,
        "honest_note": (
            "calibration not edge; no $ field; "
            + ("preview only -- pass dry_run=False to apply"
               if dry_run else
               "synthetic+malformed removed; backup at %s; "
               "duplicate rows NOT auto-purged" % backup_path)
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="CLV ledger sanity: scan (default) or purge synthetic/malformed rows."
    )
    ap.add_argument("--ledger", default=None, help="override ledger path")
    ap.add_argument(
        "--purge", action="store_true", default=False,
        help="Remove synthetic+malformed rows (backs up first). NEVER pass from automated jobs.",
    )
    ap.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Preview purge without writing (default when --purge absent).",
    )
    a = ap.parse_args(list(argv) if argv is not None else None)
    ledger = Path(a.ledger) if a.ledger else None

    result = purge_ledger(ledger, dry_run=a.dry_run) if a.purge else scan_ledger(ledger)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("status") in ("clean", "dry_run", "purged") else 1


__all__ = ["scan_ledger", "scan_assert", "purge_ledger"]

if __name__ == "__main__":
    raise SystemExit(_main())
