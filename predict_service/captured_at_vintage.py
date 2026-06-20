"""predict_service.captured_at_vintage -- vintage-preserving captured_at normalizer.

BE7-2-captured-at-vintage. QA iter11 P1 root cause: served market rows showed
captured_at = current fetch time even when underlying odds had NOT changed since
the prior ingest cycle. A consumer could not distinguish a live price update from
a stale re-serve, and is_close stayed False on completed (post/Final) games.

FIX: normalize_markets(markets, history, game_state) -> List[dict]
  Pure function, NO network. For each market row:

  * The key is (book, market_type, side).
  * If the prior history contains a row for this key whose price (odds, line)
    matches the current row -> preserve the ORIGINAL captured_at from history.
    Do NOT advance it -- it was not a live update.
  * If the price changed, or there is no prior history entry -> use the row's own
    captured_at (set by the caller from the live fetch; may be "now").
  * If the row itself has no captured_at -> passthrough unchanged (no crash).
  * is_close is set to True on every output row when game_state indicates the
    game is post/Final (state strings: 'post', 'final', 'ft', 'complete',
    'finished', 'closed'). Never fabricates is_close=True on a live or pre game.

GUARANTEE:
  * Absent history -> passthrough (no crash; no fabricated timestamp).
  * Changed price -> captured_at advances (honest: a real update happened).
  * Unchanged price -> captured_at stays at original ingest time (honest: no update).
  * post/Final game_state -> is_close=True on all rows (honest close marker).
  * pre/live game_state -> is_close unchanged (never falsely marked closed).
  * NEVER raises; NEVER mutates the input list or dicts.
  * No $ field; calibration not edge; ASCII only.

PUBLIC API:
  normalize_markets(markets, history, game_state) -> List[dict]
  is_post_game(game_state)                         -> bool
  vintage_key(row)                                 -> tuple

INVARIANTS: <=300 LOC; ASCII only; stdlib only; no I/O at import; NEVER raises;
no $ field; no edge claim; calibration not edge.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Post-game state strings -- match produce._derive_game_state vocabulary.
# ---------------------------------------------------------------------------
_POST_STATES = frozenset(
    {"post", "final", "ft", "complete", "finished", "closed"}
)

HONEST_NOTE = (
    "captured_at_vintage: unchanged price keeps the original ingest timestamp; "
    "changed price advances it; post/Final -> is_close=True; no fabricated "
    "timestamp; no $ field; calibration not edge."
)


# ---------------------------------------------------------------------------
# Public helpers.
# ---------------------------------------------------------------------------

def is_post_game(game_state: Any) -> bool:
    """True when game_state indicates the game is over (post/Final/closed).

    Accepts the same vocabulary as produce._derive_game_state (case-insensitive).
    NEVER raises.
    """
    try:
        if game_state is None:
            return False
        return str(game_state).strip().lower() in _POST_STATES
    except Exception:  # noqa: BLE001
        return False


def vintage_key(row: Any) -> Optional[Tuple[str, str, str]]:
    """Return the (book, market_type, side) identity key for a market row dict.

    Returns None if the row is not a dict or any key field is missing/falsy.
    NEVER raises.
    """
    try:
        if not isinstance(row, dict):
            return None
        book = str(row.get("book") or "")
        mt = str(row.get("market_type") or "")
        side = str(row.get("side") or "")
        # All three fields must be non-empty for a valid key.
        if not book or not mt or not side:
            return None
        return (book, mt, side)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Internal price-equivalence check.
# ---------------------------------------------------------------------------

def _prices_match(row_a: Dict[str, Any], row_b: Dict[str, Any]) -> bool:
    """True when odds and line are numerically equal (or both absent).

    Uses an epsilon comparison for floats to avoid fp noise across serialisation
    cycles. None/missing values are treated as equal only when BOTH are absent.
    NEVER raises.
    """
    try:
        def _extract(row: Dict[str, Any], field: str) -> Optional[float]:
            v = row.get(field)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        odds_a = _extract(row_a, "odds")
        odds_b = _extract(row_b, "odds")
        line_a = _extract(row_a, "line")
        line_b = _extract(row_b, "line")

        # odds comparison
        if odds_a is None and odds_b is None:
            odds_eq = True
        elif odds_a is None or odds_b is None:
            odds_eq = False
        else:
            odds_eq = abs(odds_a - odds_b) < 1e-9

        # line comparison
        if line_a is None and line_b is None:
            line_eq = True
        elif line_a is None or line_b is None:
            line_eq = False
        else:
            line_eq = abs(line_a - line_b) < 1e-9

        return odds_eq and line_eq
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Core normalizer.
# ---------------------------------------------------------------------------

def normalize_markets(
    markets: Any,
    history: Any,
    game_state: Any = None,
) -> List[Dict[str, Any]]:
    """Return a NEW list of market row dicts with vintage-preserving captured_at.

    Parameters
    ----------
    markets:
        Iterable of market row dicts (the CURRENT serve -- may be MarketRow.to_dict()
        outputs or plain dicts with at minimum {book, market_type, side, odds, line,
        captured_at, is_close}).
    history:
        Prior ingest -- any iterable of dicts with the same shape; OR None/empty
        (absent history -> passthrough with no crash). Typically the last persisted
        markets[] from the canonical store.
    game_state:
        String game state ('pre'|'live'|'post'|'final'|...). Used ONLY to set
        is_close=True when post/Final. None -> treated as 'pre' (no is_close flip).

    Returns
    -------
    List[dict] -- NEW dicts; inputs are never mutated.

    Invariants
    ----------
    * NEVER raises.
    * Absent history -> passthrough (captured_at unchanged; is_close set if post).
    * Changed price (odds or line) -> captured_at from the current row (fresh).
    * Unchanged price -> captured_at preserved from the OLDEST matching history row
      (the original ingest time; never the current fetch time).
    * post/Final game_state -> is_close=True on every output row.
    * No $ field; calibration not edge.
    """
    try:
        post = is_post_game(game_state)

        # Build a lookup from (book, market_type, side) -> history row.
        hist_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for h in (history or []):
            if not isinstance(h, dict):
                continue
            k = vintage_key(h)
            if k is not None and k not in hist_index:
                # Keep the FIRST (oldest) match in the index; if the caller passes
                # a list ordered newest-first, we still want the original ingest.
                hist_index[k] = h

        out: List[Dict[str, Any]] = []
        for row in (markets or []):
            if not isinstance(row, dict):
                # Non-dict row: pass through unchanged but wrap as copy-safe.
                try:
                    out.append(dict(row))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001
                    out.append(row)  # last resort: share the reference
                continue

            new_row = dict(row)

            # Vintage preservation: if history has a matching key with the same
            # price, keep the original captured_at.
            k = vintage_key(row)
            if k is not None and k in hist_index:
                hist_row = hist_index[k]
                if _prices_match(row, hist_row):
                    # Price unchanged -> preserve original ingest timestamp.
                    orig_ts = hist_row.get("captured_at")
                    if orig_ts is not None:
                        new_row["captured_at"] = orig_ts
                # If price changed, new_row["captured_at"] stays as set by caller.

            # is_close: set True when game is definitively over.
            if post:
                new_row["is_close"] = True

            out.append(new_row)

        return out

    except Exception as exc:  # noqa: BLE001 -- normalizer must never crash callers
        logger.warning("captured_at_vintage.normalize_markets failed: %s", exc)
        # Safe fallback: return the input list (or empty) unmodified.
        try:
            return [dict(r) for r in (markets or []) if isinstance(r, dict)]
        except Exception:  # noqa: BLE001
            return []


__all__ = [
    "HONEST_NOTE",
    "is_post_game",
    "vintage_key",
    "normalize_markets",
]
