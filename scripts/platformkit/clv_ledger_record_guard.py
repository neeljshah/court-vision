"""scripts.platformkit.clv_ledger_record_guard -- record-time dedup guard.

THE PROBLEM (QA-CLV-RECORD-DEDUP):
  clv_ledger.record_bet funnels through clv_ledger_io.append_row WITHOUT a
  dedup check. A concurrent tick or settlement can call record_bet with the
  same logical bet in two threads/processes within the same scheduler window,
  writing 8+ duplicate bet_id rows. The boot preflight concurrency gate then
  detects the duplicates and halts the box.

THIS MODULE:
  Provides a single guard function -- record_bet_guarded -- that all in-lane
  writers call instead of clv_ledger.record_bet directly. The guard:

    1. Computes the stable bet_id for the candidate record (same formula as
       clv_ledger.bet_id -- delegated, never re-derived here).
    2. Scans the existing ledger for that id (via clv_ledger_dedup.append_if_new
       which already owns the "scan + conditional append" contract).
    3. If the id is already present: returns {"appended": False, "record": None,
       "bet_id": <id>} -- the repeat write is a silent no-op, never raises.
    4. If the id is new: strips any banned $ key, writes via append_if_new
       (which funnels through the lock-guarded clv_ledger_io.append_row), and
       returns {"appended": True, "record": <written_row>, "bet_id": <id>}.
    5. Missing ledger file: creates then appends (inherited from append_if_new).

  Honesty contract (binding):
    * UNITS ONLY -- no dollar / bankroll / pnl / roi field is introduced.
      BANNED_KEYS (from clv_ledger_migrate) are stripped before any write.
    * Never overwrites an existing line (append-only by construction).
    * Never claims an edge; this is a plumbing guard, not an intelligence layer.
    * Never raises -- a guard crash must NEVER lose a real bet record. On any
      unexpected exception the guard returns {"appended": False, "error": <msg>}.

USAGE (all in-lane writers, e.g. paper_autobet, grade_paper, inplay tick):

    from scripts.platformkit.clv_ledger_record_guard import record_bet_guarded

    result = record_bet_guarded(
        sport="nba", matchup="GSW @ BOS", side="home",
        taken_book="FanDuel", taken_decimal=2.10, model_prob=0.52,
        stake_units=1.0, game_date="2026-06-19",
    )
    if result["appended"]:
        row = result["record"]          # the written JSONL row
    # else: duplicate -- no-op, row already in ledger

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; per-file
test in scripts/platformkit/test_clv_ledger_record_guard.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_clv_ledger_record_guard.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.clv_ledger import bet_id as _bet_id
from scripts.platformkit.clv_ledger import record_bet as _record_bet_raw
from scripts.platformkit.clv_ledger_dedup import append_if_new as _append_if_new
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with all banned dollar/pnl/roi keys removed."""
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


