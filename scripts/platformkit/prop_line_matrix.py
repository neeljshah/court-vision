"""scripts.platformkit.prop_line_matrix -- cross-book prop best-price matrix.

PropLineMatrix: for each (player, stat, side, line) key the row with the highest
decimal price wins.  One MatrixRow per canonical key; best_over_book /
best_under_book identify WHICH book offers the top price on each side.

Build-on (read-only):
  scripts.platformkit.odds_provider.prop_aggregate.best_line_props
  scripts.platformkit.odds_provider.prop_base.PropLine

Public API
----------
build_prop_matrix(
    providers  : Sequence[Any],   -- prop provider instances
    sport      : str,             -- e.g. "nba", "mlb", "soccer_intl"
    *,
    raw_rows   : Optional[List[PropLine]] = None,  -- injectable for tests
) -> List[MatrixRow]

MatrixRow fields (no $ field, no roi/profit):
  player, stat, line, sport, event_id, match,
  best_over_price, best_over_book,
  best_under_price, best_under_book,
  payout_type, as_of.

HONESTY: never fabricates a price; sides absent from every book stay None.
UNAVAILABLE: empty providers -> [] (no exception).
INVARIANTS: <=300 LOC; ASCII only; no $ field; build under scripts/platformkit/.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_line_matrix.py -q
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.odds_provider.prop_aggregate import (
    best_line_props,
    gather_props,
)
from scripts.platformkit.odds_provider.prop_base import PropLine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MatrixRow: one row per (player, stat, line) across ALL books
# ---------------------------------------------------------------------------

@dataclass
class MatrixRow:
    """Best-price summary for one (player, stat, line) across all polled books.

    best_over_price  : highest decimal OVER price seen across all books (> 1.0)
                       or None when no sportsbook quoted the OVER.
    best_over_book   : source/book name that yielded best_over_price; None when
                       best_over_price is None.
    best_under_price : same for the UNDER side.
    best_under_book  : same for the UNDER side.
    payout_type      : "sportsbook" when at least one side has a real price;
                       "dfs_pickem" when both sides are None (context row only).
    as_of            : most-recent as_of timestamp across all contributing rows.
    """

    player: str
    stat: str
    line: float
    sport: str
    event_id: str
    match: Optional[str]
    best_over_price: Optional[float]
    best_over_book: Optional[str]
    best_under_price: Optional[float]
    best_under_book: Optional[str]
    payout_type: str
    as_of: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _row_key(row: PropLine) -> Tuple[str, str, float]:
    """De-dup key: (player_lower, stat_lower, line).

    Uses same normalisation as prop_aggregate._key but WITHOUT event_id so that
    the matrix merges across events when a player appears in multiple games
    under the same stat+line.  Callers wanting per-game isolation should filter
    by event_id before calling build_prop_matrix.
    """
    return (
        str(row.player or "").strip().lower(),
        str(row.stat or "").strip().lower(),
        float(row.line),
    )


def _pick_better(
    current_price: Optional[float],
    current_book: Optional[str],
    candidate_price: Optional[float],
    candidate_book: Optional[str],
) -> Tuple[Optional[float], Optional[str]]:
    """Return whichever price is higher (decimal > 1.0 preferred over None).

    Never fabricates a price; never promotes a price <= 1.0.
    """
    if candidate_price is None:
        return current_price, current_book
    try:
        cp = float(candidate_price)
    except (TypeError, ValueError):
        return current_price, current_book
    if cp <= 1.0:
        return current_price, current_book
    if current_price is None:
        return cp, candidate_book
    try:
        cur = float(current_price)
    except (TypeError, ValueError):
        return cp, candidate_book
    if cp > cur:
        return cp, candidate_book
    return current_price, current_book


def _fresher_as_of(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the more-recent of two ISO-8601 as_of stamps (string compare is
    sufficient since they use the same YYYY-MM-DDTHH:MM format).  None loses."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


# ---------------------------------------------------------------------------
# Internal accumulator: one slot per (player, stat, line) key
# ---------------------------------------------------------------------------

@dataclass
class _Slot:
    player: str
    stat: str
    line: float
    sport: str
    event_id: str
    match: Optional[str]
    best_over_price: Optional[float] = None
    best_over_book: Optional[str] = None
    best_under_price: Optional[float] = None
    best_under_book: Optional[str] = None
    as_of: Optional[str] = None

    def absorb(self, row: PropLine) -> None:
        """Update slot with the best price from *row*."""
        self.best_over_price, self.best_over_book = _pick_better(
            self.best_over_price, self.best_over_book,
            row.over_price, row.source or "",
        )
        self.best_under_price, self.best_under_book = _pick_better(
            self.best_under_price, self.best_under_book,
            row.under_price, row.source or "",
        )
        self.as_of = _fresher_as_of(self.as_of, row.as_of)

    def to_row(self) -> MatrixRow:
        pt = ("sportsbook"
              if (self.best_over_price is not None
                  or self.best_under_price is not None)
              else "dfs_pickem")
        return MatrixRow(
            player=self.player,
            stat=self.stat,
            line=self.line,
            sport=self.sport,
            event_id=self.event_id,
            match=self.match,
            best_over_price=self.best_over_price,
            best_over_book=self.best_over_book,
            best_under_price=self.best_under_price,
            best_under_book=self.best_under_book,
            payout_type=pt,
            as_of=self.as_of,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_prop_matrix(
    providers: Sequence[Any],
    sport: str,
    *,
    raw_rows: Optional[List[PropLine]] = None,
) -> List[MatrixRow]:
    """Build the cross-book best-price matrix for all player props on *sport*.

    For each (player, stat, line) canonical key, exactly ONE MatrixRow is
    returned showing which book offers the highest OVER price and the highest
    UNDER price.

    Parameters
    ----------
    providers : provider instances (each must implement fetch_props(sport)).
        Ignored when raw_rows is supplied (test-injection path).
    sport : sport key e.g. "nba", "mlb", "soccer_intl".
    raw_rows : Optional pre-gathered PropLine list for offline / test use.
        When None (default), calls best_line_props(providers, sport) which
        already does per-side best-price merging across providers; then this
        function does the second pass to annotate WHICH book won each side.

    Returns
    -------
    Sorted list[MatrixRow] by (player, stat, line).  [] when no rows are
    available (offseason / all providers down).  NEVER raises.
    """
    try:
        if raw_rows is not None:
            source_rows: List[PropLine] = raw_rows
        else:
            source_rows = gather_props(providers, sport)

        if not source_rows:
            return []

        slots: Dict[Tuple[str, str, float], _Slot] = {}
        for row in source_rows:
            k = _row_key(row)
            if k not in slots:
                slots[k] = _Slot(
                    player=str(row.player or ""),
                    stat=str(row.stat or ""),
                    line=float(row.line),
                    sport=str(row.sport or sport),
                    event_id=str(row.event_id or ""),
                    match=row.match,
                    as_of=row.as_of,
                )
            slots[k].absorb(row)

        out = [slot.to_row() for slot in slots.values()]
        out.sort(key=lambda r: (r.player.lower(), r.stat.lower(), r.line))
        return out

    except Exception as exc:  # noqa: BLE001 -- never raises
        logger.warning("build_prop_matrix unexpected error for %s: %s", sport, exc)
        return []


__all__ = [
    "build_prop_matrix",
    "MatrixRow",
]
