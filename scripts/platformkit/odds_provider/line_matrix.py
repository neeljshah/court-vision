"""scripts.platformkit.odds_provider.line_matrix -- per-market-type multi-book line matrix.

build_line_matrix(sport, home, away, *, agg=None, now=None) -> LineMatrix

One LineMatrix per game; one MarketRow per market-type that any book quoted
(moneyline / spread / total); one BookCell per distinct book per row.
Per-cell freshness via freshness.freshness_status.  as_of = OLDEST cell
timestamp (stale-never-green).  No $ field; no fabricated price; UNAVAILABLE
when the slate is empty or the game is absent.  agg/now injectable for tests.

BookCell fields: book, venue_type, home_odds, away_odds, line, over_odds,
under_odds, devigged_home, devigged_away, captured_at, freshness, age_sec.
MarketRow.status: "ok" (>=2 books) | "single_book" (1 book) | "unavailable".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .aggregate import aggregate as _aggregate, _event_match, teams_match
from .base import OddsEvent, venue_type as _venue_type
from .freshness import freshness_status, DEFAULT_MAX_AGE_SEC
from .markets import (
    MarketQuote, quotes_from_aggregate,
    MONEYLINE, SPREAD, TOTAL,
)

STATUS_OK = "ok"
STATUS_SINGLE = "single_book"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class BookCell:
    """One book's price for one market-type in one game."""

    book: str
    venue_type: str
    home_odds: Optional[float]
    away_odds: Optional[float]
    line: Optional[float]        # spread handicap OR total line (None for ML)
    over_odds: Optional[float]   # total only
    under_odds: Optional[float]  # total only
    devigged_home: Optional[float]
    devigged_away: Optional[float]
    captured_at: Optional[str]
    freshness: str               # "fresh" | "stale" | "unknown"
    age_sec: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketRow:
    """All books for one market_type in one game."""

    market_type: str
    books: List[BookCell] = field(default_factory=list)
    book_count: int = 0
    status: str = STATUS_UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LineMatrix:
    """Full multi-book line matrix for one game."""

    sport: str
    game_id: str
    home: str
    away: str
    status: str
    as_of: str
    rows: List[MarketRow] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso(now: Optional[datetime]) -> str:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _oldest_timestamp(cells: List[BookCell], fallback: str) -> str:
    """Return the OLDEST captured_at across all cells (stale-never-green)."""
    parsed = []
    for c in cells:
        ts = c.captured_at
        if not ts:
            continue
        try:
            s = str(ts).replace("Z", "+00:00")
            parsed.append((datetime.fromisoformat(s), ts))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return fallback
    return min(parsed, key=lambda t: t[0])[1]


def _cell_freshness(ts: Optional[str], now: Optional[datetime],
                    market_type: str) -> Dict[str, Any]:
    return freshness_status(
        ts, now=now, market_type=market_type,
        max_age_sec=DEFAULT_MAX_AGE_SEC)


def _quotes_for_game(quotes: List[MarketQuote],
                     home: str, away: str,
                     sport: str) -> List[MarketQuote]:
    """Filter quotes to those belonging to the requested game."""
    out = []
    for q in quotes:
        if (teams_match(q.home, home, sport)
                and teams_match(q.away, away, sport)):
            out.append(q)
        elif (teams_match(q.home, away, sport)
              and teams_match(q.away, home, sport)):
            out.append(q)
    return out


def _build_cells_for_market(game_quotes: List[MarketQuote],
                             market_type: str,
                             now: Optional[datetime],
                             ) -> List[BookCell]:
    """Aggregate per-book cells for one market_type from game-scoped quotes."""
    # group quotes by book
    by_book: Dict[str, List[MarketQuote]] = {}
    for q in game_quotes:
        if q.market_type != market_type:
            continue
        by_book.setdefault(q.book, []).append(q)

    cells: List[BookCell] = []
    for book, qs in by_book.items():
        # gather sides
        home_odds = away_odds = line = None
        over_odds = under_odds = None
        dh = da = None
        captured_at = None

        for q in qs:
            captured_at = captured_at or q.captured_at
            if market_type == MONEYLINE:
                if q.side == "home":
                    home_odds = q.odds
                    dh = q.devigged_prob
                elif q.side == "away":
                    away_odds = q.odds
                    da = q.devigged_prob
            elif market_type == SPREAD:
                if q.side == "home":
                    home_odds = q.odds
                    line = q.line
                    dh = q.devigged_prob
                elif q.side == "away":
                    away_odds = q.odds
                    da = q.devigged_prob
            elif market_type == TOTAL:
                if q.side == "over":
                    over_odds = q.odds
                    line = q.line
                elif q.side == "under":
                    under_odds = q.odds

        fs = _cell_freshness(captured_at, now, market_type)
        cells.append(BookCell(
            book=book,
            venue_type=_venue_type(book),
            home_odds=home_odds,
            away_odds=away_odds,
            line=line,
            over_odds=over_odds,
            under_odds=under_odds,
            devigged_home=dh,
            devigged_away=da,
            captured_at=captured_at,
            freshness=fs["status"],
            age_sec=fs["age_sec"],
        ))
    return cells


