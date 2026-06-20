"""scripts.platformkit.odds_provider.line_movement -- line-movement detector.

Compares the OPEN quote (earliest captured) to the LATEST quote per
(book, market_type, side) for a game key. Emits a LineShift dataclass whose
`delta` field is `latest_odds - open_odds` (positive = line drifted toward the
favorite/over; negative = drifted toward the dog/under). The sign is defined
for DECIMAL odds: a price increasing from 1.80 to 2.00 means the implied
probability FELL (side became less favored) -- `delta = +0.20`.

If only an open quote exists (no separate later quote) or history is missing,
`LineShift.status` is set to `INSUFFICIENT_DATA` and `delta` is None -- we
NEVER fabricate a shift.

PM venues (Kalshi / Polymarket) are tagged `venue_type = "prediction_market"`;
sportsbook-republished lines are tagged `"sportsbook"`. The caller can filter
on that field.

No $ / ROI / edge fields. Calibration only.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib only; no network (get_open / get_latest are PURE readers).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_line_movement.py -q
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .base import venue_type
from .line_store import get_latest, get_open, parse_game_key

logger = logging.getLogger(__name__)

# Status sentinels
STATUS_OK = "ok"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# A (market_type, side) compound key as stored in line_store dicts.
_MS = Tuple[str, str]


@dataclass
class LineShift:
    """Movement of a single (book, market_type, side) line between open and latest.

    Fields:
        game_key    -- the canonical game identifier passed in.
        book        -- venue name (e.g. "espn:BetMGM", "kalshi").
        market_type -- "moneyline" | "spread" | "total".
        side        -- "home" | "away" | "over" | "under".
        open_odds   -- decimal odds of the earliest captured quote (>1.0).
        latest_odds -- decimal odds of the most-recent captured quote (>1.0).
        delta       -- latest_odds - open_odds; positive = odds lengthened
                       (side less favored); negative = odds shortened (more favored).
                       None when status != "ok".
        open_at     -- ISO-8601 timestamp of the open quote.
        latest_at   -- ISO-8601 timestamp of the latest quote.
        venue_type  -- "sportsbook" | "prediction_market".
        status      -- "ok" | "INSUFFICIENT_DATA".
    """

    game_key: str
    book: str
    market_type: str
    side: str
    open_odds: Optional[float]
    latest_odds: Optional[float]
    delta: Optional[float]
    open_at: Optional[str]
    latest_at: Optional[str]
    venue_type_tag: str
    status: str


def _extract_odds(row: Dict[str, Any]) -> Optional[float]:
    """Decimal odds (> 1.0) from a line_store row, or None."""
    try:
        v = float(row.get("odds", 0))
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _captured_at(row: Dict[str, Any]) -> Optional[str]:
    try:
        return str(row.get("captured_at") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _build_shifts(
    game_key: str,
    open_quotes: Dict[_MS, Dict[str, Any]],
    latest_quotes: Dict[_MS, Dict[str, Any]],
) -> List[LineShift]:
    """Pair open vs latest per (market_type, side, book); emit LineShifts."""
    # Index open quotes by (market_type, side, book).
    # A line_store row has market_type, side, and book fields.
    open_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in open_quotes.values():
        mt = str(row.get("market_type", ""))
        sd = str(row.get("side", ""))
        bk = str(row.get("book", ""))
        if mt and sd and bk:
            open_by_key[(mt, sd, bk)] = row

    latest_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in latest_quotes.values():
        mt = str(row.get("market_type", ""))
        sd = str(row.get("side", ""))
        bk = str(row.get("book", ""))
        if mt and sd and bk:
            latest_by_key[(mt, sd, bk)] = row

    # For each (market_type, side, book) present in either set:
    all_keys = set(open_by_key.keys()) | set(latest_by_key.keys())
    out: List[LineShift] = []
    for mt, sd, bk in sorted(all_keys):
        o_row = open_by_key.get((mt, sd, bk))
        l_row = latest_by_key.get((mt, sd, bk))
        vt = venue_type(bk)

        if o_row is None or l_row is None:
            # Only one side of the pair -- no movement can be computed.
            out.append(LineShift(
                game_key=game_key,
                book=bk,
                market_type=mt,
                side=sd,
                open_odds=_extract_odds(o_row) if o_row else None,
                latest_odds=_extract_odds(l_row) if l_row else None,
                delta=None,
                open_at=_captured_at(o_row) if o_row else None,
                latest_at=_captured_at(l_row) if l_row else None,
                venue_type_tag=vt,
                status=INSUFFICIENT_DATA,
            ))
            continue

        o_odds = _extract_odds(o_row)
        l_odds = _extract_odds(l_row)
        if o_odds is None or l_odds is None:
            out.append(LineShift(
                game_key=game_key,
                book=bk,
                market_type=mt,
                side=sd,
                open_odds=o_odds,
                latest_odds=l_odds,
                delta=None,
                open_at=_captured_at(o_row),
                latest_at=_captured_at(l_row),
                venue_type_tag=vt,
                status=INSUFFICIENT_DATA,
            ))
            continue

        # Both quotes are usable -- compute delta.
        out.append(LineShift(
            game_key=game_key,
            book=bk,
            market_type=mt,
            side=sd,
            open_odds=o_odds,
            latest_odds=l_odds,
            delta=round(l_odds - o_odds, 6),
            open_at=_captured_at(o_row),
            latest_at=_captured_at(l_row),
            venue_type_tag=vt,
            status=STATUS_OK,
        ))
    return out


def detect_line_movement(
    game_key: str,
    *,
    base=None,
) -> List[LineShift]:
    """Detect line movement for *game_key*.

    Returns a list of LineShift objects, one per (book, market_type, side).
    An empty list is returned when no history exists at all (not an error --
    the caller should treat empty == no data, not a failure). Never raises.

    Each LineShift.status is either "ok" (delta computed) or
    "INSUFFICIENT_DATA" (only open, only latest, or malformed odds).
    PM venues are tagged venue_type_tag="prediction_market".
    """
    try:
        open_quotes = get_open(game_key, base=base)
        latest_quotes = get_latest(game_key, base=base)
    except Exception:  # noqa: BLE001
        logger.exception("line_movement: error reading line store for %r", game_key)
        return []

    if open_quotes is None and latest_quotes is None:
        return []

    o = open_quotes or {}
    l = latest_quotes or {}
    return _build_shifts(game_key, o, l)


__all__ = [
    "LineShift",
    "INSUFFICIENT_DATA",
    "STATUS_OK",
    "detect_line_movement",
]
