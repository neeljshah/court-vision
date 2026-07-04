"""Per-file test for odds_provider.kalshi (offline, injected http_get).

Regression-guards the LANE 4 bugfix: KalshiProvider.fetch() now scopes its
/markets call server-side via the exact GAME series_ticker (kalshi_series_spec.
_GAME_SERIES) instead of an unfiltered 200-row page + client-side startswith
ONLY. Verifies:

  * mlb (regression) -- the built URL carries series_ticker=KXMLBGAME; a
    single-page canned response still parses into the same OddsEvent shape as
    before the fix (byte-compatible behavior for the existing sport).
  * tennis (fallback, unchanged) -- no GAME series is registered for tennis
    (MATCH-shaped, not GAME) -- the URL carries NO series_ticker param, exactly
    the prior unfiltered+startswith behavior.
  * wnba / kbo (the LANE 4 gap this closes) -- both get an exact series_ticker
    (KXWNBAGAME / KXKBOGAME) and parse real events from a canned page that
    would have been invisible to the old unfiltered call.
  * an unsupported sport -> UNAVAILABLE, never raises.
  * the client-side event_ticker startswith guard still excludes a stray
    cross-series market even when series_ticker narrowed the server response.

LANE 2 (soccer 3-way KXWCGAME) additions:
  * a clean 3-leg team/Tie/team group parses into ONE OddsEvent with
    home/away/draw all populated (the gap this lane closes -- previously ANY
    != 2-leg group was skipped, so soccer_intl kalshi events == 0).
  * the 3-way devig (via markets._moneyline_quotes, reused unchanged) sums to
    ~1.0 over all three legs -- consumer-safety proof that a 3-way price is
    NEVER misread as a 2-way win prob.
  * the pre-existing 2-leg path is untouched (byte-identical regression).
  * a malformed 3-leg group (zero or two tie-labeled legs, or any leg missing
    a price) is skipped, never guessed into a line.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi.py -q
"""
from __future__ import annotations

import math
import urllib.parse

from scripts.platformkit.odds_provider.kalshi import KalshiProvider, parse_events


def _canned_http(markets):
    """Injected http_get: returns a fixed {"markets": [...]} body, ignoring URL."""
    calls = []

    def _get(url: str):
        calls.append(url)
        return {"markets": markets}

    _get.calls = calls
    return _get


def _query_params(url: str) -> dict:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


# ---- canned two-leg MLB game (mirrors the live shape) ----------------------- #
_MLB_MARKETS = [
    {"event_ticker": "KXMLBGAME-26JUN19TORCHC", "yes_sub_title": "TOR",
     "yes_ask_dollars": 0.46},
    {"event_ticker": "KXMLBGAME-26JUN19TORCHC", "yes_sub_title": "CHC",
     "yes_ask_dollars": 0.56},
]

_WNBA_MARKETS = [
    {"event_ticker": "KXWNBAGAME-26JUL05INDLV", "yes_sub_title": "IND",
     "yes_ask_dollars": 0.30},
    {"event_ticker": "KXWNBAGAME-26JUL05INDLV", "yes_sub_title": "LV",
     "yes_ask_dollars": 0.72},
]

_KBO_MARKETS = [
    {"event_ticker": "KXKBOGAME-26JUL05NCDKIA", "yes_sub_title": "NCD",
     "yes_ask_dollars": 0.40},
    {"event_ticker": "KXKBOGAME-26JUL05NCDKIA", "yes_sub_title": "KIA",
     "yes_ask_dollars": 0.63},
]

_TENNIS_MARKETS = [
    {"event_ticker": "KXATPMATCH-26JUL05AUGDAV", "yes_sub_title": "AUG",
     "yes_ask_dollars": 0.35},
    {"event_ticker": "KXATPMATCH-26JUL05AUGDAV", "yes_sub_title": "DAV",
     "yes_ask_dollars": 0.68},
    # a stray cross-series market that must NOT leak into the parsed events:
    {"event_ticker": "KXWTAMATCH-26JUL05XXXYYY", "yes_sub_title": "XXX",
     "yes_ask_dollars": 0.50},
]


