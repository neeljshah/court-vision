"""scripts.platformkit.paper.bankroll_reset -- reversible paper-bankroll reset.

Resets the PAPER bankroll to a clean ``start_units`` (default 100u) in a way that
STICKS: the m1_bankroll daemon reconciles the live bankroll to the settled rows in
``clv_ledger.jsonl`` every tick, so a bare re-init is recomputed straight back to the
old curve.  This archives the canonical settled-ledger + display files into a
timestamped ``_ledger_archive/<ts>_reset/`` folder (REVERSIBLE -- nothing deleted),
then re-inits the bankroll, so the next reconcile sees an empty ledger -> 100u.

PAPER / UNITS ONLY.  Never touches real money (stays default-DENY, executed=False),
flips NO flag, writes NO data/registry/, claims NO edge.  The archived CLV history
(the honest yardstick + recalibrator corpus) is preserved and ``--restore`` brings it
back.  ASCII only; local-only.

CLI:
    python -m scripts.platformkit.paper.bankroll_reset            # reset to 100u
    python -m scripts.platformkit.paper.bankroll_reset --units 250
    python -m scripts.platformkit.paper.bankroll_reset --restore <ts>_reset
    python -m scripts.platformkit.paper.bankroll_reset --list
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from scripts.platformkit.paper import bankroll as _bank

_REPO = Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "data" / "frontend"
_ARCHIVE = _FRONTEND / "_ledger_archive"

# The canonical settled-ledger + display files the daemon reconciles / the UI reads.
_RESET_FILES = [
    "clv_ledger.jsonl",        # the settled-bet ledger reconcile() reads (drives bankroll)
    "paper_bankroll.json",     # the live bankroll doc
    "paper_pnl_series.json",   # SERIES_PATH (curve the UI plots)
    "paper_today.json",        # TODAY_PATH (today board)
    "grade_summary.json",      # grade rollup
]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def reset(start_units: float = 100.0, *, frontend: Optional[Path] = None,
          archive_root: Optional[Path] = None) -> Dict:
    """Archive the settled-ledger + display files, then re-init the bankroll.

    Returns a summary {archive_dir, archived[], start_units, current_units}.  The
    daemon's next tick reconciles to the now-empty ledger -> current == start_units.
    """
    fe = Path(frontend) if frontend is not None else _FRONTEND
    ar = Path(archive_root) if archive_root is not None else _ARCHIVE
    dest = ar / ("%s_reset" % _ts())
    dest.mkdir(parents=True, exist_ok=True)
    archived: List[str] = []
    for name in _RESET_FILES:
        src = fe / name
        if src.exists():
            shutil.move(str(src), str(dest / name))
            archived.append(name)
    # Re-init the bankroll doc to a clean slate (empty ledger -> reconcile holds 100u).
    cfg = _bank.init_bankroll(float(start_units), path=fe / "paper_bankroll.json")
    return {
        "archive_dir": str(dest), "archived": archived,
        "start_units": cfg["start_units"], "current_units": cfg["current_units"],
    }


def list_archives(*, archive_root: Optional[Path] = None) -> List[str]:
    ar = Path(archive_root) if archive_root is not None else _ARCHIVE
    if not ar.exists():
        return []
    return sorted(p.name for p in ar.iterdir() if p.is_dir() and p.name.endswith("_reset"))


def restore(name: str, *, frontend: Optional[Path] = None,
            archive_root: Optional[Path] = None) -> Dict:
    """Restore a prior reset archive (reverse the reset).  Copies files back."""
    fe = Path(frontend) if frontend is not None else _FRONTEND
    ar = Path(archive_root) if archive_root is not None else _ARCHIVE
    src_dir = ar / name
    if not src_dir.is_dir():
        raise FileNotFoundError("no such archive: %s" % src_dir)
    restored: List[str] = []
    for f in src_dir.iterdir():
        if f.is_file():
            shutil.copy2(str(f), str(fe / f.name))
            restored.append(f.name)
    return {"restored_from": str(src_dir), "restored": restored}


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Reversible PAPER bankroll reset (units only; no real money).")
    p.add_argument("--units", type=float, default=100.0,
                   help="Clean start units (default 100).")
    p.add_argument("--restore", type=str, default=None,
                   help="Restore a prior <ts>_reset archive instead of resetting.")
    p.add_argument("--list", action="store_true", help="List reset archives.")
    a = p.parse_args()
    if a.list:
        for n in list_archives():
            print(n)
        return 0
    if a.restore:
        r = restore(a.restore)
        print("RESTORED from %s (%d files)" % (r["restored_from"], len(r["restored"])))
        return 0
    out = reset(a.units)
    print("PAPER BANKROLL RESET (reversible; units only, no real money)")
    print("  archived %d files -> %s" % (len(out["archived"]), out["archive_dir"]))
    print("  start_units=%.1f  current_units=%.1f" %
          (out["start_units"], out["current_units"]))
    print("  the m1_bankroll daemon will reconcile to the empty ledger on next tick.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
