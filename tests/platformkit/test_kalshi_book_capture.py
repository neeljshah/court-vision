"""Per-file, no-network tests for kalshi_series_scope.py + kalshi_book_row.py +
kalshi_book_capture.py: (a) series allowlist -> discovery URL construction +
cursor pagination on fixture pages, (b) live/pregame/idle cadence selection from
fixture close_times, (c) orderbook row construction from a fixture payload (raw
ladders verbatim, best bid/ask derived) for a yes-only and a yes+no payload plus
one pass through the REAL parsers on ingame_book_depth_kalshi's own fixture body,
(d) archive path selection under the two pod env flags. Every HTTP boundary (the
discovery *get* callable, the capture StubClient) is a fixture function -- no
socket is ever opened.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_kalshi_book_capture.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.ingame import kalshi_book_capture as capture
from scripts.platformkit.ingame import kalshi_book_row as row
from scripts.platformkit.ingame import kalshi_series_scope as scope
from tests.platformkit.ingame.test_ingame_book_depth_kalshi import _ORDERBOOK_BODY


# --------------------------------------------------------------------------- #
# (a) series allowlist -> discovery URL + cursor pagination                   #
# --------------------------------------------------------------------------- #
def test_allowlist_covers_every_sport_with_its_flagship_series():
    assert scope.SERIES_BY_SPORT["nba"][0] == "KXNBAGAME"
    assert "KXMLBPITCH" in scope.SERIES_BY_SPORT["mlb"]
    assert "KXATPMATCH" in scope.SERIES_BY_SPORT["tennis"]
    assert "KXEPLGAME" in scope.SERIES_BY_SPORT["soccer"]
    assert scope.SERIES_BY_SPORT["wnba"] == ("KXWNBAGAME",)


def test_discovery_url_carries_series_status_and_cursor():
    url = scope.discovery_url("KXNBAGAME")
    assert "series_ticker=KXNBAGAME" in url and "status=open" in url
    assert "with_nested_markets=true" in url
    assert "cursor=" not in url
    assert "cursor=page2" in scope.discovery_url("KXNBAGAME", "page2")


def test_fetch_open_markets_paginates_by_cursor_and_drops_non_open():
    page1_url = scope.discovery_url("KXNBAGAME")
    page2_url = scope.discovery_url("KXNBAGAME", "page2")
    pages = {
        page1_url: {"events": [{"event_ticker": "EVT1", "title": "A at B",
                                 "markets": [{"ticker": "EVT1-A", "status": "open",
                                              "close_time": "2026-09-14T23:00:00Z"},
                                             {"ticker": "EVT1-B", "status": "closed",
                                              "close_time": "2026-09-14T23:00:00Z"}]}],
                    "cursor": "page2"},
        page2_url: {"events": [{"event_ticker": "EVT2", "markets": [
            {"ticker": "EVT2-A", "status": "open", "close_time": "2026-09-15T02:00:00Z"}]}],
                    "cursor": ""},
    }
    calls = []

    def get(url):
        calls.append(url)
        return pages.get(url)

    markets = scope.fetch_open_markets(get, "KXNBAGAME")
    assert [m["ticker"] for m in markets] == ["EVT1-A", "EVT2-A"]
    assert markets[0]["series_ticker"] == "KXNBAGAME" and markets[0]["event_ticker"] == "EVT1"
    assert calls == [page1_url, page2_url], "pagination stopped once cursor was empty"


def test_fetch_open_markets_tolerates_a_404_style_none_page():
    assert scope.fetch_open_markets(lambda _url: None, "KXNBAPTS") == []


# --------------------------------------------------------------------------- #
# (b) live/pregame/idle cadence from fixture close_times                      #
# --------------------------------------------------------------------------- #
def test_classify_market_state_live_pregame_idle_and_missing_close_time():
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    assert scope.classify_market_state({"close_time": "2026-09-14T21:00:00Z"}, "nba", now) \
        == ("live", scope.LIVE_CADENCE_SEC)
    assert scope.classify_market_state({"close_time": "2026-09-15T05:00:00Z"}, "nba", now) \
        == ("pregame", scope.PREGAME_CADENCE_SEC)
    assert scope.classify_market_state({"close_time": "2026-09-20T05:00:00Z"}, "nba", now) \
        == ("idle", scope.IDLE_CADENCE_SEC)
    assert scope.classify_market_state({}, "nba", now) == ("idle", scope.IDLE_CADENCE_SEC)


def test_classify_market_state_uses_the_sport_specific_typical_duration():
    # Same market, same clock: NBA's shorter typical duration (2.5h) puts the
    # estimated start just AFTER now (pregame); MLB's longer one (3.5h) puts it
    # before now (live) -- proves the per-sport duration is actually consulted.
    now = datetime(2026, 9, 14, 19, 15, 0, tzinfo=timezone.utc)
    market = {"close_time": "2026-09-14T22:00:00Z"}
    assert scope.classify_market_state(market, "nba", now)[0] == "pregame"
    assert scope.classify_market_state(market, "mlb", now)[0] == "live"


# --------------------------------------------------------------------------- #
# (c) orderbook row construction: raw verbatim + derived best bid/ask         #
#                                                                               #
# The two reused parsers (parse_orderbook, mlb_book_capture._levels) already   #
# own -- and are already tested against -- the venue's actual wire field       #
# names; these first two tests isolate book_row's OWN logic (verbatim storage  #
# + the best-bid/ask algebra) by feeding it the two parsers' OWN output shapes #
# directly, monkeypatched on kalshi_book_row (where book_row actually resolves #
# those names, not on kalshi_book_capture, which only re-exports book_row).    #
# --------------------------------------------------------------------------- #
def test_book_row_yes_and_no_payload_stores_raw_and_derives_both_sides(monkeypatch):
    market = {"sport": "mlb", "series_ticker": "KXMLBGAME", "ticker": "T1",
              "event_ticker": "EVT1", "state": "live"}
    body = {"fixture": "yes+no book"}  # opaque -- only identity + .get("ts") matter here
    # parse_orderbook (mocked) is the ONLY source of yes_bid/yes_ask -- book_row
    # does not re-derive them from the raw ladders. no_bid/no_ask, by contrast,
    # ARE book_row's own derivation: the algebraic inverse of yes_ask/yes_bid.
    monkeypatch.setattr(row, "parse_orderbook", lambda _b: (0.40, 0.45, 0.0, 0.0, 4))
    monkeypatch.setattr(row, "_raw_ladders", lambda _b: {
        "yes": [["0.30", "2"], ["0.40", "3"]], "no": [["0.45", "4"], ["0.55", "5"]]})
    out = row.book_row(market, body, ts_ms=1700000000000,
                        capture_ts="2026-09-14T20:00:00.000000Z")
    assert out["book"] is body, "raw payload verbatim, no transformation"
    assert out["ts_ms"] == 1700000000000 and out["capture_version"] == row.CAPTURE_VERSION
    assert out["yes_bid"] == 0.40, "straight from the mocked parse_orderbook"
    assert round(out["yes_ask"], 10) == 0.45, "straight from the mocked parse_orderbook"
    assert out["no_bid"] == 0.55, "book_row's own derivation: 1 - yes_ask (0.45)"
    assert round(out["no_ask"], 10) == 0.60, "book_row's own derivation: 1 - yes_bid (0.40)"
    assert out["yes_bid_size"] == 3.0 and out["no_bid_size"] == 5.0
    assert out["depth_bid"] == 5.0 and out["depth_ask"] == 9.0
    assert out["yes_bid_top5_asc"] == [[0.30, 2.0], [0.40, 3.0]]


def test_book_row_close_time_yields_minutes_to_close_and_omitted_yields_nulls(monkeypatch):
    market = {"sport": "nba", "series_ticker": "KXNBAGAME", "ticker": "T4",
              "event_ticker": "EVT4", "state": "live"}
    monkeypatch.setattr(row, "parse_orderbook", lambda _b: (0.40, 0.45, 0.0, 0.0, 4))
    monkeypatch.setattr(row, "_raw_ladders", lambda _b: {"yes": [], "no": []})
    # ts_ms = 2026-09-14T19:30:00Z, close_time 30 minutes later -> +30.0
    ts_ms = 1789414200000
    with_close = row.book_row(market, {}, ts_ms=ts_ms, capture_ts="2026-09-14T19:30:00.000000Z",
                               close_time="2026-09-14T20:00:00Z")
    assert with_close["close_time"] == "2026-09-14T20:00:00Z"
    assert round(with_close["minutes_to_close"], 6) == 30.0
    omitted = row.book_row(market, {}, ts_ms=ts_ms, capture_ts="2026-09-14T19:30:00.000000Z")
    assert omitted["close_time"] is None and omitted["minutes_to_close"] is None


def test_book_row_yes_only_payload_leaves_the_no_side_none(monkeypatch):
    market = {"sport": "nba", "series_ticker": "KXNBAGAME", "ticker": "T2",
              "event_ticker": "EVT2", "state": "pregame"}
    body = {"fixture": "yes-only book"}
    monkeypatch.setattr(row, "parse_orderbook", lambda _b: (0.20, None, 0.0, 0.0, 1))
    monkeypatch.setattr(row, "_raw_ladders", lambda _b: {"yes": [["0.20", "1"]], "no": []})
    out = row.book_row(market, body, ts_ms=1700000001000,
                        capture_ts="2026-09-14T20:00:05.000000Z")
    assert out["yes_bid"] == 0.20
    assert out["yes_ask"] is None and out["no_bid"] is None, \
        "no no-side ladder in this payload -> nothing to derive yes_ask/no_bid from"
    assert round(out["no_ask"], 10) == 0.80, "no_ask = 1 - best yes bid (0.20) needs only the yes side"
    assert out["no_bid_size"] is None and out["depth_ask"] == 0.0


def test_book_row_through_the_real_parsers_on_a_real_orderbook_fixture():
    """No mocking: the REAL parse_orderbook + mlb_book_capture._levels run
    against ingame_book_depth_kalshi's own fixture body, whose expected
    best_bid=0.13 / best_ask=0.82 are already proven by that module's own test
    (test_parse_orderbook_best_bid_ask_and_thinness)."""
    market = {"sport": "mlb", "series_ticker": "KXMLBGAME", "ticker": "T3",
              "event_ticker": "EVT3", "state": "live"}
    out = row.book_row(market, _ORDERBOOK_BODY, ts_ms=1700000002000,
                        capture_ts="2026-09-14T20:00:10.000000Z")
    assert out["yes_bid"] == 0.13 and round(out["yes_ask"], 6) == 0.82
    assert round(out["no_bid"], 6) == 0.18 and round(out["no_ask"], 6) == 0.87
    assert out["yes_bid_top5_asc"][-1] == [0.13, 5.0]
    assert out["depth_bid"] == 100 + 50 + 30 + 5
    assert out["depth_ask"] == 56136 + 6550 + 80


# --------------------------------------------------------------------------- #
# (d) archive path selection under the two pod env flags                      #
# --------------------------------------------------------------------------- #
def test_archive_path_is_live_only_with_both_flags_set():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    scratch = capture.SCRATCH_ARCHIVE_ROOT / "mlb" / "2026-09-14.jsonl"
    live = capture.LIVE_ARCHIVE_ROOT / "mlb" / "2026-09-14.jsonl"
    assert capture.archive_path("mlb", now, {}) == scratch
    assert capture.archive_path("mlb", now, {"CV_CAPTURE_POD": "1"}) == scratch
    assert capture.archive_path("mlb", now, {"CV_KALSHI_BOOK_ARCHIVE_LIVE": "1"}) == scratch
    both = {"CV_CAPTURE_POD": "1", "CV_KALSHI_BOOK_ARCHIVE_LIVE": "1"}
    assert capture.archive_path("mlb", now, both) == live
    assert capture.live_archive_enabled(both)
    assert not capture.live_archive_enabled({"CV_CAPTURE_POD": "1"})


# --------------------------------------------------------------------------- #
# bonus: capture_once end-to-end off a PRE-SEEDED discovery cache (no HTTP)   #
# --------------------------------------------------------------------------- #
class _StubClient:
    """GovernedClient.get returns (body, ts_ms) -- this stub mirrors that shape."""

    def __init__(self, body):
        self.n_429 = 0
        self.n_errors = 0
        self.body = body
        self.urls = []

    def get(self, url, sport, *, n_active_sports=1):
        self.urls.append(url)
        return self.body, 1700000000000


def _seeded_state(market):
    return {"discovery_cache": {"mlb": {"ts": 100.0, "markets": [market]}}}


def test_capture_once_polls_due_market_and_writes_snapshot_plus_heartbeat(tmp_path, monkeypatch):
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    # close_time 1h out, well inside mlb's 3.5h typical duration -> reclassified
    # "live" (5s cadence) by capture_once itself, same as a freshly discovered market.
    market = {"ticker": "T1", "series_ticker": "KXMLBGAME", "event_ticker": "EVT1",
              "sport": "mlb", "close_time": "2026-09-14T21:00:00Z"}
    monkeypatch.setattr(row, "parse_orderbook", lambda _b: (0.5, 0.5, 0.0, 0.0, 2))
    monkeypatch.setattr(row, "_raw_ladders", lambda _b: {"yes": [["0.5", "1"]], "no": [["0.5", "1"]]})
    client = _StubClient({"fixture": "one-level book"})
    result = capture.capture_once(client=client, sports=["mlb"], now=now,
                                   state=_seeded_state(market), clock=lambda: 100.0,
                                   output_root=tmp_path)
    assert result["n_due"] == 1 and result["n_discovered"] == 1
    rows = [json.loads(l) for l in (tmp_path / "mlb" / "2026-09-14.jsonl")
            .read_text(encoding="ascii").splitlines()]
    assert len(rows) == 1 and rows[0]["record_type"] == "snapshot" and rows[0]["ticker"] == "T1"
    hb = json.loads((tmp_path / "mlb" / "_heartbeat.json").read_text(encoding="ascii"))
    assert hb["n_snapshot_rows_tick"] == 1 and hb["n_markets_live"] == 1
    assert client.urls == ["https://api.elections.kalshi.com/trade-api/v2/markets/T1/orderbook"]


def test_capture_once_records_fetch_error_when_the_client_returns_none(tmp_path):
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    market = {"ticker": "T9", "series_ticker": "KXMLBGAME", "event_ticker": "EVT9",
              "sport": "mlb", "close_time": "2026-09-14T21:00:00Z"}
    client = _StubClient(None)
    capture.capture_once(client=client, sports=["mlb"], now=now,
                          state=_seeded_state(market), clock=lambda: 100.0, output_root=tmp_path)
    rows = [json.loads(l) for l in (tmp_path / "mlb" / "2026-09-14.jsonl")
            .read_text(encoding="ascii").splitlines()]
    assert rows[0]["record_type"] == "fetch_error" and rows[0]["ticker"] == "T9"
    assert rows[0]["reason"] == "fetch_failed" and rows[0]["capture_version"] == capture.CAPTURE_VERSION
