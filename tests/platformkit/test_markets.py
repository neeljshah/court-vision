"""Per-file unit tests for odds_provider.markets (NETWORK-FREE).

Run ONLY this file (a bare pytest freezes the box):
    python -m pytest tests/platformkit/test_markets.py -q

Feeds a CANNED aggregate() payload (offline, via the agg= injection) and asserts
typed MarketQuotes are produced for moneyline + spread + total with correct
sides/lines, malformed entries omitted, and devigged_prob in (0,1) when present.
"""
from datetime import datetime, timezone

from scripts.platformkit.odds_provider.markets import (
    MONEYLINE, SPREAD, TOTAL, MarketQuote, quotes_from_aggregate)

_CAPTURED = "2026-06-18T20:00:00+00:00"

# Canned aggregate() payload. event #1 is well-formed across all three markets
# (one sportsbook with moneyline + extended spread + total, plus a kalshi
# moneyline-only venue). The remaining events are MALFORMED in distinct ways and
# must be omitted (never fabricated into a line).
_AGG = {
    "sport": "nba",
    "status": "ok",
    "as_of": _CAPTURED,
    "sources": {"espn": "ok"},
    "events": [
        {  # fully-formed: moneyline + spread + total on a book; ml-only on kalshi
            "event_id": "401",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "New York Knicks",
            "prices": {
                "espn:DraftKings": {
                    "home": 1.50, "away": 2.60, "draw": None,
                    "spread": {
                        "home": {"line": -5.5, "odds": 1.91},
                        "away": {"line": 5.5, "odds": 1.91},
                    },
                    "total": {
                        "over": {"line": 220.5, "odds": 1.95},
                        "under": {"line": 220.5, "odds": 1.87},
                    },
                },
                "kalshi": {"home": 1.55, "away": 2.50, "draw": None},
            },
        },
        {  # malformed: missing home name -> whole event omitted
            "event_id": "402", "sport": "nba", "home": "", "away": "Heat",
            "prices": {"espn:FD": {"home": 1.8, "away": 2.0}},
        },
        {  # malformed: prices not a dict -> omitted
            "event_id": "403", "sport": "nba",
            "home": "Lakers", "away": "Suns", "prices": None,
        },
        {  # partial: one-sided moneyline (away unpriced) + spread missing a line
            "event_id": "404", "sport": "nba",
            "home": "Bucks", "away": "Bulls",
            "prices": {
                "espn:BetMGM": {
                    "home": 1.70, "away": None,  # away has no usable price
                    "spread": {
                        "home": {"odds": 1.91},          # no line -> omitted
                        "away": {"line": 4.5, "odds": 1.91},
                    },
                },
            },
        },
    ],
}


def _q(quotes, market_type, side, book):
    matches = [q for q in quotes
               if q.market_type == market_type and q.side == side
               and q.book == book]
    return matches[0] if matches else None


def test_returns_marketquotes():
    quotes = quotes_from_aggregate("nba", agg=_AGG)
    assert quotes and all(isinstance(q, MarketQuote) for q in quotes)
    assert all(q.captured_at == _CAPTURED for q in quotes)
    # events 401 (full) + 404 (partial-but-valid) survive; 402/403 dropped.
    assert {q.game_id for q in quotes} == {"401", "404"}


def test_moneyline_quotes():
    quotes = quotes_from_aggregate("nba", agg=_AGG)
    h = _q(quotes, MONEYLINE, "home", "espn:DraftKings")
    a = _q(quotes, MONEYLINE, "away", "espn:DraftKings")
    assert h is not None and a is not None
    assert h.line is None and h.odds == 1.50
    assert a.odds == 2.60
    assert h.home == "Boston Celtics" and h.away == "New York Knicks"
    # both sides price -> devig present and in (0,1), summing ~1.
    assert 0.0 < h.devigged_prob < 1.0 and 0.0 < a.devigged_prob < 1.0
    assert abs(h.devigged_prob + a.devigged_prob - 1.0) < 1e-6
    # kalshi moneyline-only venue is also surfaced.
    assert _q(quotes, MONEYLINE, "home", "kalshi") is not None


def test_spread_quotes():
    quotes = quotes_from_aggregate("nba", agg=_AGG)
    h = _q(quotes, SPREAD, "home", "espn:DraftKings")
    a = _q(quotes, SPREAD, "away", "espn:DraftKings")
    assert h is not None and a is not None
    assert h.line == -5.5 and a.line == 5.5
    assert h.odds == 1.91 and a.odds == 1.91
    assert 0.0 < h.devigged_prob < 1.0


def test_total_quotes():
    quotes = quotes_from_aggregate("nba", agg=_AGG)
    over = _q(quotes, TOTAL, "over", "espn:DraftKings")
    under = _q(quotes, TOTAL, "under", "espn:DraftKings")
    assert over is not None and under is not None
    assert over.line == 220.5 and under.line == 220.5
    assert over.side == "over" and under.side == "under"
    assert 0.0 < over.devigged_prob < 1.0


