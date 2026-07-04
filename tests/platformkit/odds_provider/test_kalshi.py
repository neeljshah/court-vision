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

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi.py -q
"""
from __future__ import annotations

import urllib.parse

from scripts.platformkit.odds_provider.kalshi import KalshiProvider


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