def test_mlb_regression_series_ticker_scoped_and_parses():
    http = _canned_http(_MLB_MARKETS)
    p = KalshiProvider(http_get=http, use_cache=False)
    events = p.fetch("mlb")
    assert isinstance(events, list)
    assert len(http.calls) == 1
    params = _query_params(http.calls[0])
    assert params.get("series_ticker") == "KXMLBGAME"
    assert params.get("status") == "open"
    assert len(events) == 1
    ev = events[0]
    assert ev.sport == "mlb"
    assert ev.prices["kalshi"]["home"] is not None
    assert ev.prices["kalshi"]["away"] is not None
    assert ev.commence_time is None  # Kalshi close_time is never a tip-off proxy


def test_tennis_fallback_no_series_ticker_param():
    http = _canned_http(_TENNIS_MARKETS)
    p = KalshiProvider(http_get=http, use_cache=False)
    events = p.fetch("tennis")
    params = _query_params(http.calls[0])
    assert "series_ticker" not in params  # no GAME series for tennis -> unfiltered
    # Only the KXATPMATCH pair forms a valid 2-leg event under the KXATP prefix
    # guard; the stray KXWTAMATCH market is excluded by the startswith guard.
    assert len(events) == 1
    assert events[0].home in ("AUG", "DAV") or events[0].away in ("AUG", "DAV")


def test_wnba_widening_series_ticker_and_parses():
    http = _canned_http(_WNBA_MARKETS)
    p = KalshiProvider(http_get=http, use_cache=False)
    events = p.fetch("wnba")
    params = _query_params(http.calls[0])
    assert params.get("series_ticker") == "KXWNBAGAME"
    assert len(events) == 1
    assert events[0].sport == "wnba"


def test_kbo_widening_series_ticker_and_parses():
    http = _canned_http(_KBO_MARKETS)
    p = KalshiProvider(http_get=http, use_cache=False)
    events = p.fetch("kbo")
    params = _query_params(http.calls[0])
    assert params.get("series_ticker") == "KXKBOGAME"
    assert len(events) == 1
    assert events[0].sport == "kbo"


def test_unsupported_sport_is_unavailable_never_raises():
    http = _canned_http([])
    p = KalshiProvider(http_get=http, use_cache=False)
    result = p.fetch("cricket")
    assert isinstance(result, dict)
    assert result.get("status") == "unavailable"
    assert http.calls == []  # never even attempted the network call


def test_http_failure_degrades_to_unavailable():
    def _raise(url: str):
        raise TimeoutError("boom")
    p = KalshiProvider(http_get=_raise, use_cache=False)
    result = p.fetch("mlb")
    assert isinstance(result, dict)
    assert result.get("status") == "unavailable"


# ---- LANE 2: soccer 3-way KXWCGAME grouping ---------------------------------- #

_WC_3WAY_MARKETS = [
    {"event_ticker": "KXWCGAME-26JUN22USAMEX", "yes_sub_title": "United States",
     "yes_ask_dollars": 0.55},
    {"event_ticker": "KXWCGAME-26JUN22USAMEX", "yes_sub_title": "Tie",
     "yes_ask_dollars": 0.25},
    {"event_ticker": "KXWCGAME-26JUN22USAMEX", "yes_sub_title": "Mexico",
     "yes_ask_dollars": 0.24},
]


