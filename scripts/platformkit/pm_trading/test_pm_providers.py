"""test_pm_providers.py -- per-file tests for pm_providers module.

Acceptance contract (workstream W4-pm-paper-real-trades):
  1. KalshiPMProvider.fetch_markets() returns shaped rows with market_id, sport,
     home, away, pm_prob in (0,1), venue="kalshi", no $ keys.
  2. PolymarketPMProvider.fetch_markets() returns shaped rows; binary rows carry
     binary_title / binary_yes_prob and venue="polymarket".
  3. Both providers return [] (honest empty) when the API body is empty or when
     the network raises -- never fabricate rows.
  4. _default_pm_providers() returns exactly 2 PMProvider instances.
  5. Futures/championship binary rows from PolymarketPMProvider carry
     binary_title but active_pairs Path-4 rejects them (tested in
     test_live_feed.py; here we confirm the binary shape is correct).

Run:
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/pm_trading/test_pm_providers.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_HERE), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pm_providers import (  # noqa: E402
    PMProvider, KalshiPMProvider, PolymarketPMProvider,
    _default_pm_providers, _odds_event_to_pm_market, _single_binary_to_pm_market,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({
    "dollar_pnl", "pnl_usd", "dollar", "dollars", "pnl", "roi",
    "profit", "dollar_stake", "dollar_value", "net_pnl",
    "realized_pnl", "unrealized_pnl",
})

# ---------------------------------------------------------------------------
# Canned API stubs
# ---------------------------------------------------------------------------

_KALSHI_MLB_BODY = {
    "markets": [
        {
            "ticker": "KXMLB-2026-NYY-T",
            "event_ticker": "KXMLB-2026-NYY-BOS-20260620",
            "yes_sub_title": "New York Yankees",
            "yes_ask_dollars": 0.60,
            "yes_bid_dollars": 0.58,
        },
        {
            "ticker": "KXMLB-2026-BOS-T",
            "event_ticker": "KXMLB-2026-NYY-BOS-20260620",
            "yes_sub_title": "Boston Red Sox",
            "yes_ask_dollars": 0.42,
            "yes_bid_dollars": 0.40,
        },
    ]
}

_KALSHI_EMPTY_BODY = {"markets": []}

_POLY_NBA_BODY = [
    {
        "id": "poly-nba-celtics-heat",
        "slug": "nba-2026-celtics-vs-heat",
        "question": "NBA: Celtics vs Heat -- who wins?",
        "outcomes": json.dumps(["Celtics", "Heat"]),
        "outcomePrices": json.dumps(["0.57", "0.43"]),
        "startDate": "2026-06-20T19:00:00Z",
    }
]

_POLY_BINARY_GAME_BODY = [
    {
        "id": "poly-nba-celtics-win-tonight",
        "slug": "nba-will-boston-celtics-win-tonight",
        "question": "Will the Boston Celtics win tonight?",
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.65", "0.35"]),
        "startDate": "2026-06-20T19:00:00Z",
    }
]

_POLY_EMPTY_BODY = []


def _http_always(body):
    """Return a stub http_get that always returns *body*."""
    def _http(url):  # noqa: ARG001
        return body
    return _http


def _http_raises():
    """Return a stub http_get that always raises (simulates offline)."""
    def _http(url):  # noqa: ARG001
        raise RuntimeError("network error")
    return _http


# ---------------------------------------------------------------------------
# Shared assertion helpers
# ---------------------------------------------------------------------------

def _assert_no_dollar_keys(row: dict) -> None:
    bad = _DOLLAR_KEYS & set(row.keys())
    assert not bad, "$ key(s) in PM row: %s" % sorted(bad)


def _assert_two_leg_row_shape(row: dict, sport: str = "") -> None:
    """Assert a two-leg market row (home/away explicit, pm_prob in (0,1))."""
    assert "market_id" in row, "market_id missing"
    assert "sport" in row, "sport missing"
    if sport:
        assert row["sport"] == sport, "sport mismatch: %r != %r" % (row["sport"], sport)
    assert "home" in row and row["home"] is not None, "home missing/None"
    assert "away" in row and row["away"] is not None, "away missing/None"
    assert "pm_prob" in row, "pm_prob missing"
    assert 0.0 < float(row["pm_prob"]) < 1.0, "pm_prob out of (0,1): %s" % row["pm_prob"]
    _assert_no_dollar_keys(row)


# ---------------------------------------------------------------------------
# _odds_event_to_pm_market unit tests
# ---------------------------------------------------------------------------

def test_odds_event_to_pm_market_valid():
    """_odds_event_to_pm_market with a well-formed OddsEvent returns a shaped row."""
    from scripts.platformkit.odds_provider.base import OddsEvent
    ev = OddsEvent(
        event_id="EVT-1", sport="nba", home="Lakers", away="Clippers",
        commence_time=None,
        prices={"kalshi": {"home": 1.8182, "away": 2.2222, "draw": None}},
        source="kalshi",
    )
    row = _odds_event_to_pm_market(ev, "nba", venue="kalshi")
    assert row is not None, "_odds_event_to_pm_market returned None for valid event"
    assert row["market_id"] == "EVT-1"
    assert row["sport"] == "nba"
    assert row["home"] == "Lakers"
    assert row["away"] == "Clippers"
    assert 0.0 < row["pm_prob"] < 1.0
    assert abs(row["pm_prob"] - 0.55) < 0.01  # 1/1.8182 ~ 0.55
    assert row.get("venue") == "kalshi"
    _assert_no_dollar_keys(row)


def test_odds_event_to_pm_market_no_prices_returns_none():
    """_odds_event_to_pm_market returns None when prices are absent."""
    from scripts.platformkit.odds_provider.base import OddsEvent
    ev = OddsEvent(
        event_id="EVT-2", sport="nba", home="A", away="B",
        commence_time=None, prices={}, source="kalshi",
    )
    assert _odds_event_to_pm_market(ev, "nba") is None


def test_odds_event_to_pm_market_stamps_venue():
    """venue kwarg is stamped onto the returned row."""
    from scripts.platformkit.odds_provider.base import OddsEvent
    ev = OddsEvent(
        event_id="EVT-3", sport="mlb", home="NYY", away="BOS",
        commence_time=None,
        prices={"kalshi": {"home": 1.67, "away": 2.5, "draw": None}},
        source="kalshi",
    )
    row = _odds_event_to_pm_market(ev, "mlb", venue="kalshi")
    assert row is not None
    assert row.get("venue") == "kalshi"


def test_single_binary_to_pm_market_valid():
    """_single_binary_to_pm_market returns a shaped partial row."""
    row = _single_binary_to_pm_market(
        "M-BIN-1", "nba", "Will the Celtics win tonight?", 0.65,
        venue="polymarket",
    )
    assert row is not None
    assert row["market_id"] == "M-BIN-1"
    assert row["sport"] == "nba"
    assert row["home"] is None
    assert row["away"] is None
    assert row["pm_prob"] is None
    assert "Will the Celtics win tonight?" in row["binary_title"]
    assert abs(row["binary_yes_prob"] - 0.65) < 1e-9
    assert row.get("venue") == "polymarket"
    _assert_no_dollar_keys(row)


def test_single_binary_to_pm_market_rejects_out_of_range():
    """yes_prob outside (0, 1) causes _single_binary_to_pm_market to return None."""
    assert _single_binary_to_pm_market("M", "nba", "Will Celtics win?", 0.0) is None
    assert _single_binary_to_pm_market("M", "nba", "Will Celtics win?", 1.0) is None
    assert _single_binary_to_pm_market("M", "nba", "Will Celtics win?", 1.5) is None


# ---------------------------------------------------------------------------
# KalshiPMProvider
# ---------------------------------------------------------------------------

def test_kalshi_provider_returns_shaped_rows():
    """KalshiPMProvider with stubbed MLB body returns >= 1 shaped market row."""
    prov = KalshiPMProvider(sports=["mlb"],
                             http_get=_http_always(_KALSHI_MLB_BODY))
    rows = prov.fetch_markets()
    assert len(rows) >= 1, "expected >= 1 row from canned Kalshi MLB body"
    for row in rows:
        _assert_two_leg_row_shape(row, sport="mlb")


def test_kalshi_provider_stamps_venue_kalshi():
    """Every row from KalshiPMProvider must carry venue='kalshi'."""
    prov = KalshiPMProvider(sports=["mlb"],
                             http_get=_http_always(_KALSHI_MLB_BODY))
    rows = prov.fetch_markets()
    for row in rows:
        assert row.get("venue") == "kalshi", (
            "KalshiPMProvider row must carry venue='kalshi'; got %r" % row.get("venue")
        )


def test_kalshi_provider_honest_empty_on_empty_body():
    """KalshiPMProvider returns [] honestly when the API body has no markets."""
    prov = KalshiPMProvider(sports=["mlb"],
                             http_get=_http_always(_KALSHI_EMPTY_BODY))
    assert prov.fetch_markets() == [], "expected honest [] for empty Kalshi body"


def test_kalshi_provider_degrades_on_network_error():
    """KalshiPMProvider returns [] (never raises) when http_get throws."""
    prov = KalshiPMProvider(sports=["mlb"], http_get=_http_raises())
    assert prov.fetch_markets() == [], "expected [] on network error"


def test_kalshi_provider_no_dollar_keys():
    """No dollar/pnl/roi key appears in KalshiPMProvider rows."""
    prov = KalshiPMProvider(sports=["mlb"],
                             http_get=_http_always(_KALSHI_MLB_BODY))
    for row in prov.fetch_markets():
        _assert_no_dollar_keys(row)


# ---------------------------------------------------------------------------
# PolymarketPMProvider
# ---------------------------------------------------------------------------

def test_polymarket_provider_returns_shaped_rows_for_two_leg():
    """PolymarketPMProvider with stubbed NBA body returns >= 1 shaped two-leg row."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_NBA_BODY))
    rows = prov.fetch_markets()
    two_leg = [r for r in rows if r.get("home") is not None]
    assert len(two_leg) >= 1, "expected >= 1 two-leg row from Polymarket NBA body"
    for row in two_leg:
        _assert_two_leg_row_shape(row)


