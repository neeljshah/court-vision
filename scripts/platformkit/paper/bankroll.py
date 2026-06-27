"""scripts.platformkit.paper.bankroll -- a UNITS-ONLY paper bankroll model.

The everyday paper bankroll the user asked for, measured in UNITS (never dollars).
A starting balance (default 100.0 units) is persisted to
``data/frontend/paper_bankroll.json`` and the current balance is derived by applying
every settled ``unit_result`` (the pure unit count grade_paper already computes:
win -> +(dec-1)*units, loss -> -units, push -> 0.0, void/undecided -> skipped).

Honesty rails:
  * UNITS ONLY -- no dollar / pnl / roi / profit / bankroll($) key is ever written.
    BANNED_KEYS are stripped before persisting (belt-and-suspenders).
  * Real money stays DEFAULT-DENY; edge is NEVER claimed (honest_note states this).
  * Reading a balance never fabricates a result; only graded settled rows move it.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_bankroll.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

_HERE = Path(__file__).resolve().parent
# scripts/platformkit/paper/ -> repo root is parents[3].
DEFAULT_BANKROLL = _HERE.parents[2] / "data" / "frontend" / "paper_bankroll.json"

DEFAULT_START_UNITS = 100.0

_HONEST_NOTE = (
    "Paper bankroll in UNITS only (never $). Real money stays default-DENY; "
    "executed=False on every bet. No edge is claimed -- a positive curve here is "
    "a paper track record, not a realized profit, and CLV is the honest yardstick."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_banned(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with every banned dollar/pnl/roi key removed."""
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


def default_config(start_units: float = DEFAULT_START_UNITS) -> Dict[str, Any]:
    """A fresh bankroll config dict: start == current, units only, edge_claimed False."""
    su = float(start_units)
    return {
        "start_units": su,
        "current_units": su,
        "updated_at": _now_iso(),
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "executed": False,
    }


def read_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the persisted bankroll config; missing/corrupt file -> a fresh default.

    The returned dict is always sanitised (banned keys stripped) so a stale on-disk
    dollar field can never leak back into the model.
    """
    target = Path(path) if path is not None else DEFAULT_BANKROLL
    if not target.exists():
        return default_config()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config()
    if not isinstance(raw, dict):
        return default_config()
    cfg = _strip_banned(raw)
    # Re-assert required fields so a partial file is always usable.
    if "start_units" not in cfg:
        cfg["start_units"] = DEFAULT_START_UNITS
    cfg["start_units"] = float(cfg["start_units"])
    if "current_units" not in cfg:
        cfg["current_units"] = cfg["start_units"]
    cfg["current_units"] = float(cfg["current_units"])
    cfg["honest_note"] = _HONEST_NOTE
    cfg["edge_claimed"] = False
    cfg["executed"] = False
    return cfg


def write_config(cfg: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    """Persist *cfg* to the bankroll JSON (units only); returns the written dict.

    BANNED_KEYS are stripped first; the file is written atomically (tmp + replace).
    """
    target = Path(path) if path is not None else DEFAULT_BANKROLL
    clean = _strip_banned(cfg)
    clean["honest_note"] = _HONEST_NOTE
    clean["edge_claimed"] = False
    clean["executed"] = False
    clean["updated_at"] = _now_iso()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(target)
    return clean


def init_bankroll(
    start_units: float = DEFAULT_START_UNITS, path: Optional[Path] = None
) -> Dict[str, Any]:
    """Initialise (or RESET) the bankroll to *start_units*; persist and return it."""
    return write_config(default_config(start_units), path)


def _iter_unit_results(settled_rows: Iterable[Dict[str, Any]]) -> Iterable[float]:
    """Yield the float unit_result of each settled row that actually has one.

    None (void/undecided) and missing values are skipped -- never coerced to 0 in a
    way that could hide a non-result, and never fabricated.
    """
    for r in settled_rows:
        ur = r.get("unit_result")
        if ur is None:
            continue
        try:
            yield float(ur)
        except (TypeError, ValueError):
            continue


def apply_settled(
    settled_rows: Iterable[Dict[str, Any]],
    *,
    start_units: Optional[float] = None,
    path: Optional[Path] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Recompute current balance = start_units + sum(unit_result over settled rows).

    *start_units* defaults to the persisted config's start (or DEFAULT_START_UNITS).
    Recomputed from scratch each call (idempotent -- never double-counts). When
    *persist* is True the new current_units is written back to the JSON file.
    """
    cfg = read_config(path)
    su = float(start_units) if start_units is not None else float(cfg["start_units"])
    total = sum(_iter_unit_results(settled_rows))
    cfg["start_units"] = su
    cfg["current_units"] = round(su + total, 6)
    cfg["net_units"] = round(total, 6)
    if persist:
        return write_config(cfg, path)
    cfg["honest_note"] = _HONEST_NOTE
    cfg["edge_claimed"] = False
    cfg["executed"] = False
    return cfg


def current_units(path: Optional[Path] = None) -> float:
    """Read the persisted current balance in units (no recompute, no I/O on rows)."""
    return float(read_config(path)["current_units"])


__all__ = [
    "DEFAULT_BANKROLL", "DEFAULT_START_UNITS",
    "default_config", "read_config", "write_config", "init_bankroll",
    "apply_settled", "current_units",
]