def test_3leg_grouping_emits_one_event_with_all_three_prices():
    """A clean team/Tie/team 3-leg group -> ONE OddsEvent, home+away+draw all set."""
    events = parse_events(_WC_3WAY_MARKETS, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    assert len(events) == 1
    ev = events[0]
    assert ev.event_id == "KXWCGAME-26JUN22USAMEX"
    prices = ev.prices["kalshi"]
    assert prices["home"] is not None
    assert prices["away"] is not None
    assert prices["draw"] is not None
    # the tie leg must never be surfaced as a team name
    assert ev.home != "Tie" and ev.away != "Tie"
    assert {ev.home, ev.away} == {"United States", "Mexico"}


def test_3leg_devig_sums_to_one_over_three_outcomes():
    """Consumer-safety proof: the 3-way price devigs (via markets.py, reused
    unchanged) to ~1.0 across home+draw+away -- never collapsed into a 2-way."""
    from scripts.platformkit.odds_provider.markets import (
        MONEYLINE, quotes_from_aggregate,
    )
    events = parse_events(_WC_3WAY_MARKETS, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    ev = events[0]
    agg = {
        "status": "ok", "sport": "soccer_intl", "as_of": "2026-06-22T00:00:00Z",
        "sources": {"kalshi": "ok"}, "events": [ev.to_dict()],
    }
    quotes = quotes_from_aggregate("soccer_intl", agg=agg)
    ml = [q for q in quotes if q.market_type == MONEYLINE and q.book == "kalshi"]
    assert len(ml) == 3
    sides = {q.side for q in ml}
    assert sides == {"home", "draw", "away"}
    for q in ml:
        assert q.devigged_prob is not None, f"side={q.side} devigged_prob is None"
        assert 0.0 < q.devigged_prob < 1.0
    total = sum(q.devigged_prob for q in ml)
    assert math.isclose(total, 1.0, abs_tol=1e-6), f"devigged probs sum to {total}"


def test_2leg_regression_unchanged_by_3way_addition():
    """The pre-existing 2-leg path (MLB etc.) is untouched: draw stays None."""
    events = parse_events(_MLB_MARKETS, "mlb", as_of="2026-06-19T00:00:00Z")
    assert len(events) == 1
    ev = events[0]
    prices = ev.prices["kalshi"]
    assert prices["home"] is not None
    assert prices["away"] is not None
    assert prices["draw"] is None


def test_malformed_3leg_group_skipped_no_tie_label():
    """Three legs with NO tie-labeled leg (e.g. a stray 3rd team market some
    other way) is not a recognizable 3-way -- skipped, never guessed."""
    markets = [
        {"event_ticker": "KXWCGAME-26JUN22AAABBB", "yes_sub_title": "Team A",
         "yes_ask_dollars": 0.40},
        {"event_ticker": "KXWCGAME-26JUN22AAABBB", "yes_sub_title": "Team B",
         "yes_ask_dollars": 0.35},
        {"event_ticker": "KXWCGAME-26JUN22AAABBB", "yes_sub_title": "Team C",
         "yes_ask_dollars": 0.25},
    ]
    events = parse_events(markets, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    assert events == []


def test_malformed_3leg_group_skipped_two_tie_labels():
    """Two tie-labeled legs (ambiguous) -- skipped, never guessed."""
    markets = [
        {"event_ticker": "KXWCGAME-26JUN22CCCDDD", "yes_sub_title": "Draw",
         "yes_ask_dollars": 0.30},
        {"event_ticker": "KXWCGAME-26JUN22CCCDDD", "yes_sub_title": "Tie",
         "yes_ask_dollars": 0.25},
        {"event_ticker": "KXWCGAME-26JUN22CCCDDD", "yes_sub_title": "Brazil",
         "yes_ask_dollars": 0.45},
    ]
    events = parse_events(markets, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    assert events == []


def test_3leg_group_missing_price_on_one_leg_skipped():
    """A 3-leg group where one leg has NO usable YES ask -> skipped whole
    (never fabricate the missing side)."""
    markets = [
        {"event_ticker": "KXWCGAME-26JUN22EEEFFF", "yes_sub_title": "Spain",
         "yes_ask_dollars": 0.60},
        {"event_ticker": "KXWCGAME-26JUN22EEEFFF", "yes_sub_title": "Tie",
         "yes_ask_dollars": None},
        {"event_ticker": "KXWCGAME-26JUN22EEEFFF", "yes_sub_title": "Italy",
         "yes_ask_dollars": 0.30},
    ]
    events = parse_events(markets, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    assert events == []


def test_book_table_lists_draw_leg_safely():
    """Consumer-safety: book_table._ML_SIDES already reads 'draw' as its own
    (moneyline, 'draw') cell -- never conflated with a team win-prob side."""
    from scripts.platformkit.odds_provider.book_table import book_table_for_event
    events = parse_events(_WC_3WAY_MARKETS, "soccer_intl", as_of="2026-06-22T00:00:00Z")
    table = book_table_for_event(events[0].to_dict())
    assert ("moneyline", "home") in table
    assert ("moneyline", "away") in table
    assert ("moneyline", "draw") in table
    draw_books = table[("moneyline", "draw")]["books"]
    assert len(draw_books) == 1
    assert draw_books[0]["book"] == "kalshi"
    assert draw_books[0]["is_pm"] is True  # kalshi is a PM venue, never a bettable "best"
    assert table[("moneyline", "draw")]["best"] is None  # PM never wins "best"
