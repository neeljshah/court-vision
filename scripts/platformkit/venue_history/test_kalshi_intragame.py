"""Tests for scripts.platformkit.venue_history.kalshi_intragame. Offline, canned HTTP only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.venue_history import kalshi_intragame as ki


def _fake_http(pages: Dict[str, Any], candles_by_ticker: Dict[str, List[Dict[str, Any]]]):
    def http(url: str) -> Any:
        if "/candlesticks" in url:
            ticker = url.split("/markets/")[1].split("/candlesticks")[0]
            return {"candlesticks": candles_by_ticker.get(ticker, [])}
        cursor = "" if "cursor=" not in url else url.split("cursor=")[1].split("&")[0]
        return pages[cursor]
    return http


def test_cursor_pagination_resumable(tmp_path: Path) -> None:
    """Two pages chained by cursor; a resumed run with saved progress skips page 1."""
    m1 = {"ticker": "KXMLBGAME-26JUN01-AAA", "event_ticker": "KXMLBGAME-26JUN01",
          "close_time": "2026-06-01T00:00:00Z", "result": "yes"}
    m2 = {"ticker": "KXMLBGAME-26JUN02-BBB", "event_ticker": "KXMLBGAME-26JUN02",
          "close_time": "2026-06-02T00:00:00Z", "result": "no"}
    pages = {
        "": {"markets": [m1], "cursor": "CUR1"},
        "CUR1": {"markets": [m2], "cursor": ""},
    }
    http = _fake_http(pages, {})
    out_dir = tmp_path / "kalshi_out"
    result = ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http,
                              sleep_sec=0, sleep_fn=lambda s: None, max_requests=20)
    assert result["n_markets_total_done"] == 2
    assert result["exhausted"] is True
    assert (out_dir / "KXMLBGAME-26JUN01-AAA.jsonl").is_file()
    assert (out_dir / "KXMLBGAME-26JUN02-BBB.jsonl").is_file()

    # Simulate an interrupted run: progress already has ticker 1 done + cursor at CUR1.
    prog_path = out_dir / "_progress.json"
    prog = json.loads(prog_path.read_text(encoding="utf-8"))
    assert prog["cursor"] == ""  # fully exhausted from the run above
    # Force a resume scenario: seed progress mid-way and confirm it is honoured.
    seeded = {"cursor": "CUR1", "done_tickers": ["KXMLBGAME-26JUN01-AAA"],
              "earliest_close_time": "2026-06-01T00:00:00Z"}
    prog_path.write_text(json.dumps(seeded), encoding="utf-8")
    for f in out_dir.glob("*.jsonl"):
        f.unlink()
    result2 = ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http,
                               sleep_sec=0, sleep_fn=lambda s: None, max_requests=20)
    # Only ticker 2 should be (re-)fetched since ticker 1 was marked done in progress.
    assert not (out_dir / "KXMLBGAME-26JUN01-AAA.jsonl").exists()
    assert (out_dir / "KXMLBGAME-26JUN02-BBB.jsonl").is_file()
    assert result2["n_markets_fetched_this_run"] == 1


def test_min_close_ts_never_sent() -> None:
    """The enumerator must never place min_close_ts on the wire (server-side no-op)."""
    seen_urls: List[str] = []

    def http(url: str) -> Any:
        seen_urls.append(url)
        return {"markets": [], "cursor": ""}

    ki.list_settled_markets_page("KXMLBGAME", http=http)
    assert len(seen_urls) == 1
    assert "min_close_ts" not in seen_urls[0]


def test_max_close_ts_is_forwarded() -> None:
    seen_urls: List[str] = []

    def http(url: str) -> Any:
        seen_urls.append(url)
        return {"markets": [], "cursor": ""}

    ki.list_settled_markets_page("KXMLBGAME", max_close_ts=1234567890, http=http)
    assert "max_close_ts=1234567890" in seen_urls[0]


def test_empty_price_object_handled_distinctly_from_populated() -> None:
    """A tradeless-minute candle (price={}) falls back to bid/ask mid and is
    flagged traded=False; a traded candle uses price.close_dollars and traded=True."""
    tradeless = {
        "end_period_ts": 1782865560, "price": {},
        "yes_bid": {"close_dollars": "0.1300"}, "yes_ask": {"close_dollars": "0.9500"},
    }
    traded = {
        "end_period_ts": 1782958260, "price": {"close_dollars": "0.5300"},
        "yes_bid": {"close_dollars": "0.4800"}, "yes_ask": {"close_dollars": "0.5400"},
    }
    p1 = ki._candle_to_point(tradeless)
    p2 = ki._candle_to_point(traded)
    assert p1 is not None and p1["traded"] is False
    assert abs(p1["prob"] - 0.54) < 1e-6  # mid of bid/ask fallback (0.13,0.95)
    assert p2 is not None and p2["traded"] is True
    assert abs(p2["prob"] - 0.53) < 1e-6


def test_empty_price_and_no_quotes_skipped() -> None:
    """price={} AND no usable bid/ask -> the candle is skipped, never fabricated."""
    dead = {"end_period_ts": 1782865560, "price": {}, "yes_bid": {}, "yes_ask": {}}
    assert ki._candle_to_point(dead) is None


def test_discovery_window_exclusion_flag() -> None:
    """Games whose close_time falls inside 2026-06-19..07-02 are flagged, not silently
    dropped -- the honest independent subset excludes them downstream. Default sport
    (mlb) is the one that actually had the live discovery capture."""
    assert ki.in_discovery_window("2026-06-25T12:00:00Z") is True
    assert ki.in_discovery_window("2026-06-18T23:59:59Z") is False
    assert ki.in_discovery_window("2026-07-03T00:00:01Z") is False
    assert ki.in_discovery_window(ki.DISCOVERY_WINDOW_START) is True
    assert ki.in_discovery_window(ki.DISCOVERY_WINDOW_END) is True


def test_discovery_window_never_flagged_for_nba() -> None:
    """NBA never had the live in-play discovery capture running -- a date that WOULD
    match the MLB window must never be flagged for nba, even by calendar coincidence."""
    assert ki.in_discovery_window("2026-06-25T12:00:00Z", sport="nba") is False
    assert ki.in_discovery_window("2026-06-25T12:00:00Z", sport="NBA") is False
    assert ki.in_discovery_window(ki.DISCOVERY_WINDOW_START, sport="nba") is False
    # mlb (any case) is unaffected
    assert ki.in_discovery_window("2026-06-25T12:00:00Z", sport="MLB") is True


def test_nba_series_param_end_to_end(tmp_path: Path) -> None:
    """run_backfill with series='KXNBAGAME', sport='nba' writes docs stamped sport='nba'
    and NEVER flags in_discovery_window True, even for a close_time inside the MLB window."""
    m = {"ticker": "KXNBAGAME-26JUN25NYKSAS-NYK", "event_ticker": "KXNBAGAME-26JUN25NYKSAS",
         "close_time": "2026-06-25T03:00:00Z", "result": "yes"}
    pages = {"": {"markets": [m], "cursor": ""}}
    http = _fake_http(pages, {"KXNBAGAME-26JUN25NYKSAS-NYK": []})
    out_dir = tmp_path / "nba_out"
    result = ki.run_backfill("KXNBAGAME", "nba", out_dir=out_dir, http=http,
                              sleep_sec=0, sleep_fn=lambda s: None, max_requests=20)
    assert result["series_ticker"] == "KXNBAGAME"
    assert result["sport"] == "nba"
    doc = json.loads((out_dir / "KXNBAGAME-26JUN25NYKSAS-NYK.jsonl").read_text(encoding="utf-8"))
    assert doc["sport"] == "nba"
    assert doc["series_ticker"] == "KXNBAGAME"
    assert doc["in_discovery_window"] is False  # NBA never had the discovery window


def test_candle_window_fits_server_cap() -> None:
    """The requested candle window must never exceed MAX_CANDLES_PER_CALL minutes,
    regardless of how long the market was listed before its close."""
    seen_urls: List[str] = []

    def http(url: str) -> Any:
        seen_urls.append(url)
        return {"candlesticks": []}

    ki.fetch_market_candles("KXMLBGAME", "KXMLBGAME-26JUN01-AAA",
                             "2026-06-04T00:00:00Z", http=http)
    url = seen_urls[0]
    qs = dict(p.split("=") for p in url.split("?")[1].split("&"))
    span_min = (int(qs["end_ts"]) - int(qs["start_ts"])) / 60.0
    assert span_min <= ki.MAX_CANDLES_PER_CALL + 1  # +1 float rounding slack


def test_run_backfill_stamps_provenance_and_discovery_flag(tmp_path: Path) -> None:
    m = {"ticker": "KXMLBGAME-26JUN25-XYZ", "event_ticker": "KXMLBGAME-26JUN25",
         "close_time": "2026-06-25T12:00:00Z", "result": "yes"}
    pages = {"": {"markets": [m], "cursor": ""}}
    candle = {"end_period_ts": 1750852800, "price": {"close_dollars": "0.6000"}}
    http = _fake_http(pages, {"KXMLBGAME-26JUN25-XYZ": [candle]})
    out_dir = tmp_path / "out"
    ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http,
                     sleep_sec=0, sleep_fn=lambda s: None, max_requests=20)
    doc = json.loads((out_dir / "KXMLBGAME-26JUN25-XYZ.jsonl").read_text(encoding="utf-8"))
    assert doc["series_ticker"] == "KXMLBGAME"
    assert doc["sport"] == "mlb"
    assert doc["result"] == "yes"
    assert doc["in_discovery_window"] is True  # 2026-06-25 is inside 06-19..07-02
    assert doc["n_candles"] == 1


def test_cursor_continuation_never_refetches_done_ticker_candles(tmp_path: Path) -> None:
    """A resumed run with a persisted cursor + done_tickers must NEVER re-issue a
    candlesticks call for a ticker already marked done -- assert the call count."""
    m1 = {"ticker": "KXMLBGAME-26JUN01-AAA", "event_ticker": "KXMLBGAME-26JUN01",
          "close_time": "2026-06-01T00:00:00Z", "result": "yes"}
    m2 = {"ticker": "KXMLBGAME-26JUN02-BBB", "event_ticker": "KXMLBGAME-26JUN02",
          "close_time": "2026-06-02T00:00:00Z", "result": "no"}
    # Both tickers appear again on the resumed page (as a real Kalshi cursor page
    # would replay if the caller re-requested from an earlier cursor by mistake).
    pages = {"CUR1": {"markets": [m1, m2], "cursor": ""}}
    candle_calls: List[str] = []

    def http(url: str) -> Any:
        if "/candlesticks" in url:
            ticker = url.split("/markets/")[1].split("/candlesticks")[0]
            candle_calls.append(ticker)
            return {"candlesticks": []}
        return pages["CUR1"]

    out_dir = tmp_path / "resume"
    prog_path = out_dir / "_progress.json"
    out_dir.mkdir(parents=True)
    prog_path.write_text(json.dumps({
        "cursor": "CUR1", "done_tickers": ["KXMLBGAME-26JUN01-AAA"],
        "earliest_close_time": "2026-06-01T00:00:00Z",
    }), encoding="utf-8")

    result = ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http,
                              sleep_sec=0, sleep_fn=lambda s: None, max_requests=20)
    assert candle_calls == ["KXMLBGAME-26JUN02-BBB"]  # AAA never re-fetched
    assert result["n_markets_fetched_this_run"] == 1
    assert not (out_dir / "KXMLBGAME-26JUN01-AAA.jsonl").exists()


def test_governor_caller_opt_in_gates_every_request(tmp_path: Path, monkeypatch) -> None:
    """governor_caller="backfill" resolves a REAL governor and gates BOTH the page
    listing call and the per-market candle call; default (None) stays a no-op --
    same opt-in idiom as inplay_kalshi.fetch_inplay's governor_caller."""
    calls = []
    monkeypatch.setattr(ki, "_governor_before",
                        lambda governor, sport: calls.append((governor, sport)))
    m = {"ticker": "KXMLBGAME-26JUN25-XYZ", "event_ticker": "e", "close_time": "2026-06-25T12:00:00Z",
         "result": "yes"}
    pages = {"": {"markets": [m], "cursor": ""}}
    http = _fake_http(pages, {"KXMLBGAME-26JUN25-XYZ": []})
    out_dir = tmp_path / "gov"
    ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http, sleep_sec=0,
                    sleep_fn=lambda s: None, max_requests=20)
    assert calls and all(governor is None for governor, _sport in calls)  # no caller -> no-op

    calls.clear()
    for f in out_dir.glob("*.jsonl"):
        f.unlink()
    (out_dir / "_progress.json").unlink()
    ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http, sleep_sec=0,
                    sleep_fn=lambda s: None, max_requests=20, governor_caller="backfill")
    assert len(calls) == 2  # one page-list call + one candles call
    assert all(sport == "mlb" and governor is not None for governor, sport in calls)


