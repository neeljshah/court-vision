"""Per-file test for odds_provider.inplay_kalshi (offline, injected http).

Drives fetch_inplay + fetch_price_history on FIXTURE *_dollars JSON and asserts the
HONEST liquidity gate + canonical in-play schema:

  * a LIQUID market (tight *_dollars spread, real volume_fp, real *_size_fp) -> a
    parsed in-play tick with the canonical schema + phase="in_play";
  * an ILLIQUID / untraded market (wide/no spread, low volume, None sizes) -> EXCLUDED
    (never faked into a live price);
  * a market priced ONLY by the deprecated bare-integer fields (yes_bid/yes_ask/
    volume = None on the live API) -> NOT zeroed into a real price -> excluded;
  * commence_time is never emitted (a near-final price can't be is_true_close);
  * fetch_price_history maps candlesticks to the canonical schema + phase.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_inplay_kalshi.py -q
"""
from __future__ import annotations

import re

from scripts.platformkit.odds_provider.inplay_kalshi import (
    PHASE,
    fetch_inplay,
    fetch_price_history,
    is_liquid,
)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CANON_KEYS = {"sport", "game_id", "venue", "market_type", "side", "ticker",
               "prob", "ts", "phase"}


# ---- a LIQUID in-season game market (real *_dollars / *_fp depth) ----------- #
_LIQUID = {
    "ticker": "KXMLBGAME-26JUN191420TORCHC-CHC",
    "event_ticker": "KXMLBGAME-26JUN191420TORCHC",
    "yes_sub_title": "CHC",
    "yes_bid_dollars": 0.53,
    "yes_ask_dollars": 0.54,            # 1c spread
    "yes_bid_size_fp": 71910.0,
    "yes_ask_size_fp": 1000227.0,
    "volume_fp": 606488.0,
    "open_interest_fp": 578154.0,
    # deprecated integer fields read None on the live API:
    "yes_bid": None, "yes_ask": None, "last_price": None, "volume": None,
}

# ---- an ILLIQUID / untraded pregame contract (wide spread, no depth) -------- #
_ILLIQUID = {
    "ticker": "KXMLBGAME-26JUN199999XXXYYY-YYY",
    "event_ticker": "KXMLBGAME-26JUN199999XXXYYY",
    "yes_sub_title": "YYY",
    "yes_bid_dollars": 0.10,
    "yes_ask_dollars": 0.80,            # 70c spread -> not tradeable
    "yes_bid_size_fp": None,
    "yes_ask_size_fp": None,
    "volume_fp": 0.0,
    "open_interest_fp": 0.0,
}

# ---- a market priced ONLY by deprecated integer fields (live *_dollars None) - #
# The live API would read None on these; a naive parser that reads yes_bid/yes_ask
# would zero it into a fake price. Our gate (no *_dollars spread, None *_fp) drops it.
_DEPRECATED_ONLY = {
    "ticker": "KXMLBGAME-26JUN195555AAABBB-BBB",
    "event_ticker": "KXMLBGAME-26JUN195555AAABBB",
    "yes_sub_title": "BBB",
    "yes_bid": 47, "yes_ask": 49, "volume": 1234,   # deprecated ints (would mislead)
    "yes_bid_dollars": None, "yes_ask_dollars": None,
    "yes_bid_size_fp": None, "yes_ask_size_fp": None, "volume_fp": None,
}

# A wrong-sport market (different series prefix) must be ignored entirely.
_OTHER_SPORT = dict(_LIQUID, ticker="KXNBAGAME-x", event_ticker="KXNBAGAME-x")


def _fake_http(markets, *, seen=None):
    def _get(url):
        if seen is not None:
            seen.append(url)
        return {"markets": markets}
    return _get


