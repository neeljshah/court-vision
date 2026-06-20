"""scripts.platformkit.odds_provider.line_movement_alert -- alert layer over line-movement.

Consumes LineShift records from line_movement.detect_line_movement and emits
MovementAlert objects for (book, market_type, side) pairs whose absolute price
shift exceeds a configurable threshold. Alerts carry a direction tag:

  STEAM  -- odds shortened (line moved toward a side; delta < -threshold)
  FADE   -- odds lengthened (line moved away from a side; delta > +threshold)
  STABLE -- absolute delta below threshold; no alert emitted by default

Usage::

    alerts = get_alerts("nba|NYK|SAS|2026-06-20", base=Path("data/cache/line_history"))
    # -> list[MovementAlert]; empty on missing history; never raises

Acceptance criteria (LS-12 extension):
  * open+latest rows for a (book, market) -> LineShift.delta == latest-open with
    sign matching direction; that flows into MovementAlert.delta + direction.
  * single-snapshot -> MovementAlert.status == INSUFFICIENT_DATA.
  * missing key -> [] no exception.
  * no $ / roi / pnl / edge field anywhere.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib only; no network (line_store readers are PURE).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_line_movement_alert.py -q
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .line_movement import (
    INSUFFICIENT_DATA,
    STATUS_OK,
    LineShift,
    detect_line_movement,
)

logger = logging.getLogger(__name__)

# Direction sentinels -- ASCII only; no $ / ROI / PNL.
DIRECTION_STEAM = "STEAM"   # odds shortened: line moved toward this side
DIRECTION_FADE = "FADE"     # odds lengthened: line moved away from this side
DIRECTION_STABLE = "STABLE" # shift below threshold; informational only

# Default threshold in decimal-odds units. A shift smaller than this in absolute
# value is classified STABLE and suppressed from the default alert list.
DEFAULT_THRESHOLD = 0.05


@dataclass
class MovementAlert:
    """A significant line shift for one (book, market_type, side).

    Fields
    ------
    game_key     -- the canonical game identifier passed in.
    book         -- venue name (e.g. "espn:BetMGM", "kalshi").
    market_type  -- "moneyline" | "spread" | "total".
    side         -- "home" | "away" | "over" | "under".
    open_odds    -- decimal odds at earliest captured quote (>1.0) or None.
    latest_odds  -- decimal odds at most-recent captured quote (>1.0) or None.
    delta        -- latest_odds - open_odds; positive = odds lengthened (FADE);
                    negative = odds shortened (STEAM). None when INSUFFICIENT_DATA.
    direction    -- STEAM | FADE | STABLE | INSUFFICIENT_DATA.
    open_at      -- ISO-8601 timestamp of open quote (or None).
    latest_at    -- ISO-8601 timestamp of latest quote (or None).
    venue_type   -- "sportsbook" | "prediction_market".
    status       -- "ok" | "INSUFFICIENT_DATA".
    threshold    -- the decimal-odds threshold used to classify this alert.
    """

    game_key: str
    book: str
    market_type: str
    side: str
    open_odds: Optional[float]
    latest_odds: Optional[float]
    delta: Optional[float]
    direction: str
    open_at: Optional[str]
    latest_at: Optional[str]
    venue_type: str
    status: str
    threshold: float


def _direction(delta: float, threshold: float) -> str:
    """Classify a delta (latest - open) into STEAM / FADE / STABLE.

    STEAM: odds shortened (delta < -threshold) -- the market moved TOWARD this
    side (implied probability increased). A line shortening from 2.00 -> 1.80
    is a classic steam move.

    FADE: odds lengthened (delta > +threshold) -- the market moved AWAY from
    this side (implied probability decreased). A line drifting from 1.80 -> 2.00
    suggests sharp money on the other side.

    STABLE: |delta| <= threshold -- no meaningful movement detected.
    """
    if delta < -threshold:
        return DIRECTION_STEAM
    if delta > threshold:
        return DIRECTION_FADE
    return DIRECTION_STABLE


def _alert_from_shift(shift: LineShift, threshold: float) -> MovementAlert:
    """Build a MovementAlert from a LineShift."""
    if shift.status != STATUS_OK or shift.delta is None:
        return MovementAlert(
            game_key=shift.game_key,
            book=shift.book,
            market_type=shift.market_type,
            side=shift.side,
            open_odds=shift.open_odds,
            latest_odds=shift.latest_odds,
            delta=None,
            direction=INSUFFICIENT_DATA,
            open_at=shift.open_at,
            latest_at=shift.latest_at,
            venue_type=shift.venue_type_tag,
            status=INSUFFICIENT_DATA,
            threshold=threshold,
        )
    direction = _direction(shift.delta, threshold)
    return MovementAlert(
        game_key=shift.game_key,
        book=shift.book,
        market_type=shift.market_type,
        side=shift.side,
        open_odds=shift.open_odds,
        latest_odds=shift.latest_odds,
        delta=shift.delta,
        direction=direction,
        open_at=shift.open_at,
        latest_at=shift.latest_at,
        venue_type=shift.venue_type_tag,
        status=STATUS_OK,
        threshold=threshold,
    )


def get_alerts(
    game_key: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    include_stable: bool = False,
    base: Optional[Path] = None,
) -> List[MovementAlert]:
    """Return MovementAlert objects for *game_key*.

    Parameters
    ----------
    game_key      -- canonical game key (game_id or "sport|home|away|date").
    threshold     -- decimal-odds delta floor; shifts below this are STABLE.
    include_stable-- when False (default), STABLE alerts are suppressed.
                     Pass True to surface every (book, market, side) pair.
    base          -- override for the line-history root dir (tests inject this).

    Returns
    -------
    List of MovementAlert, possibly empty. Never raises. An empty list means no
    history was found for this key -- it is NOT an error.

    INSUFFICIENT_DATA is returned per-shift when only a single snapshot exists
    for that (book, market_type, side) so no movement can be measured.
    """
    try:
        shifts: List[LineShift] = detect_line_movement(game_key, base=base)
    except Exception:  # noqa: BLE001
        logger.exception(
            "line_movement_alert: unexpected error for game_key=%r", game_key
        )
        return []

    if not shifts:
        return []

    alerts: List[MovementAlert] = []
    for shift in shifts:
        alert = _alert_from_shift(shift, threshold)
        if not include_stable and alert.direction == DIRECTION_STABLE:
            continue
        alerts.append(alert)
    return alerts


def filter_by_direction(
    alerts: List[MovementAlert], direction: str
) -> List[MovementAlert]:
    """Return only alerts matching *direction* (STEAM | FADE | INSUFFICIENT_DATA)."""
    return [a for a in alerts if a.direction == direction]


def filter_by_book(
    alerts: List[MovementAlert], book: str
) -> List[MovementAlert]:
    """Return only alerts for *book* (exact venue name match)."""
    return [a for a in alerts if a.book == book]


__all__ = [
    "MovementAlert",
    "DEFAULT_THRESHOLD",
    "DIRECTION_STEAM",
    "DIRECTION_FADE",
    "DIRECTION_STABLE",
    "INSUFFICIENT_DATA",
    "get_alerts",
    "filter_by_direction",
    "filter_by_book",
]