def test_malformed_omitted():
    quotes = quotes_from_aggregate("nba", agg=_AGG)
    ids = {q.game_id for q in quotes}
    # 402 (no home name) and 403 (prices not a dict) are fully dropped.
    assert "402" not in ids and "403" not in ids
    assert ids == {"401", "404"}
    # event 404: away moneyline unpriced -> that quote omitted (never fabricated)
    assert _q(quotes, MONEYLINE, "away", "espn:BetMGM") is None
    # event 404: home moneyline IS priced -> emitted, but one-sided -> no devig
    home_ml = _q(quotes, MONEYLINE, "home", "espn:BetMGM")
    assert home_ml is not None and home_ml.odds == 1.70
    assert home_ml.devigged_prob is None
    # event 404 spread: home leg has no line (omitted); away leg has line+odds
    assert _q(quotes, SPREAD, "home", "espn:BetMGM") is None
    away_sp = _q(quotes, SPREAD, "away", "espn:BetMGM")
    assert away_sp is not None and away_sp.line == 4.5
    assert away_sp.devigged_prob is None  # one-sided -> no devig


def test_unavailable_slate_empty():
    assert quotes_from_aggregate("nba", agg={"status": "unavailable"}) == []
    assert quotes_from_aggregate("nba", agg={}) == []


def test_now_fallback_when_no_as_of():
    agg = {"sport": "nba", "status": "ok", "events": _AGG["events"][:1]}
    now = datetime(2026, 6, 18, 21, 0, 0, tzinfo=timezone.utc)
    quotes = quotes_from_aggregate("nba", agg=agg, now=now)
    assert quotes and all(
        q.captured_at == "2026-06-18T21:00:00+00:00" for q in quotes)


# ---------------------------------------------------------------------------
# CLOCK-TRUST GUARD (captured_at_suspect) -- go-live defect A
# ---------------------------------------------------------------------------

def test_captured_at_not_suspect_when_now_agrees_with_as_of():
    """Happy path: *now* (the poller's own clock, read moments after as_of was
    stamped) agrees with as_of within the window -> never suspect."""
    now = datetime(2026, 6, 18, 20, 2, 0, tzinfo=timezone.utc)  # 2 min after as_of
    quotes = quotes_from_aggregate("nba", agg=_AGG, now=now)
    assert quotes and all(q.captured_at_suspect is False for q in quotes)


def test_captured_at_suspect_on_clock_divergence():
    """A poller-clock step: *now* disagrees with the slate's as_of by more than
    CAPTURED_AT_SUSPECT_WINDOW_SEC (5 min) -> every quote from this tick is
    stamped captured_at_suspect=True, but captured_at itself is unchanged
    (still the honest as_of -- we never fabricate a different capture time)."""
    now = datetime(2026, 6, 18, 21, 0, 0, tzinfo=timezone.utc)  # 1h after as_of
    quotes = quotes_from_aggregate("nba", agg=_AGG, now=now)
    assert quotes and all(q.captured_at_suspect is True for q in quotes)
    assert all(q.captured_at == _CAPTURED for q in quotes)


def test_captured_at_suspect_just_inside_window_is_not_suspect():
    now = datetime(2026, 6, 18, 20, 4, 59, tzinfo=timezone.utc)  # 299s after as_of
    quotes = quotes_from_aggregate("nba", agg=_AGG, now=now)
    assert quotes and all(q.captured_at_suspect is False for q in quotes)


def test_captured_at_suspect_just_outside_window_is_suspect():
    now = datetime(2026, 6, 18, 20, 5, 1, tzinfo=timezone.utc)  # 301s after as_of
    quotes = quotes_from_aggregate("nba", agg=_AGG, now=now)
    assert quotes and all(q.captured_at_suspect is True for q in quotes)


def test_captured_at_suspect_on_unparseable_as_of():
    agg = dict(_AGG)
    agg["as_of"] = "not-a-timestamp"
    quotes = quotes_from_aggregate("nba", agg=agg)
    assert quotes and all(q.captured_at_suspect is True for q in quotes)
    assert all(q.captured_at == "not-a-timestamp" for q in quotes)  # never fabricated


def test_captured_at_suspect_never_fires_on_now_fallback():
    """No as_of at all -> captured_at is stamped from *now* itself, so there is
    nothing to disagree with -- never suspect regardless of *now*."""
    agg = {"sport": "nba", "status": "ok", "events": _AGG["events"][:1]}
    now = datetime(2026, 6, 18, 21, 0, 0, tzinfo=timezone.utc)
    quotes = quotes_from_aggregate("nba", agg=agg, now=now)
    assert quotes and all(q.captured_at_suspect is False for q in quotes)
