"""scripts.platformkit.improve.ledger_reconcile -- daemon-vs-graded reconciliation.

SI-11 parity check: every SHIP row in proposals.jsonl must have a matching graded
row in improve_ledger_segmented.jsonl (keyed by candidate_id / cycle). A SHIP row
with no matching graded row is an orphan_ship. A graded row with no matching daemon
entry is an orphan_grade. Either condition -> verdict NO_CANDIDATE (do-no-harm).
Missing or empty inputs -> INSUFFICIENT_DATA (stale-never-green; never raises;
no $/roi/pnl/profit key in any output). calibration, not edge.

Join key: daemon proposals use (name, ts). Graded rows use (full_market, ts) --
FULL market string, not the sport prefix, so "nba:moneyline" and "nba:pts" at the
same ts produce distinct keys and cannot collide (BE-R5-5 bug fix).

Usage:
  from scripts.platformkit.improve.ledger_reconcile import reconcile
  result = reconcile()
  result = reconcile(proposals_path, graded_path)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths (mirrors selfimprove_daemon defaults)
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[3]
_IMPROVE_DIR = _REPO / "data" / "cache" / "improve"
DEFAULT_PROPOSALS = _IMPROVE_DIR / "proposals.jsonl"

_FRONTEND_DIR = _REPO / "data" / "frontend"
DEFAULT_GRADED = _FRONTEND_DIR / "improve_ledger_segmented.jsonl"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALIBRATION_NOTE = (
    "calibration != edge: a SHIP in proposals is a recalibration improvement, "
    "not a profit or market edge"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

# Verdict tokens
VERDICT_CLEAN = "CLEAN"
VERDICT_NO_CANDIDATE = "NO_CANDIDATE"
VERDICT_INSUFFICIENT = "INSUFFICIENT_DATA"


# -- Internal helpers --------------------------------------------------------


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
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


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any) -> None:
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.search(k):
            raise ValueError("Banned key '%s' in reconcile output" % k)


def _ship_rows(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in proposals if str(r.get("decision", "")).upper() == "SHIP"]


def _daemon_key(row: Dict[str, Any]) -> str:
    """Stable key for a daemon proposal row: candidate_id or name:ts."""
    cid = str(row.get("candidate_id", "")).strip()
    if cid:
        return cid
    name = str(row.get("name", "")).strip().lower()
    ts = str(row.get("ts", "")).strip()
    return "%s:%s" % (name, ts)


def _daemon_name(row: Dict[str, Any]) -> str:
    cid = str(row.get("candidate_id", "")).strip()
    return cid or str(row.get("name", "")).strip().lower()


def _graded_full_key(row: Dict[str, Any]) -> str:
    """Collision-free key for a graded row: candidate_id or full_market:ts.

    Uses the FULL market string so "nba:moneyline" and "nba:pts" at the same ts
    produce distinct keys and cannot overwrite each other in the index.
    """
    cid = str(row.get("candidate_id", "")).strip()
    if cid:
        return cid
    market = str(row.get("market", "")).strip().lower()
    ts = str(row.get("ts", "")).strip()
    return "%s:%s" % (market, ts)


def _graded_sport_prefix(row: Dict[str, Any]) -> str:
    """Return just the sport prefix of the market (e.g. 'nba' from 'nba:moneyline')."""
    cid = str(row.get("candidate_id", "")).strip()
    if cid:
        return cid
    market = str(row.get("market", "")).strip().lower()
    return market.split(":")[0] if ":" in market else market


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    proposals_path: Optional[Path] = None,
    graded_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reconcile SHIP rows in proposals.jsonl against improve_ledger_segmented.jsonl.

    Join key: daemon side = candidate_id or (name, ts). Graded side = candidate_id
    or (full_market, ts). Daemon "nba" at ts T matches the first unconsumed graded
    row whose sport prefix == "nba" at ts T. Extra same-prefix graded rows at T
    become orphan_grade entries. Never raises. No $ key.
    """
    pp = Path(proposals_path) if proposals_path is not None else DEFAULT_PROPOSALS
    gp = Path(graded_path) if graded_path is not None else DEFAULT_GRADED

    proposals = _read_jsonl(pp)
    graded = _read_jsonl(gp)

    ships = _ship_rows(proposals)
    n_ship = len(ships)
    n_graded = len(graded)

    # INSUFFICIENT_DATA guards
    if not proposals:
        res = _insufficient("proposals file missing or empty", 0, n_graded)
        _assert_no_banned_keys(res)
        return res
    if n_ship == 0:
        res = _insufficient("no SHIP rows in proposals", 0, n_graded)
        _assert_no_banned_keys(res)
        return res
    if not graded:
        res = _insufficient("graded ledger missing or empty", n_ship, 0)
        _assert_no_banned_keys(res)
        return res

    # FULL key (collision-free) + prefix-ts slot index for daemon-name matching.
    graded_by_full_key: Dict[str, Dict[str, Any]] = {}
    graded_by_prefix_ts: Dict[tuple, List[Dict[str, Any]]] = {}
    for gr in graded:
        full_key = _graded_full_key(gr)
        graded_by_full_key[full_key] = gr
        prefix = _graded_sport_prefix(gr)
        ts = str(gr.get("ts", "")).strip()
        slot = (prefix, ts)
        graded_by_prefix_ts.setdefault(slot, []).append(gr)

    consumed_graded_keys: set = set()
    orphan_ships: List[Dict[str, Any]] = []
    matched: List[Dict[str, Any]] = []

    for ship in ships:
        daemon_key = _daemon_key(ship)
        ship_name = _daemon_name(ship)
        ship_ts = str(ship.get("ts", "")).strip()

        # 1. Exact full-key match (candidate_id on both sides).
        if daemon_key in graded_by_full_key:
            gr = graded_by_full_key[daemon_key]
            full_key = _graded_full_key(gr)
            if full_key not in consumed_graded_keys:
                consumed_graded_keys.add(full_key)
                matched.append({
                    "ship_name": ship_name,
                    "ship_ts": ship_ts,
                    "graded_market": gr.get("market"),
                    "graded_ts": gr.get("ts"),
                    "graded_status": gr.get("status"),
                })
                continue

        # 2. Sport-prefix + ts fallback: match the first unconsumed graded row
        #    whose prefix == ship_name at the same ts.
        slot = (ship_name, ship_ts)
        candidates = graded_by_prefix_ts.get(slot, [])
        matched_gr: Optional[Dict[str, Any]] = None
        for gr_candidate in candidates:
            full_key = _graded_full_key(gr_candidate)
            if full_key not in consumed_graded_keys:
                matched_gr = gr_candidate
                consumed_graded_keys.add(full_key)
                break

        if matched_gr is not None:
            matched.append({
                "ship_name": ship_name,
                "ship_ts": ship_ts,
                "graded_market": matched_gr.get("market"),
                "graded_ts": matched_gr.get("ts"),
                "graded_status": matched_gr.get("status"),
            })
        else:
            orphan_ships.append({
                "ship_name": ship_name,
                "ship_ts": ship_ts,
                "ship_version": ship.get("shipped_version"),
                "reason": (
                    "daemon SHIP row has no matching graded row in "
                    "improve_ledger_segmented -- ratchet must not auto-promote"
                ),
            })

    # Orphan grades: graded rows not consumed by any daemon SHIP.
    orphan_grades: List[Dict[str, Any]] = []
    for gr in graded:
        full_key = _graded_full_key(gr)
        if full_key not in consumed_graded_keys:
            orphan_grades.append({
                "graded_market": gr.get("market"),
                "graded_ts": gr.get("ts"),
                "graded_status": gr.get("status"),
                "reason": (
                    "graded row has no matching daemon SHIP entry -- "
                    "promoted without a daemon proposal; NO_CANDIDATE"
                ),
            })

    n_matched = len(matched)
    n_orphan_ship = len(orphan_ships)
    n_orphan_grade = len(orphan_grades)

    is_clean = (n_orphan_ship == 0 and n_orphan_grade == 0
                and n_matched == n_ship)
    if is_clean:
        verdict = VERDICT_CLEAN
    else:
        verdict = VERDICT_NO_CANDIDATE

    result: Dict[str, Any] = {
        "verdict": verdict,
        "n_ship_rows": n_ship,
        "n_graded_rows": n_graded,
        "n_matched": n_matched,
        "n_orphan_ship": n_orphan_ship,
        "n_orphan_grade": n_orphan_grade,
        "orphan_ships": orphan_ships,
        "orphan_grades": orphan_grades,
        "matched": matched,
        "clean": is_clean,
        "note": CALIBRATION_NOTE,
    }
    _assert_no_banned_keys(result)
    return result


def _insufficient(reason: str, n_ship: int, n_graded: int) -> Dict[str, Any]:
    return {
        "verdict": VERDICT_INSUFFICIENT,
        "n_ship_rows": n_ship,
        "n_graded_rows": n_graded,
        "n_matched": 0,
        "n_orphan_ship": 0,
        "n_orphan_grade": 0,
        "orphan_ships": [],
        "orphan_grades": [],
        "matched": [],
        "clean": False,
        "reason": reason,
        "note": CALIBRATION_NOTE,
    }


__all__ = [
    "reconcile",
    "DEFAULT_PROPOSALS",
    "DEFAULT_GRADED",
    "CALIBRATION_NOTE",
    "VERDICT_CLEAN",
    "VERDICT_NO_CANDIDATE",
    "VERDICT_INSUFFICIENT",
]
