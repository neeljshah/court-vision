"""scripts.platformkit.clv_ledger_betid_backfill -- normalize-and-stamp self-heal.

PURPOSE
-------
The CLV ledger has rows written by older code paths that pre-date the bet_id field
(68 of 95 rows at the time of writing). Without a bet_id the governance concurrency
gate falls back to SHA-1 of the full row content, which means:

  1. An open row and its settled twin look like DIFFERENT rows (SHA-1 differs) --
     so no false dup there, but there is also no durable logical identity linking
     the two.
  2. Two truly identical open rows written by a retry/replay (same sport/matchup/
     side/book/ts) hash to the same SHA-1 and DO collide -- but only if EVERY field
     is identical, which is fragile.
  3. run_governance._run_concurrency cannot use the status-aware <bet_id|status>
     key formula for these rows, so the gate state depends entirely on SHA-1
     hash coincidences rather than logical bet identity.

This module provides:

  * derive_bet_id(row) -- derives a durable bet_id from natural fields (mirrors
    scripts.platformkit.clv_ledger.bet_id() exactly).

  * status_aware_key(row) -- returns <derived_or_stored_bet_id>|<status>, the
    same formula concurrency_guard._row_key() uses for rows that already have a
    bet_id. This gives every row a stable, status-aware identity regardless of
    whether it was written with or without an explicit bet_id.

  * run_report(path) -- READ-ONLY scan. Derives keys for all rows; detects:
      - rows missing bet_id (candidates for stamping),
      - open/settled twin pairs (same bet_id, different status -- NOT dups),
      - true replays (same bet_id AND same status -- genuine dups).
    Returns a plain dict report with no $/pnl/roi fields.

  * stamp_missing(rows) -- PURE function (no I/O). Returns a NEW list with
    bet_id stamped onto every row that lacked it. Caller controls persistence.
    No $/pnl/roi/dollar fields in the stamped record.

INVARIANTS
----------
* Read-only by default. stamp_missing() is pure; it NEVER writes to disk.
* Caller controls whether and how to persist stamped rows.
* No $/pnl/roi/profit/dollar/bankroll key introduced or emitted in the report.
* pnl already present in settled rows is NOT stripped (those rows are ledger
  truth; this tool does not sanitize existing rows).
* Calibration, not edge. Units not $.
* <=300 LOC; ASCII; stdlib only; no secrets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"

# Keys that must NOT appear in the report output (honesty gate).
_BANNED_REPORT_KEYS = frozenset({
    "dollar", "roi", "profit", "usd", "bankroll",
    "stake_usd", "pnl_units", "profit_units", "roi_units",
})


# ---------------------------------------------------------------------------
# Core key derivation
# ---------------------------------------------------------------------------

def derive_bet_id(row: Dict[str, Any]) -> str:
    """Derive a durable bet_id from natural fields when row lacks an explicit one.

    Mirrors scripts.platformkit.clv_ledger.bet_id() exactly:
      sport | (event_id or matchup) | (market or market_type or 'moneyline')
           | side | (taken_book or book) | game_date

    game_date is row['game_date'] if present, else the UTC date prefix of row['ts'].
    This is IDENTICAL to what new code writes into bet_id, so stamped rows will
    hash-collide with any future row written by the new code for the same logical bet.
    """
    anchor = str(row.get("event_id") or row.get("matchup") or "")
    market = str(row.get("market") or row.get("market_type") or "moneyline")
    book = str(row.get("taken_book") or row.get("book") or "")
    ts = str(row.get("ts") or "")
    gd = str(row.get("game_date") or "")
    game_date = gd[:10] if gd else ts[:10]
    sport = str(row.get("sport") or "")
    side = str(row.get("side") or "")
    return "|".join([sport, anchor, market, side, book, game_date])


def status_aware_key(row: Dict[str, Any]) -> str:
    """Stable status-aware unique key matching concurrency_guard._row_key.

    For rows WITH a bet_id: returns  <bet_id>|<status>
    For rows WITHOUT a bet_id: derives the bet_id from natural fields first,
    then returns  <derived_bet_id>|<status>

    This guarantees that an open row and its settled twin (same logical bet,
    different status) produce DISTINCT keys, while a true replay (same logical
    bet AND same status) still collides -- exactly the semantics concurrency_guard
    expects.

    Never raises. Missing status is normalised to 'open'.
    """
    status = str(row.get("status") or "open").strip().lower()
    bid = row.get("bet_id")
    if bid is None:
        bid = derive_bet_id(row)
    return "%s|%s" % (str(bid), status)


# ---------------------------------------------------------------------------
# Report (read-only)
# ---------------------------------------------------------------------------

def run_report(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only scan of the CLV ledger. Returns a report dict; never mutates.

    The report carries:
      n_rows            -- total rows in the ledger
      n_missing_bet_id  -- rows that lack a bet_id field
      n_open_settled_twins -- (bet_id, distinct-statuses) pairs (NOT dups)
      true_dups         -- list of status-aware keys that appear more than once
      n_true_dups       -- len(true_dups)
      missing_bet_id_rows -- list of {lineno, derived_bet_id, status}
      status            -- 'CLEAN' | 'DUPS_FOUND' | 'UNAVAILABLE'
      ledger_path       -- str

    No $/pnl/roi/profit key is ever present in the report. Calibration not edge.
    """
    ledger = Path(path) if path is not None else _DEFAULT_LEDGER

    base: Dict[str, Any] = {
        "status": "UNAVAILABLE",
        "n_rows": 0,
        "n_missing_bet_id": 0,
        "n_open_settled_twins": 0,
        "true_dups": [],
        "n_true_dups": 0,
        "missing_bet_id_rows": [],
        "ledger_path": str(ledger),
        "error": None,
    }

    if not ledger.exists():
        base["error"] = "ledger not found: %s" % ledger
        return base

    try:
        numbered_rows = _load_rows(ledger)
    except Exception as exc:  # noqa: BLE001
        base["error"] = "read error: %s" % exc
        return base

    base["n_rows"] = len(numbered_rows)

    # --- scan: derive keys + tally ---
    key_lines: Dict[str, List[int]] = {}   # status_aware_key -> [lineno, ...]
    bet_id_statuses: Dict[str, set] = {}   # derived_bet_id -> {statuses seen}
    missing_rows: List[Dict[str, Any]] = []

    for lineno, row in numbered_rows:
        bid_stored = row.get("bet_id")
        bid = str(bid_stored) if bid_stored is not None else derive_bet_id(row)
        key = status_aware_key(row)
        status = str(row.get("status") or "open").strip().lower()

        if key not in key_lines:
            key_lines[key] = [lineno]
        else:
            key_lines[key].append(lineno)

        if bid not in bet_id_statuses:
            bet_id_statuses[bid] = set()
        bet_id_statuses[bid].add(status)

        if bid_stored is None:
            missing_rows.append({
                "lineno": lineno,
                "derived_bet_id": bid,
                "status": status,
            })

    # true dups: same status_aware_key appears more than once
    true_dup_keys = sorted(k for k, lines in key_lines.items() if len(lines) > 1)
    # open/settled twins: same bet_id with > 1 distinct status (NOT a dup)
    twin_count = sum(
        1 for statuses in bet_id_statuses.values() if len(statuses) > 1
    )

    base["n_missing_bet_id"] = len(missing_rows)
    base["n_open_settled_twins"] = twin_count
    base["true_dups"] = true_dup_keys
    base["n_true_dups"] = len(true_dup_keys)
    base["missing_bet_id_rows"] = missing_rows
    base["status"] = "DUPS_FOUND" if true_dup_keys else "CLEAN"

    # Belt-and-suspenders: remove any banned key from the report dict
    for bk in _BANNED_REPORT_KEYS:
        base.pop(bk, None)

    return base