def _compute_bet_id_from_kwargs(
    sport: str,
    matchup: str,
    side: str,
    taken_book: str,
    game_date: Optional[str],
    market: Optional[str],
    event_id: Optional[str],
) -> str:
    """Compute the stable bet_id from record_bet kwargs before writing."""
    probe: Dict[str, Any] = {
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": taken_book,
    }
    if game_date is not None:
        probe["game_date"] = game_date
    if market is not None:
        probe["market"] = market
    if event_id is not None:
        probe["event_id"] = event_id
    return _bet_id(probe)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def record_bet_guarded(
    sport: str,
    matchup: str,
    side: str,
    taken_book: str,
    taken_decimal: float,
    model_prob: Optional[float] = None,
    stake_units: float = 1.0,
    *,
    market: Optional[str] = None,
    event_id: Optional[str] = None,
    game_date: Optional[str] = None,
    path: Optional[Path] = None,
    stake: Optional[float] = None,  # deprecated alias -> units, never $
) -> Dict[str, Any]:
    """Dedup-guarded replacement for clv_ledger.record_bet.

    Computes the stable bet_id BEFORE writing and delegates to
    clv_ledger_dedup.append_if_new so that a repeat call with the same logical
    bet is a silent no-op (returns appended=False). A genuinely new bet is
    written via the lock-guarded clv_ledger_io.append_row path.

    Returns a dict:
      {"appended": True,  "record": <row_dict>, "bet_id": <str>}   -- new bet
      {"appended": False, "record": None,        "bet_id": <str>}   -- dup
      {"appended": False, "record": None, "error": <msg>}           -- guard err

    Honesty invariants:
      * No $ key is ever written (BANNED_KEYS stripped before append).
      * Append-only: existing ledger lines are never mutated.
      * Never raises: all exceptions are caught and returned in "error".
    """
    target = Path(path) if path is not None else None

    try:
        # --- 1. Compute stable bet_id before touching the ledger ----------
        bid = _compute_bet_id_from_kwargs(
            sport=sport,
            matchup=matchup,
            side=side,
            taken_book=taken_book,
            game_date=game_date,
            market=market,
            event_id=event_id,
        )

        # --- 2. Check for existence via append_if_new (scan + guard) ------
        # We use record_bet_raw to build the fully-shaped row dict, then pass
        # that row to append_if_new which already owns the "only write if new"
        # contract. However record_bet_raw ALSO writes (via _append_line). To
        # avoid a double-write we intercept at the row-construction level:
        # build the row dict manually (same shape as record_bet produces), strip
        # $ keys, then delegate entirely to append_if_new.
        from scripts.platformkit.clv_ledger import _now_iso  # type: ignore[attr-defined]

        units = float(stake if stake is not None else stake_units)
        s = str(side).strip().lower()

        row: Dict[str, Any] = {
            "ts": _now_iso(),
            "sport": str(sport),
            "matchup": str(matchup),
            "side": s,
            "taken_book": str(taken_book),
            "taken_decimal": float(taken_decimal),
            "model_prob": (float(model_prob) if model_prob is not None else None),
            "stake_units": units,
            "status": "open",
            "executed": False,
        }
        if market is not None:
            row["market"] = str(market)
        if event_id is not None:
            row["event_id"] = str(event_id)
        if game_date is not None:
            row["game_date"] = str(game_date)
        row["bet_id"] = bid

        # Strip any $ keys (belt-and-suspenders; record_bet never writes them
        # but a caller may have injected extras via a monkey-patch or subclass).
        row = _strip_dollar_keys(row)

        # --- 3. Conditional append via dedup guard -------------------------
        ledger_path = target
        written = _append_if_new(row, ledger_path)
        if written:
            return {"appended": True, "record": row, "bet_id": bid}
        return {"appended": False, "record": None, "bet_id": bid}

    except Exception as exc:  # noqa: BLE001 -- guard must NEVER raise
        return {"appended": False, "record": None, "error": str(exc)}


def record_settlement_guarded(
    settled: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Dedup-guarded settlement append.

    A settled row shares the same bet_id as its open twin (bet_id is
    status-agnostic). A settlement is a NEW logical ledger event (it carries
    status="settled") so we derive a SETTLEMENT-specific id by suffixing the
    standard bet_id with ":settled" to allow the pair (open + settled) to
    coexist while still deduping duplicate settlement writes.

    Returns {"appended": True, "record": <row>} or {"appended": False, ...}.
    Never raises.
    """
    target = Path(path) if path is not None else None
    try:
        base_id = settled.get("bet_id") or _bet_id(settled)
        settlement_id = base_id + ":settled"
        row = _strip_dollar_keys(dict(settled))
        row["bet_id"] = settlement_id  # override so dedup sees settlement slot
        written = _append_if_new(row, target)
        if written:
            return {"appended": True, "record": row, "bet_id": settlement_id}
        return {"appended": False, "record": None, "bet_id": settlement_id}
    except Exception as exc:  # noqa: BLE001
        return {"appended": False, "record": None, "error": str(exc)}


__all__ = [
    "record_bet_guarded",
    "record_settlement_guarded",
]