def test_polymarket_provider_stamps_venue_polymarket():
    """Every row from PolymarketPMProvider must carry venue='polymarket'."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_NBA_BODY))
    rows = prov.fetch_markets()
    for row in rows:
        assert row.get("venue") == "polymarket", (
            "PolymarketPMProvider row must carry venue='polymarket'; got %r"
            % row.get("venue")
        )


def test_polymarket_provider_binary_does_not_produce_yesno_home_away():
    """A YES/NO binary must NOT produce home='Yes'/away='No' rows."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_BINARY_GAME_BODY))
    rows = prov.fetch_markets()
    for row in rows:
        assert str(row.get("home", "")).lower() != "yes", (
            "YES/NO binary mis-shaped as two-leg: home='Yes'"
        )
        assert str(row.get("away", "")).lower() != "no", (
            "YES/NO binary mis-shaped as two-leg: away='No'"
        )


def test_polymarket_provider_binary_row_shape():
    """A YES/NO binary emits a single-binary row: binary_title set, home/away=None."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_BINARY_GAME_BODY))
    rows = prov.fetch_markets()
    binary_rows = [r for r in rows if r.get("binary_title")]
    assert len(binary_rows) >= 1, "expected >= 1 binary row"
    b = binary_rows[0]
    assert b["home"] is None, "binary row home must be None"
    assert b["away"] is None, "binary row away must be None"
    assert b["pm_prob"] is None, "binary row pm_prob must be None"
    assert 0.0 < b["binary_yes_prob"] < 1.0
    assert b.get("venue") == "polymarket"
    _assert_no_dollar_keys(b)


def test_polymarket_provider_honest_empty_on_empty_body():
    """PolymarketPMProvider returns [] honestly when the API body is empty."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_EMPTY_BODY))
    assert prov.fetch_markets() == [], "expected honest [] for empty Polymarket body"