# ---- a LIQUID World Cup soccer per-GAME market (KXWCGAME series) ------------- #
_LIQUID_WC = {
    "ticker": "KXWCGAME-26JUN18MEXKOR-MEX",
    "event_ticker": "KXWCGAME-26JUN18MEXKOR",
    "yes_sub_title": "MEX",
    "yes_bid_dollars": 0.61,
    "yes_ask_dollars": 0.62,            # 1c spread
    "yes_bid_size_fp": 25000.0,
    "yes_ask_size_fp": 31000.0,
    "volume_fp": 142000.0,
    "open_interest_fp": 99000.0,
    "yes_bid": None, "yes_ask": None, "last_price": None, "volume": None,
}


def test_is_liquid_gate():
    assert is_liquid(_LIQUID) is True
    assert is_liquid(_ILLIQUID) is False       # wide spread + no depth
    assert is_liquid(_DEPRECATED_ONLY) is False  # live *_dollars None -> VOID


def test_liquid_market_parses_to_canonical_inplay_tick():
    ticks = fetch_inplay(
        "mlb", http=_fake_http([_LIQUID, _ILLIQUID, _DEPRECATED_ONLY, _OTHER_SPORT]),
        now_iso="2026-06-19T18:30:00Z")
    # only the single LIQUID, correct-sport market survives the gate
    assert len(ticks) == 1
    t = ticks[0]
    assert set(t) == _CANON_KEYS
    assert t["venue"] == "kalshi"
    assert t["sport"] == "mlb"
    assert t["market_type"] == "moneyline"
    assert t["side"] == "CHC"
    assert t["ticker"] == "KXMLBGAME-26JUN191420TORCHC-CHC"
    assert t["game_id"] == "KXMLBGAME-26JUN191420TORCHC"
    assert t["phase"] == PHASE == "in_play"
    assert isinstance(t["prob"], float) and 0.0 < t["prob"] < 1.0
    assert abs(t["prob"] - 0.54) < 1e-9   # yes_ask_dollars
    assert _ISO.match(t["ts"])
    # HONESTY: a near-final price must never carry a commence_time -> is_true_close
    assert "commence_time" not in t


def test_fetch_queries_per_game_series_ticker():
    # W2: the list endpoint MUST be queried with series_ticker=KX<league>GAME so the
    # per-game liquid markets page in (the old broad KX<league> prefix missed them).
    seen = []
    fetch_inplay("mlb", http=_fake_http([_LIQUID], seen=seen),
                 now_iso="2026-06-19T18:30:00Z")
    assert len(seen) == 1
    assert "series_ticker=KXMLBGAME" in seen[0]
    assert "status=open" in seen[0]

    seen_wc = []
    fetch_inplay("soccer_intl", http=_fake_http([_LIQUID_WC], seen=seen_wc),
                 now_iso="2026-06-19T18:30:00Z")
    assert len(seen_wc) == 1
    assert "series_ticker=KXWCGAME" in seen_wc[0]


def test_world_cup_per_game_market_parses_liquid_tick():
    # mirror the real KXMLBGAME-...CWSDET shape for World Cup (KXWCGAME) soccer:
    # a liquid per-game pair passes the gate; an untraded one is gated out.
    ticks = fetch_inplay(
        "soccer_intl", http=_fake_http([_LIQUID_WC, _ILLIQUID]),
        now_iso="2026-06-19T18:30:00Z")
    assert len(ticks) == 1
    t = ticks[0]
    assert set(t) == _CANON_KEYS
    assert t["sport"] == "soccer_intl"
    assert t["side"] == "MEX"
    assert t["ticker"] == "KXWCGAME-26JUN18MEXKOR-MEX"
    assert t["game_id"] == "KXWCGAME-26JUN18MEXKOR"
    assert t["phase"] == "in_play"
    assert abs(t["prob"] - 0.62) < 1e-9
    assert "commence_time" not in t


def test_future_dated_game_excluded_as_not_inplay():
    # A LIQUID contract for a game DAYS out (the next tournament days, traded pre-match)
    # must NOT be emitted as in-play -- it would let a pregame price masquerade as live.
    # KXWCGAME-26JUL04CANMAR is Jul 4; with now=Jun 30 it is 4 days out -> dropped.
    future = dict(_LIQUID_WC, ticker="KXWCGAME-26JUL04CANMAR-MAR",
                  event_ticker="KXWCGAME-26JUL04CANMAR")
    ticks = fetch_inplay("soccer_intl", http=_fake_http([future]),
                         now_iso="2026-06-30T19:00:00Z")
    assert ticks == []