# ---------------------------------------------------------------------------
# Pure stamp function (no I/O)
# ---------------------------------------------------------------------------

def stamp_missing(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Return a NEW list of rows with bet_id stamped onto each row that lacks one.

    This is a PURE function: it never reads or writes any file. The caller
    controls what to do with the result (write back, diff, inspect, etc.).

    Rules:
      - Rows that already have bet_id are returned unchanged (shallow copy).
      - Rows missing bet_id get bet_id = derive_bet_id(row) added.
      - No $/pnl/roi/profit key is introduced. Existing pnl etc. in the row
        are NOT touched (they are ledger truth; this function does not sanitize).

    Returns (stamped_rows, n_stamped) where n_stamped is the count of rows
    that received a derived bet_id.
    """
    out: List[Dict[str, Any]] = []
    n_stamped = 0
    for row in rows:
        if row.get("bet_id") is not None:
            out.append(dict(row))
        else:
            stamped = dict(row)
            stamped["bet_id"] = derive_bet_id(row)
            out.append(stamped)
            n_stamped += 1
    return out, n_stamped


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_rows(ledger: Path) -> List[Tuple[int, Dict[str, Any]]]:
    """Load valid JSONL rows; skip blank/torn lines. Returns [(lineno, row), ...]."""
    out: List[Tuple[int, Dict[str, Any]]] = []
    with ledger.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    out.append((lineno, obj))
            except json.JSONDecodeError:
                pass
    return out


# ---------------------------------------------------------------------------
# CLI (report mode only -- never auto-mutates)
# ---------------------------------------------------------------------------

def _cli() -> None:
    """Print a plain-ASCII report to stdout. Never writes the ledger."""
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    report = run_report(path)

    print("=== CLV LEDGER BET-ID BACKFILL REPORT ===")
    print("ledger   : %s" % report["ledger_path"])
    print("status   : %s" % report["status"])
    print("total rows       : %d" % report["n_rows"])
    print("missing bet_id   : %d" % report["n_missing_bet_id"])
    print("open/settled twins (not dups): %d" % report["n_open_settled_twins"])
    print("true dups (same bet_id+status): %d" % report["n_true_dups"])
    if report["true_dups"]:
        print("dup keys:")
        for k in report["true_dups"]:
            print("  %s" % k)
    if report.get("error"):
        print("error    : %s" % report["error"])
    print("==========================================")


if __name__ == "__main__":  # pragma: no cover
    _cli()


__all__ = [
    "derive_bet_id",
    "status_aware_key",
    "run_report",
    "stamp_missing",
]
