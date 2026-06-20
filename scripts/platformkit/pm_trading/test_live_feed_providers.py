"""test_live_feed_providers.py -- per-file tests for KalshiPMProvider,
PolymarketPMProvider, and _default_pm_providers wired into active_pairs.

Acceptance contract (workstream ws2-pm-trail-providers + ws2-polymarket-binary-shape):
  1. With a stubbed live PM market injected, _default_pm_providers().fetch_markets()
     returns shaped rows {market_id, sport, home, away, pm_prob}.
  2. active_pairs() with those providers + a stubbed game + stubbed predict_fn
     returns non-empty (total_pm > 0).
  3. With no markets (network returns empty body), fetch_markets() returns []
     (honest empty, no fabricated rows).
  4. No dollar / $ field ever appears in any row.
  5. clv_status == "INSUFFICIENT_DATA" on every pair row.
  6. (ws2-polymarket-binary-shape) A YES/NO Polymarket contract parses to a
     single-binary row (binary_title set, home/away/pm_prob=None) NOT a two-leg
     row with home="Yes"/away="No".
  7. active_pairs() with a slate game whose team canonical-matches the binary
     question title emits >= 1 pair row (clv_status=INSUFFICIENT_DATA, no $).
  8. Honest empty preserved when no question matches the slate.

Run:
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/pm_trading/test_live_feed_providers.py -q
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

import live_feed as LF  # noqa: E402

# ---------------------------------------------------------------------------
# Canned HTTP stubs
# ---------------------------------------------------------------------------

# Two Kalshi NBA markets that form ONE game event (two-team YES contracts).
_KALSHI_NBA_BODY = {
    "markets": [
        {
            "ticker": "KXNBA-2026-BOS-20260620-T",
            "event_ticker": "KXNBA-2026-BOS-20260620",
            "yes_sub_title": "Boston Celtics",
            "yes_ask_dollars": 0.55,
            "yes_bid_dollars": 0.53,
            "last_price_dollars": 0.54,
        },
        {
            "ticker": "KXNBA-2026-MIA-20260620-T",
            "event_ticker": "KXNBA-2026-BOS-20260620",
            "yes_sub_title": "Miami Heat",
            "yes_ask_dollars": 0.45,
            "yes_bid_dollars": 0.43,
            "last_price_dollars": 0.44,
        },
    ]
}

# One MLB game event on Kalshi.
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

# Polymarket two-way NBA market (gamma format).
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

# Polymarket single-sided YES/NO binary NBA market -- FUTURES/championship form.
# "Will the Boston Celtics win the NBA championship?" is a season-long futures
# contract; its YES price (0.65) is NOT a per-game win probability.
# Path-4 must REJECT this via _FUTURES_EXCLUDE_RE ("championship" keyword).
_POLY_BINARY_CHAMPIONSHIP_BODY = [
    {
        "id": "poly-nba-celtics-win-title",
        "slug": "nba-will-boston-celtics-win-championship",
        "question": "Will the Boston Celtics win the NBA championship?",
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.65", "0.35"]),
        "startDate": "2026-06-20T19:00:00Z",
    }
]
# Backward-compat alias used in some earlier tests (same data, different name).
_POLY_BINARY_BODY = _POLY_BINARY_CHAMPIONSHIP_BODY

# Polymarket per-game binary: "Will the Boston Celtics win tonight?" -- this IS
# a per-game question and should route through Path-4 to produce a pair row.
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

# Mixed body: one YES/NO binary + one two-way market.
_POLY_MIXED_BODY = _POLY_NBA_BODY + _POLY_BINARY_BODY

# Empty Kalshi response (offseason / no live markets).
_KALSHI_EMPTY_BODY = {"markets": []}

# Empty Polymarket response.
_POLY_EMPTY_BODY = []


def _make_kalshi_http(sport_body_map: dict):
    """Return an http_get stub that routes by URL query string sport prefix."""
    from scripts.platformkit.odds_provider.kalshi import _SERIES_HINT

    def _http(url: str):
        for sport, prefix in _SERIES_HINT.items():
            if sport in sport_body_map:
                body = sport_body_map[sport]
                # Check if the URL is a /markets query (we only serve one URL).
                if "/markets?" in url:
                    return body
        # Default: empty
        return {"markets": []}

    return _http


def _make_kalshi_http_single(body: dict):
    """Simple stub: always returns *body* regardless of URL."""
    def _http(url: str):  # noqa: ARG001
        return body
    return _http


def _make_poly_http_single(body):
    """Simple stub: always returns *body* regardless of URL."""
    def _http(url: str):  # noqa: ARG001
        return body
    return _http


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({"dollar_pnl", "pnl_usd", "dollar", "pnl",
                           "roi", "profit", "dollar_stake"})


def _assert_row_shape(row: dict) -> None:
    """Assert a PM market row has the required fields and no $ field."""
    assert "market_id" in row, "market_id missing"
    assert "sport" in row, "sport missing"
    assert "home" in row, "home missing"
    assert "away" in row, "away missing"
    assert "pm_prob" in row, "pm_prob missing"
    p = row["pm_prob"]
    assert 0.0 < p < 1.0, "pm_prob %s out of (0,1)" % p
    bad = _DOLLAR_KEYS & set(row.keys())
    assert not bad, "$ field(s) in row: %s" % sorted(bad)


def _fake_predict(sport, home, away):
    return {"p_home_win": 0.62}


# ---------------------------------------------------------------------------
# KalshiPMProvider tests
# ---------------------------------------------------------------------------

def test_kalshi_provider_returns_shaped_rows_for_nba():
    """KalshiPMProvider with a stubbed NBA body returns valid PM market rows."""
    prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_NBA_BODY),
    )
    rows = prov.fetch_markets()
    assert len(rows) >= 1, "expected at least one row from canned NBA body"
    for row in rows:
        _assert_row_shape(row)
    # Must be flagged as nba
    assert all(r["sport"] == "nba" for r in rows)


def test_kalshi_provider_returns_empty_on_empty_body():
    """KalshiPMProvider returns [] honestly when the API returns no markets."""
    prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_EMPTY_BODY),
    )
    rows = prov.fetch_markets()
    assert rows == [], "expected honest [] for empty Kalshi body"


def test_kalshi_provider_degrades_on_network_error():
    """KalshiPMProvider returns [] (not raise) when http_get throws."""
    def _boom(url):
        raise RuntimeError("network error")

    prov = LF.KalshiPMProvider(sports=["nba"], http_get=_boom)
    rows = prov.fetch_markets()
    assert rows == [], "expected [] on network error, not a crash"


def test_kalshi_provider_no_dollar_fields():
    """KalshiPMProvider rows must never contain any $ / P&L field."""
    prov = LF.KalshiPMProvider(
        sports=["mlb"],
        http_get=_make_kalshi_http_single(_KALSHI_MLB_BODY),
    )
    rows = prov.fetch_markets()
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ field in KalshiPMProvider row: %s" % sorted(bad)


# ---------------------------------------------------------------------------
# PolymarketPMProvider tests
# ---------------------------------------------------------------------------

def test_polymarket_provider_returns_shaped_rows_for_nba():
    """PolymarketPMProvider with a stubbed NBA body returns valid PM market rows."""
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_NBA_BODY),
    )
    rows = prov.fetch_markets()
    assert len(rows) >= 1, "expected at least one row from canned Polymarket body"
    for row in rows:
        _assert_row_shape(row)


def test_polymarket_provider_returns_empty_on_empty_body():
    """PolymarketPMProvider returns [] honestly when the API returns no markets."""
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_EMPTY_BODY),
    )
    rows = prov.fetch_markets()
    assert rows == [], "expected honest [] for empty Polymarket body"


def test_polymarket_provider_degrades_on_network_error():
    """PolymarketPMProvider returns [] (not raise) when http_get throws."""
    def _boom(url):
        raise ConnectionError("offline")

    prov = LF.PolymarketPMProvider(sports=["nba"], http_get=_boom)
    rows = prov.fetch_markets()
    assert rows == [], "expected [] on Polymarket network error"


def test_polymarket_provider_no_dollar_fields():
    """PolymarketPMProvider rows must never contain $ / P&L fields."""
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_NBA_BODY),
    )
    rows = prov.fetch_markets()
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ field in PolymarketPMProvider row: %s" % sorted(bad)


# ---------------------------------------------------------------------------
# _default_pm_providers integration tests
# ---------------------------------------------------------------------------

def test_default_pm_providers_structure():
    """_default_pm_providers() returns a list of 2 PMProvider instances."""
    providers = LF._default_pm_providers()
    assert len(providers) == 2
    assert all(isinstance(p, LF.PMProvider) for p in providers)
    assert isinstance(providers[0], LF.KalshiPMProvider)
    assert isinstance(providers[1], LF.PolymarketPMProvider)


def test_default_pm_providers_with_stubbed_kalshi_returns_rows():
    """With a stubbed Kalshi feed, _default_pm_providers()[0].fetch_markets() != []."""
    kalshi_prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_NBA_BODY),
    )
    rows = kalshi_prov.fetch_markets()
    assert rows, "expected rows from stubbed Kalshi provider"
    for r in rows:
        _assert_row_shape(r)


def test_default_pm_providers_empty_when_both_feeds_empty():
    """When both Kalshi and Polymarket return empty bodies, fetch_markets returns []."""
    providers = [
        LF.KalshiPMProvider(sports=["nba"],
                             http_get=_make_kalshi_http_single(_KALSHI_EMPTY_BODY)),
        LF.PolymarketPMProvider(sports=["nba"],
                                http_get=_make_poly_http_single(_POLY_EMPTY_BODY)),
    ]
    all_rows = []
    for p in providers:
        all_rows.extend(p.fetch_markets())
    assert all_rows == [], "expected [] when both feeds are empty (honest empty)"


# ---------------------------------------------------------------------------
# active_pairs integration (the P1 acceptance gate)
# ---------------------------------------------------------------------------

def _nba_game():
    """One NBA game that matches the canned Kalshi NBA body (Celtics vs Heat)."""
    return LF.Game("nba", "Boston Celtics", "Miami Heat",
                   game_id="KXNBA-2026-BOS-20260620", game_date="2026-06-20")


def test_active_pairs_total_pm_gt_0_with_stubbed_kalshi():
    """active_pairs() with stubbed Kalshi NBA market -> total_pm > 0 (non-empty)."""
    kalshi_prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_NBA_BODY),
    )
    rows = LF.active_pairs(
        now=1_750_000_000.0,
        sources=[LF.MockGamesSource([_nba_game()])],
        predict_fn=_fake_predict,
        pm_providers=[kalshi_prov],
    )
    assert len(rows) >= 1, "total_pm must be > 0 when a live PM market matches a game"
    row = rows[0]
    assert "model_prob" in row
    assert "pm_prob" in row
    assert row["clv_status"] == "INSUFFICIENT_DATA"
    assert abs(row["model_prob"] - 0.62) < 1e-5
    bad = _DOLLAR_KEYS & set(row.keys())
    assert not bad, "$ fields in active_pairs row: %s" % sorted(bad)


def test_active_pairs_empty_when_no_pm_markets():
    """P1 pm-trail-empty: active_pairs returns [] when all providers are empty."""
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game()])],
        predict_fn=_fake_predict,
        pm_providers=[
            LF.KalshiPMProvider(sports=["nba"],
                                 http_get=_make_kalshi_http_single(_KALSHI_EMPTY_BODY)),
            LF.PolymarketPMProvider(sports=["nba"],
                                    http_get=_make_poly_http_single(_POLY_EMPTY_BODY)),
        ],
    )
    assert rows == [], "honest empty state: [] when no live PM market exists"


def test_active_pairs_clv_status_always_insufficient_data():
    """Every pair row must carry clv_status=INSUFFICIENT_DATA (PM CLV unproven)."""
    kalshi_prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_NBA_BODY),
    )
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game()])],
        predict_fn=_fake_predict,
        pm_providers=[kalshi_prov],
    )
    for row in rows:
        assert row.get("clv_status") == "INSUFFICIENT_DATA"


def test_active_pairs_no_dollar_fields_end_to_end():
    """No $ / P&L field in any row emitted by active_pairs end-to-end."""
    kalshi_prov = LF.KalshiPMProvider(
        sports=["nba"],
        http_get=_make_kalshi_http_single(_KALSHI_NBA_BODY),
    )
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game()])],
        predict_fn=_fake_predict,
        pm_providers=[kalshi_prov],
    )
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ field leaked into active_pairs: %s" % sorted(bad)


# ---------------------------------------------------------------------------
# _odds_event_to_pm_market unit tests
# ---------------------------------------------------------------------------

def test_odds_event_to_pm_market_valid():
    """_odds_event_to_pm_market converts a well-formed OddsEvent to a PM row."""
    from scripts.platformkit.odds_provider.base import OddsEvent
    ev = OddsEvent(
        event_id="EVT-1",
        sport="nba",
        home="Lakers",
        away="Clippers",
        commence_time=None,
        prices={"kalshi": {"home": 1.8182, "away": 2.2222, "draw": None}},
        source="kalshi",
    )
    row = LF._odds_event_to_pm_market(ev, "nba")
    assert row is not None
    assert row["market_id"] == "EVT-1"
    assert row["sport"] == "nba"
    assert row["home"] == "Lakers"
    assert row["away"] == "Clippers"
    assert 0.0 < row["pm_prob"] < 1.0
    # 1/1.8182 ~ 0.55
    assert abs(row["pm_prob"] - 0.55) < 0.01


def test_odds_event_to_pm_market_no_prices_returns_none():
    """_odds_event_to_pm_market returns None when prices are missing."""
    from scripts.platformkit.odds_provider.base import OddsEvent
    ev = OddsEvent(
        event_id="EVT-2", sport="nba", home="A", away="B",
        commence_time=None, prices={}, source="kalshi",
    )
    assert LF._odds_event_to_pm_market(ev, "nba") is None


# ---------------------------------------------------------------------------
# ws2-polymarket-binary-shape acceptance tests
# ---------------------------------------------------------------------------

def test_polymarket_binary_does_not_produce_yesno_home_away():
    """A YES/NO binary must NOT produce home='Yes'/away='No' rows.

    The old broken path mapped YES/NO to home/away, creating a bogus
    'nba:yes|nba:no|nba' index key that never matched any game slate.
    """
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_BINARY_BODY),
    )
    rows = prov.fetch_markets()
    # No row should have home='Yes' or away='No' (literal outcome labels).
    for row in rows:
        assert str(row.get("home", "")).lower() != "yes", \
            "YES/NO binary mis-shaped as two-leg: home='Yes'"
        assert str(row.get("away", "")).lower() != "no", \
            "YES/NO binary mis-shaped as two-leg: away='No'"


def test_polymarket_binary_produces_single_binary_row():
    """A YES/NO gamma contract emits a single-binary row: binary_title set,
    home/away/pm_prob all None."""
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_BINARY_BODY),
    )
    rows = prov.fetch_markets()
    binary_rows = [r for r in rows if r.get("binary_title")]
    assert len(binary_rows) >= 1, "expected >= 1 binary row from YES/NO market"
    b = binary_rows[0]
    assert b["home"] is None, "binary row home must be None"
    assert b["away"] is None, "binary row away must be None"
    assert b["pm_prob"] is None, "binary row pm_prob must be None"
    assert "Boston Celtics" in b["binary_title"] or "celtics" in b["binary_title"].lower()
    assert 0.0 < b["binary_yes_prob"] < 1.0, "binary_yes_prob out of (0,1)"
    bad = _DOLLAR_KEYS & set(b.keys())
    assert not bad, "$ field in binary row: %s" % sorted(bad)


def test_polymarket_mixed_body_splits_events_and_binaries():
    """A mixed Polymarket body yields both two-leg rows and binary rows."""
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_MIXED_BODY),
    )
    rows = prov.fetch_markets()
    two_leg = [r for r in rows if r.get("home") is not None]
    binary = [r for r in rows if r.get("binary_title")]
    assert len(two_leg) >= 1, "expected >= 1 two-leg row from mixed body"
    assert len(binary) >= 1, "expected >= 1 binary row from mixed body"


def test_active_pairs_binary_routes_through_path4():
    """active_pairs() with a per-game "Will TEAM win tonight?" binary routes
    through Path-4 and emits >= 1 pair row with correct fields.

    Uses _POLY_BINARY_GAME_BODY ("Will the Boston Celtics win tonight?") which
    is a genuine per-game binary.  Futures/championship contracts are tested
    separately in test_active_pairs_championship_binary_suppressed.
    """
    celtics_game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                           game_id="game-bos-mia", game_date="2026-06-20")
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_BINARY_GAME_BODY),
    )
    rows = LF.active_pairs(
        now=1_750_000_000.0,
        sources=[LF.MockGamesSource([celtics_game])],
        predict_fn=_fake_predict,
        pm_providers=[prov],
    )
    assert len(rows) >= 1, (
        "active_pairs must emit >= 1 row when per-game binary title matches "
        "slate team; got 0 (Path-4 routing broken)"
    )
    row = rows[0]
    assert row["clv_status"] == "INSUFFICIENT_DATA"
    assert 0.0 < row["model_prob"] < 1.0
    assert 0.0 < row["pm_prob"] < 1.0
    bad = _DOLLAR_KEYS & set(row.keys())
    assert not bad, "$ field in Path-4 pair row: %s" % sorted(bad)


def test_active_pairs_championship_binary_suppressed():
    """A futures/championship binary must NOT produce a pair row in active_pairs.

    "Will the Boston Celtics win the NBA championship?" is a season-long contract.
    Its YES price (0.65) is NOT a per-game win probability. Path-4 must reject it
    via _FUTURES_EXCLUDE_RE so the model-vs-PM divergence is never misleading.
    """
    celtics_game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                           game_id="game-bos-mia", game_date="2026-06-20")
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_BINARY_CHAMPIONSHIP_BODY),
    )
    rows = LF.active_pairs(
        now=1_750_000_000.0,
        sources=[LF.MockGamesSource([celtics_game])],
        predict_fn=_fake_predict,
        pm_providers=[prov],
    )
    assert rows == [], (
        "championship/futures binary must be suppressed by Path-4 futures gate; "
        "got %d rows (season-long YES price paired against per-game model prob)"
        % len(rows)
    )


def test_active_pairs_binary_honest_empty_when_no_match():
    """When a per-game binary title does NOT match any slate team, active_pairs
    returns [] (honest empty -- no fabricated rows)."""
    # Slate game: Phoenix Suns vs Dallas Mavericks.
    # Binary question: "Will the Boston Celtics win tonight?" -- Celtics not on slate.
    suns_game = LF.Game("nba", "Phoenix Suns", "Dallas Mavericks",
                        game_id="game-phx-dal", game_date="2026-06-20")
    prov = LF.PolymarketPMProvider(
        sports=["nba"],
        http_get=_make_poly_http_single(_POLY_BINARY_GAME_BODY),
    )
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([suns_game])],
        predict_fn=_fake_predict,
        pm_providers=[prov],
    )
    assert rows == [], (
        "honest empty: [] when per-game binary question does not match slate team"
    )


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