def _row_status(book_count: int) -> str:
    if book_count >= 2:
        return STATUS_OK
    if book_count == 1:
        return STATUS_SINGLE
    return STATUS_UNAVAILABLE


def build_line_matrix(
    sport: str,
    game_home: str,
    game_away: str,
    *,
    agg: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> LineMatrix:
    """Build the multi-book line matrix for one game.

    Parameters
    ----------
    sport       : sport key ("nba", "mlb", "soccer", ...).
    game_home   : home team name as known to the caller.
    game_away   : away team name as known to the caller.
    agg         : pre-fetched aggregate() payload (injectable for offline tests).
                  When None, calls aggregate(sport) -- hits real providers.
    now         : injectable UTC datetime for freshness checks (default: real now).

    Returns
    -------
    LineMatrix with status="unavailable" when no quotes are found for the game,
    and rows for each market_type that at least one book quoted.  Single-book
    markets get status="single_book" (honest).  Offseason / no slate -> rows=[].
    """
    now_str = _now_iso(now)
    payload = agg if agg is not None else _aggregate(sport)

    # Aggregate failed or empty
    if not isinstance(payload, dict) or payload.get("status") != STATUS_OK:
        return LineMatrix(
            sport=sport.lower(), game_id="",
            home=game_home, away=game_away,
            status=STATUS_UNAVAILABLE, as_of=now_str,
            rows=[])

    # Derive game_id from the matching event in the aggregate
    game_id = ""
    sport_key = str(payload.get("sport") or sport).lower()
    for ev in payload.get("events", []) or []:
        if (teams_match(ev.get("home", ""), game_home, sport_key)
                and teams_match(ev.get("away", ""), game_away, sport_key)):
            game_id = str(ev.get("event_id") or "")
            break
        if (teams_match(ev.get("home", ""), game_away, sport_key)
                and teams_match(ev.get("away", ""), game_home, sport_key)):
            game_id = str(ev.get("event_id") or "")
            break

    quotes = quotes_from_aggregate(sport_key, agg=payload, now=now)
    game_quotes = _quotes_for_game(quotes, game_home, game_away, sport_key)

    if not game_quotes:
        return LineMatrix(
            sport=sport_key, game_id=game_id,
            home=game_home, away=game_away,
            status=STATUS_UNAVAILABLE, as_of=now_str,
            rows=[])

    rows: List[MarketRow] = []
    all_cells: List[BookCell] = []
    for mt in (MONEYLINE, SPREAD, TOTAL):
        cells = _build_cells_for_market(game_quotes, mt, now)
        if not cells:
            continue
        cnt = len(cells)
        rows.append(MarketRow(
            market_type=mt,
            books=cells,
            book_count=cnt,
            status=_row_status(cnt),
        ))
        all_cells.extend(cells)

    as_of = _oldest_timestamp(all_cells, now_str)
    matrix_status = STATUS_OK if any(
        r.status in (STATUS_OK, STATUS_SINGLE) for r in rows
    ) else STATUS_UNAVAILABLE

    return LineMatrix(
        sport=sport_key, game_id=game_id,
        home=game_home, away=game_away,
        status=matrix_status, as_of=as_of,
        rows=rows,
    )


__all__ = [
    "build_line_matrix",
    "LineMatrix", "MarketRow", "BookCell",
    "STATUS_OK", "STATUS_SINGLE", "STATUS_UNAVAILABLE",
]
