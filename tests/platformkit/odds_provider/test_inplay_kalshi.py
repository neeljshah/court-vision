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
  * fetch_price_history maps candlesticks to the canonical schema + phase;
  * fetch_inplay iterates ALL of a sport's wired series (mlb: game+total+spread+
    team_total; tennis: ATP+WTA), tags market_type, carries "line" from floor_strike
    for non-moneyline, isolates one series' failure from the others, and moneyline
    rows stay byte-compatible with the pre-widening schema.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_inplay_kalshi.py -q
"""
from __future__ import annotations

import re
import urllib.error

from scripts.platformkit.odds_provider import transport as _transport
from scripts.platformkit.odds_provider.inplay_kalshi import (
    MAX_429_COOLDOWN_SEC,
    PHASE,
    REQUEST_STAGGER_SEC,
    _tick_from_market,  # exercised directly for the depth-fields honesty case (see below)
    fetch_inplay,
    fetch_price_history,
    is_liquid,
)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# best_bid/best_ask/spread_bp: additive LEVER-1 exec_depth fields (2026-07-15) --
# see ingame_exec_gate.build_exec_depth's _DEPTH_TICK_FIELDS for the consumer.
_CANON_KEYS = {"sport", "game_id", "venue", "market_type", "side", "ticker",
               "prob", "line", "ts", "phase", "best_bid", "best_ask", "spread_bp"}
_MONEYLINE_LEGACY_KEYS = {"sport", "game_id", "venue", "market_type", "side",
                          "ticker", "prob", "ts", "phase"}  # pre-widening shape


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
    # mlb now queries 4 series (game/total/spread/team_total); the SAME fixture body is
    # returned for each, but the event_ticker startswith(series) guard means only the
    # KXMLBGAME query's markets survive -- the total/spread/team_total queries see the
    # SAME body but every market in it has an event_ticker starting "KXMLBGAME", which
    # does not start with "KXMLBTOTAL"/"KXMLBSPREAD"/"KXMLBTEAMTOTAL", so they contribute 0.
    ticks = fetch_inplay(
        "mlb", http=_fake_http([_LIQUID, _ILLIQUID, _DEPRECATED_ONLY, _OTHER_SPORT]),
        now_iso="2026-06-19T18:30:00Z")
    # only the single LIQUID, correct-sport, correct-series market survives the gate
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
    assert t["line"] is None              # moneyline never carries a line
    assert _ISO.match(t["ts"])
    # HONESTY: a near-final price must never carry a commence_time -> is_true_close
    assert "commence_time" not in t
    # moneyline rows stay BYTE-COMPATIBLE with the pre-widening schema (minus "line",
    # which is a new key -- every OLD key is still present and unchanged).
    assert _MONEYLINE_LEGACY_KEYS <= set(t)
    # LEVER-1 exec_depth fields: real bid/ask/spread off the SAME live *_dollars
    # fields the liquidity gate already required (see _LIQUID fixture above).
    assert t["best_bid"] == 0.53 and t["best_ask"] == 0.54
    assert abs(t["spread_bp"] - 100.0) < 1e-9   # 1c spread = 100bp of a $1 contract


def test_tick_from_market_depth_fields_none_when_unquoted_never_fabricated():
    # A market with a usable YES price (last_price_dollars) but NO live bid/ask quote
    # -- a shape is_liquid() would gate out at the fetch_inplay level (it hard-requires
    # both *_dollars sides), so this exercises _tick_from_market directly to prove the
    # depth fields are honestly None, never a fabricated number, when genuinely absent.
    market = {
        "ticker": "KXMLBGAME-26JUN191420TORCHC-CHC",
        "event_ticker": "KXMLBGAME-26JUN191420TORCHC",
        "yes_sub_title": "CHC",
        "last_price_dollars": 0.54,
        "yes_bid_dollars": None, "yes_ask_dollars": None,
    }
    t = _tick_from_market("mlb", market, "2026-06-19T18:30:00Z", "moneyline")
    assert t is not None
    assert t["ticker"] == "KXMLBGAME-26JUN191420TORCHC-CHC"  # ticker is already the per-side id
    assert t["best_bid"] is None and t["best_ask"] is None and t["spread_bp"] is None


def test_fetch_queries_every_wired_series_for_the_sport():
    # W2->widened: mlb queries ALL FOUR series (game/total/spread/team_total); tennis
    # queries ATP+WTA; soccer_intl queries game+spread+team_total.
    seen = []
    fetch_inplay("mlb", http=_fake_http([_LIQUID], seen=seen),
                 now_iso="2026-06-19T18:30:00Z")
    assert len(seen) == 4
    assert all("status=open" in u for u in seen)
    got_series = {u.split("series_ticker=")[1].split("&")[0] for u in seen}
    assert got_series == {"KXMLBGAME", "KXMLBTOTAL", "KXMLBSPREAD", "KXMLBTEAMTOTAL"}

    seen_wc = []
    fetch_inplay("soccer_intl", http=_fake_http([_LIQUID_WC], seen=seen_wc),
                 now_iso="2026-06-19T18:30:00Z")
    assert len(seen_wc) == 3
    got_wc = {u.split("series_ticker=")[1].split("&")[0] for u in seen_wc}
    assert got_wc == {"KXWCGAME", "KXWCSPREAD", "KXWCTEAMTOTAL"}

    seen_tennis = []
    fetch_inplay("tennis", http=_fake_http([], seen=seen_tennis),
                 now_iso="2026-06-19T18:30:00Z")
    assert len(seen_tennis) == 2
    got_tennis = {u.split("series_ticker=")[1].split("&")[0] for u in seen_tennis}
    assert got_tennis == {"KXATPMATCH", "KXWTAMATCH"}


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
    assert t["line"] is None
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


# ---- tennis (KXATPMATCH/KXWTAMATCH -- moneyline only, real-shaped ticker) ---- #
_LIQUID_ATP = {
    "ticker": "KXATPMATCH-26JUL05SAFDJO-SAF",
    "event_ticker": "KXATPMATCH-26JUL05SAFDJO",
    "yes_sub_title": "Roman Safiullin",
    "strike_type": "structured",     # real shape: NO floor_strike on a moneyline match
    "yes_bid_dollars": 0.15, "yes_ask_dollars": 0.16,
    "yes_bid_size_fp": 1200.0, "yes_ask_size_fp": 1500.0,
    "volume_fp": 144.53,
    "yes_bid": None, "yes_ask": None, "last_price": None, "volume": None,
}


def test_tennis_atp_match_parses_liquid_moneyline_tick_no_line():
    # now = match day itself (Jul 5) so the future-game ticker-date guard keeps it.
    ticks = fetch_inplay("tennis", http=_fake_http([_LIQUID_ATP]),
                         now_iso="2026-07-05T12:00:00Z")
    assert len(ticks) == 1
    t = ticks[0]
    assert t["sport"] == "tennis"
    assert t["market_type"] == "moneyline"
    assert t["ticker"] == "KXATPMATCH-26JUL05SAFDJO-SAF"
    assert t["game_id"] == "KXATPMATCH-26JUL05SAFDJO"
    assert t["side"] == "Roman Safiullin"
    assert abs(t["prob"] - 0.16) < 1e-9
    assert t["line"] is None  # a tennis moneyline match never carries a strike line


# ---- total/spread/team_total: real-shaped fixtures (floor_strike carries the line) - #
_LIQUID_TOTAL = {
    "ticker": "KXMLBTOTAL-26JUL032010SFCOL-9",
    "event_ticker": "KXMLBTOTAL-26JUL032010SFCOL",
    "yes_sub_title": "Over 8.5 runs scored",
    "floor_strike": 8.5, "strike_type": "greater",
    "yes_bid_dollars": 0.73, "yes_ask_dollars": 0.74,
    "yes_bid_size_fp": 153.0, "yes_ask_size_fp": 2849.21,
    "volume_fp": 1716.35,
    "yes_bid": None, "yes_ask": None, "last_price": None, "volume": None,
}

_LIQUID_SPREAD = {
    "ticker": "KXMLBSPREAD-26JUL032010SFCOL-SF4",
    "event_ticker": "KXMLBSPREAD-26JUL032010SFCOL",
    "yes_sub_title": "San Francisco wins by over 3.5 runs",
    "floor_strike": 3.5, "strike_type": "greater",
    "yes_bid_dollars": 0.30, "yes_ask_dollars": 0.31,
    "yes_bid_size_fp": 4977.80, "yes_ask_size_fp": 10471.85,
    "volume_fp": 560.61,
    "yes_bid": None, "yes_ask": None, "last_price": None, "volume": None,
}


def test_mlb_total_market_tags_market_type_and_carries_line():
    def _series_router(url):
        if "series_ticker=KXMLBTOTAL" in url:
            return {"markets": [_LIQUID_TOTAL]}
        return {"markets": []}
    ticks = fetch_inplay("mlb", http=_series_router, now_iso="2026-07-03T20:15:00Z")
    assert len(ticks) == 1
    t = ticks[0]
    assert t["market_type"] == "total"
    assert t["ticker"] == "KXMLBTOTAL-26JUL032010SFCOL-9"
    assert t["game_id"] == "KXMLBTOTAL-26JUL032010SFCOL"
    assert abs(t["line"] - 8.5) < 1e-9
    assert abs(t["prob"] - 0.74) < 1e-9
    assert set(t) == _CANON_KEYS


def test_mlb_spread_market_tags_market_type_and_carries_line():
    def _series_router(url):
        if "series_ticker=KXMLBSPREAD" in url:
            return {"markets": [_LIQUID_SPREAD]}
        return {"markets": []}
    ticks = fetch_inplay("mlb", http=_series_router, now_iso="2026-07-03T20:15:00Z")
    assert len(ticks) == 1
    t = ticks[0]
    assert t["market_type"] == "spread"
    assert abs(t["line"] - 3.5) < 1e-9


def test_one_series_failure_does_not_sink_the_others():
    # KXMLBTOTAL raises; KXMLBGAME/SPREAD/TEAMTOTAL still return their own markets.
    def _flaky_router(url):
        if "series_ticker=KXMLBTOTAL" in url:
            raise RuntimeError("network down for this series only")
        if "series_ticker=KXMLBGAME" in url:
            return {"markets": [_LIQUID]}
        return {"markets": []}
    ticks = fetch_inplay("mlb", http=_flaky_router, now_iso="2026-06-19T18:30:00Z")
    assert len(ticks) == 1
    assert ticks[0]["market_type"] == "moneyline"
    assert ticks[0]["ticker"] == "KXMLBGAME-26JUN191420TORCHC-CHC"


def test_default_http_fetcher_is_the_resilient_transport():
    # fetch_inplay's default http param must be transport.resilient_get_json (the
    # escalating stealth-fallback tier), not the plain http_get_json -- same injection
    # seam, new default.
    import inspect
    sig = inspect.signature(fetch_inplay)
    assert sig.parameters["http"].default is _transport.resilient_get_json


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
        # fetch_price_history's schema is UNCHANGED by this widening (no "line" key --
        # it is a single-market candle backfill, not a multi-series in-play fetch).
        assert set(t) == _MONEYLINE_LEGACY_KEYS
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


# --------------------------------------------------------------------------------------- #
# LANE 1 (wave-16 fix): request pacing + 429 observability, injected clock (no real sleep)  #
# --------------------------------------------------------------------------------------- #
def _http_429(headers=None):
    return urllib.error.HTTPError(url="http://x", code=429, msg="Too Many Requests",
                                  hdrs=headers or {}, fp=None)


def test_fetch_inplay_default_stagger_is_zero_no_behavior_change_for_existing_callers():
    # BACK-COMPAT (LANE 1): stagger_sec defaults to 0.0 -- a caller that never
    # mentions pacing (every pre-existing test/caller) gets ZERO sleeps, so the
    # offline suite stays instant and production callers are unaffected unless
    # they explicitly opt in (see inplay_capture_loop._default_inplay_fetch).
    sleeps = []
    fetch_inplay("mlb", http=_fake_http([_LIQUID]), now_iso="2026-06-19T18:30:00Z",
                sleep_fn=sleeps.append)
    assert sleeps == []


def test_fetch_inplay_explicit_stagger_sleeps_between_but_not_before_first_series():
    # mlb queries 4 series -> 3 gaps between them, sleep injected (no real time.sleep).
    sleeps = []
    fetch_inplay("mlb", http=_fake_http([_LIQUID]), now_iso="2026-06-19T18:30:00Z",
                sleep_fn=sleeps.append, stagger_sec=REQUEST_STAGGER_SEC)
    assert sleeps == [REQUEST_STAGGER_SEC] * 3


def test_fetch_inplay_counts_requests_in_stats():
    stats: dict = {}
    fetch_inplay("mlb", http=_fake_http([_LIQUID]), now_iso="2026-06-19T18:30:00Z",
                stats=stats, sleep_fn=lambda s: None)
    assert stats["n_requests"] == 4  # mlb wires 4 series


def test_fetch_inplay_counts_429_and_recovers_other_series():
    # KXMLBTOTAL 429s (counted + cooled down, no real sleep); the other 3 series still
    # return their own markets -- one series' 429 never sinks the sport's fetch.
    def _router(url):
        if "series_ticker=KXMLBTOTAL" in url:
            raise _http_429()
        if "series_ticker=KXMLBGAME" in url:
            return {"markets": [_LIQUID]}
        return {"markets": []}

    stats: dict = {}
    cooldowns = []
    ticks = fetch_inplay("mlb", http=_router, now_iso="2026-06-19T18:30:00Z",
                         stats=stats, sleep_fn=cooldowns.append)
    assert stats["n_requests"] == 4
    assert stats["n_429"] == 1
    assert len(ticks) == 1 and ticks[0]["ticker"] == "KXMLBGAME-26JUN191420TORCHC-CHC"
    # the 429 cool-down IS one of the injected sleep calls (mixed with stagger sleeps).
    assert any(abs(s - MAX_429_COOLDOWN_SEC) < 1e-9 for s in cooldowns)


def test_fetch_inplay_429_honors_retry_after_header_capped():
    def _router(url):
        if "series_ticker=KXMLBTOTAL" in url:
            raise _http_429(headers={"Retry-After": "1"})
        return {"markets": []}

    cooldowns = []
    fetch_inplay("mlb", http=_router, now_iso="2026-06-19T18:30:00Z",
                sleep_fn=cooldowns.append)
    assert 1.0 in cooldowns  # honored, under MAX_429_COOLDOWN_SEC cap


def test_fetch_inplay_non_429_error_is_not_counted_as_429():
    def _router(url):
        if "series_ticker=KXMLBTOTAL" in url:
            raise RuntimeError("plain network error")
        return {"markets": []}

    stats: dict = {}
    fetch_inplay("mlb", http=_router, now_iso="2026-06-19T18:30:00Z",
                stats=stats, sleep_fn=lambda s: None)
    assert stats.get("n_429", 0) == 0
    assert stats["n_requests"] == 4


def test_fetch_inplay_stats_none_by_default_no_behavior_change():
    # Calling fetch_inplay exactly as every pre-existing caller does (no stats/sleep_fn
    # kwargs) must be unaffected -- this exercises the real default sleep_fn=time.sleep
    # with stagger_sec=0 to avoid a real sleep in the test suite.
    ticks = fetch_inplay("mlb", http=_fake_http([_LIQUID]), now_iso="2026-06-19T18:30:00Z",
                         stagger_sec=0.0)
    assert len(ticks) == 1