def test_today_and_tomorrow_games_kept_timezone_tolerant():
    # Today (Jun 30) AND tomorrow (Jul 01) are within the 1-day grace -> KEPT (their true
    # liveness is the downstream score-state bridge's call); only multi-day futures drop.
    for d in ("26JUN30", "26JUL01"):
        m = dict(_LIQUID_WC, ticker="KXWCGAME-%sXYZABC-XYZ" % d,
                 event_ticker="KXWCGAME-%sXYZABC" % d)
        ticks = fetch_inplay("soccer_intl", http=_fake_http([m]),
                             now_iso="2026-06-30T19:00:00Z")
        assert len(ticks) == 1, "today/tomorrow game must be kept (%s)" % d


def test_unparseable_ticker_date_is_kept_not_dropped():
    # A ticker with no parseable date is KEPT -- never drop a market on a parse miss.
    m = dict(_LIQUID_WC, ticker="KXWCGAME-WEIRDFORMAT-XYZ",
             event_ticker="KXWCGAME-WEIRDFORMAT")
    ticks = fetch_inplay("soccer_intl", http=_fake_http([m]),
                         now_iso="2026-06-30T19:00:00Z")
    assert len(ticks) == 1


def test_illiquid_and_deprecated_excluded_not_faked():
    # A slate of ONLY untradeable markets emits NOTHING (VOID), never a 0-fill.
    ticks = fetch_inplay(
        "mlb", http=_fake_http([_ILLIQUID, _DEPRECATED_ONLY]),
        now_iso="2026-06-19T18:30:00Z")
    assert ticks == []


def test_unsupported_sport_and_bad_body_yield_empty():
    assert fetch_inplay("cricket", http=_fake_http([_LIQUID])) == []
    assert fetch_inplay("mlb", http=lambda u: {"markets": "bad"}) == []

    def _boom(url):
        raise RuntimeError("network down")

    assert fetch_inplay("mlb", http=_boom) == []


def test_price_history_maps_to_canonical_schema_with_phase():
    body = {
        "candlesticks": [
            {"end_period_ts": 1781564400,
             "price": {"close_dollars": "0.45"},
             "yes_bid": {"close_dollars": "0.44"},
             "yes_ask": {"close_dollars": "0.46"}},
            {"end_period_ts": 1781568000,
             "price": {"close_dollars": "0.01"}},   # walked to resolution
            {"end_period_ts": 1781571600, "price": {}, "yes_bid": {}, "yes_ask": {}},
        ]
    }

    def _get(url):
        return body

    ticks = fetch_price_history(
        "KXMLBGAME-26JUN182140LAAATH-LAA", window=7200,
        sport="mlb", side="LAA", http=_get, now_epoch=1781575200)
    assert len(ticks) == 2  # 3rd candle unusable -> skipped (never fabricated)
    for t in ticks:
        assert set(t) == _CANON_KEYS
        assert t["venue"] == "kalshi"
        assert t["phase"] == "in_play"
        assert t["ticker"] == "KXMLBGAME-26JUN182140LAAATH-LAA"
        assert t["side"] == "LAA"
        assert isinstance(t["prob"], float) and 0.0 <= t["prob"] <= 1.0
        assert _ISO.match(t["ts"])
        assert "commence_time" not in t   # never mislabel a near-final as the close
    assert abs(ticks[0]["prob"] - 0.45) < 1e-9
    assert abs(ticks[1]["prob"] - 0.01) < 1e-9


def test_price_history_bad_body_yields_empty():
    assert fetch_price_history("KXMLBGAME-x", http=lambda u: {}) == []

    def _boom(url):
        raise RuntimeError("down")

    assert fetch_price_history("KXMLBGAME-x", http=_boom) == []
