"""scripts.platformkit.clv_ledger_migrate -- one-shot UNITS-ONLY ledger migration.

The canonical CLV ledger (data/frontend/clv_ledger.jsonl) historically stored a
DOLLAR ``stake`` (and graders appended a dollar ``pnl``). The binding rail is
UNITS ONLY: NO dollar / bankroll / pnl / roi field anywhere in the source of
truth. This module rewrites every existing row to units:

  * ``stake``        -> ``stake_units`` (the magnitude is REINTERPRETED as a unit
                        count -- we never knew/stored a bankroll, so this is not
                        money any more; it is simply relabelled),
  * ``pnl`` / ``total_pnl`` / ``total_stake`` / ``paper_roi`` / ``bankroll`` /
    ``profit`` / ``dollars`` -> DROPPED,
  * a durable ``bet_id`` (independent of the write ts) is back-filled.

The rewrite is IDEMPOTENT (a clean ledger rewrites to itself), ATOMIC (tmp file +
os.replace), and BACKS UP the original to ``<ledger>.bak`` first. Public function
never raises -- a migration must never crash the box.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
never claims an edge; never writes a dollar field.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/test_clv_ledger_units.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id, load_ledger

# Dollar / bankroll / pnl / roi keys that must NEVER live in the canonical record.
BANNED_KEYS = (
    "stake", "pnl", "total_pnl", "total_stake", "paper_roi", "roi",
    "bankroll", "profit", "dollars",
)


def to_units_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a UNITS-ONLY copy of *row*.

    Relabels ``stake`` -> ``stake_units`` (when stake_units is absent), drops every
    banned dollar key, and back-fills a durable ``bet_id``. Idempotent: a row that
    is already clean returns with identical content (modulo a back-filled bet_id).
    """
    out = dict(row)
    if "stake" in out and "stake_units" not in out:
        val = out.get("stake")
        if val is not None:
            try:
                out["stake_units"] = float(val)
            except (TypeError, ValueError):
                out["stake_units"] = 1.0
    for banned in BANNED_KEYS:
        out.pop(banned, None)
    if not out.get("bet_id"):
        out["bet_id"] = bet_id(out)
    return out


def row_has_dollars(row: Dict[str, Any]) -> bool:
    """True if *row* still carries any banned dollar/bankroll/pnl/roi key."""
    return any(k in row for k in BANNED_KEYS)


def migrate_ledger_to_units(path: Optional[Path] = None) -> Dict[str, Any]:
    """Rewrite every ledger row to UNITS ONLY. Atomic + idempotent + backed-up.

    Returns a status dict: {status, rows, changed, path}. ``status`` is "ok" on a
    successful (or no-op) migration, "no_file" when the ledger does not exist, or
    "error: <Type>" on any failure (the original file is left untouched on error).
    Never raises.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    out: Dict[str, Any] = {"status": "ok", "rows": 0, "changed": 0,
                           "path": str(target)}
    if not target.exists():
        out["status"] = "no_file"
        return out
    try:
        rows = load_ledger(target)
        migrated = [to_units_row(r) for r in rows]
        out["rows"] = len(rows)
        out["changed"] = sum(1 for a, b in zip(rows, migrated) if a != b)
        # Backup the original (overwrite any prior .bak so re-runs stay clean).
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        # Atomic rewrite: tmp file in the same dir, then os.replace.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=target.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for r in migrated:
                    fh.write(json.dumps(r, default=str) + "\n")
            os.replace(tmp_name, str(target))
        finally:
            if Path(tmp_name).exists():
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 -- a migration must never crash the box
        out["status"] = "error: %s" % type(exc).__name__
    return out


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Rewrite the CLV ledger to UNITS ONLY (idempotent, atomic).")
    ap.add_argument("--ledger", default=None, help="override ledger path")
    a = ap.parse_args(list(argv) if argv is not None else None)
    res = migrate_ledger_to_units(Path(a.ledger) if a.ledger else None)
    print(json.dumps(res, default=str))
    status = str(res.get("status", ""))
    return 0 if status in ("ok", "no_file") else 1


__all__ = [
    "BANNED_KEYS",
    "to_units_row",
    "row_has_dollars",
    "migrate_ledger_to_units",
]


if __name__ == "__main__":
    raise SystemExit(_main())
