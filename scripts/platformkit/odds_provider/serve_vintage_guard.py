"""scripts.platformkit.odds_provider.serve_vintage_guard -- serve-time vintage guard.

QA iter 11 P1: the snapshot/serve layer re-stamped captured_at to now() even when
underlying prices were UNCHANGED, hiding the true ingest age from every consumer.
This module is the pure serve-time fix.

Public API
----------
apply(incoming_row, prior_row, *, game_state=None) -> dict

Given a DICT-shaped market row (the shape snapshot.write_quotes emits and
line_store reads: keys include market_type, side, line, odds, book,
captured_at, game_id, ...) and an optional prior row for the same
(game_id, market_type, book, side):

  - SAME price (line + odds unchanged) -> keep prior captured_at; do NOT
    advance to the incoming row's captured_at (the stale-re-stamp bug).
  - CHANGED price -> use the incoming row's captured_at (the new tick).
  - NO prior row -> passthrough: use the incoming row's captured_at unchanged.
  - is_close=True is set on the returned row when the game_state arg signals
    the game is post/Final (post-game or completed).
  - price_changed and captured_at_preserved flags are added as audit fields.

Returns a NEW dict (never mutates the inputs). Never raises; a bad/missing
captured_at is passed through without fabrication. No $ field; ASCII only.

Build on
--------
  - capture_vintage_guard: same price-unchanged philosophy (read, not imported
    to avoid circular dependency -- we are a pure dict layer).
  - postgame_suppress._COMPLETED_STATES (conceptually; we redeclare inline to
    stay import-free from ingame/).
  - line_store row shape (keys: market_type, side, line, odds, book, captured_at).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; stdlib only; pure
(injectable now); no network, no I/O; no fabricated timestamps; no $ field.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_serve_vintage_guard.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Game-state strings that indicate a completed game (post/Final).
# Duplicated inline to avoid a cross-subpackage import.
_POSTGAME_STATES = frozenset({
    "post", "final", "final_ot", "final_pen",
    "STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_PEN",
    "STATUS_FINAL_OVERTIME",
})


def _is_postgame(game_state: Any) -> bool:
    """True iff game_state signals the game is completed (post/Final).

    Accepts a string, a dict with a 'state' key, or None. Never raises.
    """
    if game_state is None:
        return False
    try:
        if isinstance(game_state, dict):
            raw = str(game_state.get("state") or "").strip()
        else:
            raw = str(game_state).strip()
        if not raw:
            return False
        lraw = raw.lower()
        # Exact set check (case-insensitive for the common variants).
        if lraw in {"post", "final", "final_ot", "final_pen"}:
            return True
        # Also check the full set of exact strings (ESPN/NBA API variants).
        return raw in _POSTGAME_STATES
    except Exception:  # noqa: BLE001
        return False


def _price_key(row: Dict[str, Any]) -> tuple:
    """A (line, rounded_odds) fingerprint of the price, independent of captured_at.

    Two rows with the same side/line/odds are price-equivalent. line is kept as
    a rounded float (4 dp) to absorb tiny float-repr noise; odds rounded to 6 dp
    (matching capture_vintage_guard._price_key precision).
    """
    try:
        line = row.get("line")
        odds = row.get("odds")
        line_val = round(float(line), 4) if line is not None else None
        odds_val = round(float(odds), 6) if odds is not None else None
    except (TypeError, ValueError):
        line_val = None
        odds_val = None
    return (line_val, odds_val)


def apply(
    incoming_row: Dict[str, Any],
    prior_row: Optional[Dict[str, Any]],
    *,
    game_state: Any = None,
) -> Dict[str, Any]:
    """Apply the serve-time vintage guard to one market row.

    Parameters
    ----------
    incoming_row : dict
        The freshly polled market row (line_store/snapshot row shape).
        Must carry at minimum 'odds' and 'captured_at'. Never mutated.
    prior_row : dict | None
        The most-recently persisted row for the same (game_id, market_type,
        book, side), as returned by line_store.get_latest(). Pass None on
        first observation (no prior history).
    game_state : str | dict | None
        Optional game-completion signal. A string like "post"/"Final" or a dict
        with a 'state' key. When this signals the game is complete, is_close=True
        is stamped on the returned row.

    Returns
    -------
    dict
        A copy of incoming_row with:
          - captured_at  : preserved from prior when price unchanged; else incoming.
          - is_close     : True when game_state is post/Final; False otherwise.
          - price_changed: True when odds/line differ from prior; False otherwise.
          - captured_at_preserved: True when prior captured_at was kept.

    Never raises; never fabricates a timestamp; no $ field.
    """
    try:
        return _apply_inner(incoming_row, prior_row, game_state=game_state)
    except Exception:  # noqa: BLE001 -- serve path must never raise
        logger.exception("serve_vintage_guard.apply() unexpected error; passthrough")
        out = dict(incoming_row)
        out.setdefault("is_close", False)
        out.setdefault("price_changed", False)
        out.setdefault("captured_at_preserved", False)
        return out


def _apply_inner(
    incoming_row: Dict[str, Any],
    prior_row: Optional[Dict[str, Any]],
    *,
    game_state: Any,
) -> Dict[str, Any]:
    out = dict(incoming_row)

    # --- is_close from game_state -------------------------------------------
    out["is_close"] = _is_postgame(game_state)

    # --- No prior: passthrough captured_at unchanged -------------------------
    if prior_row is None or not isinstance(prior_row, dict):
        out["price_changed"] = False
        out["captured_at_preserved"] = False
        return out

    # --- Compare price keys --------------------------------------------------
    incoming_pk = _price_key(incoming_row)
    prior_pk = _price_key(prior_row)

    if incoming_pk == prior_pk:
        # Price UNCHANGED: keep the prior's captured_at.
        prior_ts = str(prior_row.get("captured_at") or "").strip()
        if prior_ts:
            out["captured_at"] = prior_ts
            out["price_changed"] = False
            out["captured_at_preserved"] = True
        else:
            # Prior has no usable captured_at; fall through to incoming.
            out["price_changed"] = False
            out["captured_at_preserved"] = False
    else:
        # Price CHANGED: use the incoming captured_at (the new tick).
        out["price_changed"] = True
        out["captured_at_preserved"] = False

    return out


def apply_batch(
    rows: list,
    prior_by_key: Optional[Dict[tuple, Dict[str, Any]]] = None,
    *,
    game_state: Any = None,
) -> list:
    """Apply the vintage guard to a batch of market rows.

    prior_by_key maps (game_id, market_type, book, side) -> most-recent prior row.
    Rows without a matching prior key are treated as first-observations (passthrough).
    Returns a new list of guarded rows. Never raises.
    """
    if not rows:
        return []
    prior_map: Dict[tuple, Dict[str, Any]] = prior_by_key or {}
    out = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        key = (
            str(row.get("game_id") or ""),
            str(row.get("market_type") or ""),
            str(row.get("book") or ""),
            str(row.get("side") or ""),
        )
        prior = prior_map.get(key)
        out.append(apply(row, prior, game_state=game_state))
    return out


__all__ = [
    "apply",
    "apply_batch",
]