def test_polymarket_provider_degrades_on_network_error():
    """PolymarketPMProvider returns [] (never raises) when http_get throws."""
    prov = PolymarketPMProvider(sports=["nba"], http_get=_http_raises())
    assert prov.fetch_markets() == [], "expected [] on Polymarket network error"


def test_polymarket_provider_no_dollar_keys():
    """No dollar/pnl/roi key appears in PolymarketPMProvider rows."""
    prov = PolymarketPMProvider(sports=["nba"],
                                 http_get=_http_always(_POLY_NBA_BODY))
    for row in prov.fetch_markets():
        _assert_no_dollar_keys(row)


# ---------------------------------------------------------------------------
# _default_pm_providers
# ---------------------------------------------------------------------------

def test_default_pm_providers_returns_two_instances():
    """_default_pm_providers() returns exactly 2 PMProvider instances."""
    providers = _default_pm_providers()
    assert len(providers) == 2, "expected 2 providers; got %d" % len(providers)
    assert all(isinstance(p, PMProvider) for p in providers)
    assert isinstance(providers[0], KalshiPMProvider)
    assert isinstance(providers[1], PolymarketPMProvider)


def test_default_pm_providers_empty_when_both_feeds_empty():
    """When both feeds return empty bodies, all_rows == [] (honest empty)."""
    providers = [
        KalshiPMProvider(sports=["nba"],
                         http_get=_http_always(_KALSHI_EMPTY_BODY)),
        PolymarketPMProvider(sports=["nba"],
                              http_get=_http_always(_POLY_EMPTY_BODY)),
    ]
    all_rows = []
    for p in providers:
        all_rows.extend(p.fetch_markets())
    assert all_rows == [], "expected [] when both feeds are empty (honest empty)"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspect
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and inspect.isfunction(v)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
            passed += 1
        except Exception as exc:
            print("FAIL", name, "->", exc)
    print("%d/%d green" % (passed, len(tests)))