def test_governor_reports_429(tmp_path: Path, monkeypatch) -> None:
    """A 429 on the governed path must report_429 so the shared backoff engages."""
    import urllib.error
    reported = []
    monkeypatch.setattr(ki, "_governor_report_429", lambda governor: reported.append(governor))

    def http(url: str) -> Any:
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    out_dir = tmp_path / "gov429"
    result = ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http, sleep_sec=0,
                             sleep_fn=lambda s: None, max_requests=5, governor_caller="backfill")
    assert result["n_markets_total_done"] == 0  # the failed page yields no markets
    assert len(reported) == 1


def test_max_requests_budget_respected(tmp_path: Path) -> None:
    """A tight max_requests budget stops the run early without exhausting pages."""
    markets = [{"ticker": "KXMLBGAME-26JUN0%d-T" % i, "event_ticker": "e%d" % i,
                "close_time": "2026-05-01T00:00:00Z", "result": "yes"} for i in range(1, 4)]
    pages = {"": {"markets": markets, "cursor": "MORE"}, "MORE": {"markets": [], "cursor": ""}}
    http = _fake_http(pages, {})
    out_dir = tmp_path / "budget"
    result = ki.run_backfill("KXMLBGAME", "mlb", out_dir=out_dir, http=http,
                              sleep_sec=0, sleep_fn=lambda s: None, max_requests=2)
    assert result["n_requests"] <= 2
    assert result["n_markets_total_done"] <= 1
