"""Per-file tests for depth_capture (canned fixtures only -- NO live network calls).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_depth_capture.py -q

Acceptance criteria:
  1. fetch_orderbook_row parses a real-shaped orderbook_fp body into the
     canonical row (yes_bids/yes_asks/depth_totals/provenance fields).
  2. A malformed rung (bad price/size) is skipped, never fabricated.
  3. Both ladders empty -> row is None (VOID, never a fake empty row).
  4. A fetch exception isolates to None; a 429 records stats + cools down.
  5. capture_depth_snapshot lists tickers per series then fetches one row per
     ticker, respecting max_tickers; an unsupported sport yields [].
  6. append_rows_atomic appends across multiple calls (round-trips exact JSON)
     and returns 0 (never raises) on an unwritable path.
  7. run_capture_pass writes one dated JSONL per sport and aggregates
     n_requests_total/n_429_total across sports.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.odds_provider import depth_capture as dc


def _book(yes_rungs, no_rungs):
    return {"orderbook_fp": {"yes_dollars": yes_rungs, "no_dollars": no_rungs}}


def test_fetch_orderbook_row_parses_real_shape():
    body = _book([["0.42", "150.00"], ["0.41", "10.00"]],
                 [["0.58", "75.50"]])
    row = dc.fetch_orderbook_row("mlb", "KXMLBGAME-26JUL07COLLAD-LAD",
                                  "KXMLBGAME-26JUL07COLLAD", "2026-07-07T00:00:00Z",
                                  http=lambda url: body)
    assert row is not None
    assert row["sport"] == "mlb"
    assert row["ticker"] == "KXMLBGAME-26JUL07COLLAD-LAD"
    assert row["event_ticker"] == "KXMLBGAME-26JUL07COLLAD"
    assert row["yes_bids"] == [[0.42, 150.0], [0.41, 10.0]]
    assert row["yes_asks"] == [[0.58, 75.5]]
    assert row["depth_totals"] == {"yes_bid_total": 160.0, "yes_ask_total": 75.5}
    assert row["source"] == "kalshi"
    assert row["capture_version"] == dc.CAPTURE_VERSION
    assert row["ts"] == "2026-07-07T00:00:00Z"
    assert row["fetched_at"] == "2026-07-07T00:00:00Z"
    assert "orderbook" in row["source_url"]


def test_malformed_rung_skipped_never_fabricated():
    body = _book([["0.42", "150.00"], ["bad", "10.00"], ["0.10"]], [])
    row = dc.fetch_orderbook_row("mlb", "T-1", "E-1", "ts", http=lambda url: body)
    assert row is not None
    assert row["yes_bids"] == [[0.42, 150.0]]
    assert row["yes_asks"] == []


def test_both_ladders_empty_yields_none():
    row = dc.fetch_orderbook_row("mlb", "T-1", "E-1", "ts", http=lambda url: _book([], []))
    assert row is None


def test_missing_orderbook_key_yields_none():
    row = dc.fetch_orderbook_row("mlb", "T-1", "E-1", "ts", http=lambda url: {"foo": "bar"})
    assert row is None


def test_fetch_exception_isolates_to_none():
    def boom(url):
        raise RuntimeError("network down")
    row = dc.fetch_orderbook_row("mlb", "T-1", "E-1", "ts", http=boom)
    assert row is None


def test_429_records_stats_and_cools_down():
    import urllib.error

    def raise_429(url):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    stats: dict = {}
    slept = []
    row = dc.fetch_orderbook_row("mlb", "T-1", "E-1", "ts", http=raise_429,
                                  stats=stats, sleep_fn=slept.append)
    assert row is None
    assert stats["n_requests"] == 1
    assert stats["n_429"] == 1
    assert slept  # a cooldown sleep was attempted


def test_capture_depth_snapshot_lists_then_fetches_per_ticker():
    # mlb has 4 wired series (kalshi_series_spec.SERIES_SPEC); only the first
    # (KXMLBGAME) has markets here -- the others legitimately return empty.
    listing_body = {"markets": [
        {"ticker": "KXMLBGAME-A-HOME", "event_ticker": "KXMLBGAME-A"},
        {"ticker": "KXMLBGAME-A-AWAY", "event_ticker": "KXMLBGAME-A"},
    ]}
    empty_listing = {"markets": []}
    book_body = _book([["0.5", "10.0"]], [["0.5", "10.0"]])
    calls = []

    def fake_http(url):
        calls.append(url)
        if "/orderbook" in url:
            return book_body
        if "series_ticker=KXMLBGAME&" in url:
            return listing_body
        return empty_listing

    rows = dc.capture_depth_snapshot("mlb", http=fake_http, now_iso="ts1")
    assert len(rows) == 2
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"KXMLBGAME-A-HOME", "KXMLBGAME-A-AWAY"}
    assert all(r["ts"] == "ts1" for r in rows)
    # one listing call per series (4 for mlb) + one orderbook call per ticker
    assert sum(1 for u in calls if "/orderbook" in u) == 2


def test_capture_depth_snapshot_respects_max_tickers():
    listing_body = {"markets": [
        {"ticker": "T-1", "event_ticker": "E-1"},
        {"ticker": "T-2", "event_ticker": "E-1"},
        {"ticker": "T-3", "event_ticker": "E-1"},
    ]}
    book_body = _book([["0.5", "10.0"]], [])

    def fake_http(url):
        return book_body if "/orderbook" in url else listing_body

    rows = dc.capture_depth_snapshot("mlb", http=fake_http, max_tickers=1)
    assert len(rows) == 1


def test_capture_depth_snapshot_unsupported_sport_yields_empty():
    rows = dc.capture_depth_snapshot("curling", http=lambda url: {"markets": []})
    assert rows == []


def test_capture_depth_snapshot_listing_failure_isolated():
    def fake_http(url):
        raise RuntimeError("dead feed")
    rows = dc.capture_depth_snapshot("mlb", http=fake_http)
    assert rows == []


def test_append_rows_atomic_round_trips_and_accumulates(tmp_path):
    path = tmp_path / "depth" / "mlb" / "2026-07-07.jsonl"
    row1 = {"ticker": "A", "ts": "t1"}
    row2 = {"ticker": "B", "ts": "t2"}
    n1 = dc.append_rows_atomic([row1], path)
    n2 = dc.append_rows_atomic([row2], path)
    assert n1 == 1
    assert n2 == 1
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == row1
    assert json.loads(lines[1]) == row2


def test_append_rows_atomic_empty_rows_is_noop(tmp_path):
    path = tmp_path / "nowhere" / "x.jsonl"
    assert dc.append_rows_atomic([], path) == 0
    assert not path.exists()


def test_append_rows_atomic_unwritable_path_never_raises(tmp_path):
    # A path whose parent is actually a FILE (not a dir) cannot be mkdir'd into.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_path = blocker / "sub" / "x.jsonl"
    n = dc.append_rows_atomic([{"a": 1}], bad_path)
    assert n == 0


def test_run_capture_pass_writes_dated_jsonl_and_aggregates_stats(tmp_path):
    # Only KXMLBGAME (mlb's first series) and KXATPMATCH (tennis's first series)
    # carry a market here -- every other wired series legitimately returns empty,
    # so the ticker de-dupe below reflects one real market per sport.
    listing_body = {"markets": [{"ticker": "T-1", "event_ticker": "E-1"}]}
    empty_listing = {"markets": []}
    book_body = _book([["0.5", "10.0"]], [])

    def fake_http(url):
        if "/orderbook" in url:
            return book_body
        if "series_ticker=KXMLBGAME&" in url or "series_ticker=KXATPMATCH&" in url:
            return listing_body
        return empty_listing

    summary = dc.run_capture_pass(
        ["mlb", "tennis"], http=fake_http, base_dir=tmp_path,
        stagger_sec=0.0, max_tickers_per_sport=10, now_iso="2026-07-07T01:02:03Z")

    assert summary["ts"] == "2026-07-07T01:02:03Z"
    assert summary["sports"]["mlb"]["n_markets"] == 1
    assert summary["sports"]["mlb"]["n_rows_written"] == 1
    mlb_path = tmp_path / "mlb" / "2026-07-07.jsonl"
    assert mlb_path.is_file()
    row = json.loads(mlb_path.read_text(encoding="utf-8").strip())
    assert row["ticker"] == "T-1"
    assert summary["sports"]["tennis"]["n_markets"] == 1
    assert summary["n_requests_total"] > 0


def test_capture_depth_snapshot_governor_caller_gates_every_request(monkeypatch):
    """governor_caller="depth_capture" resolves a REAL governor and acquires a
    token before EVERY listing + orderbook call; the default (None, every
    pre-existing caller) resolves to governor=None so before_request is a no-op."""
    listing_body = {"markets": [{"ticker": "T-1", "event_ticker": "E-1"}]}
    empty_listing = {"markets": []}
    book_body = _book([["0.5", "10.0"]], [])

    def fake_http(url):
        if "/orderbook" in url:
            return book_body
        if "series_ticker=KXMLBGAME&" in url:
            return listing_body
        return empty_listing

    calls = []
    real_before = dc._governor_before

    def spy_before(governor, sport):
        calls.append(governor is not None)
        return real_before(governor, sport)

    monkeypatch.setattr(dc, "_governor_before", spy_before)
    dc.capture_depth_snapshot("mlb", http=fake_http, governor_caller="depth_capture")
    assert calls  # at least one before_request call was made
    assert all(calls)  # every call resolved a REAL (non-None) governor

    calls.clear()
    dc.capture_depth_snapshot("mlb", http=fake_http)  # governor_caller=None (default)
    assert calls
    assert not any(calls)  # unpaced by default -- byte-identical for old callers


def test_run_capture_pass_per_sport_failure_isolated(tmp_path, monkeypatch):
    def boom_snapshot(sport, **kwargs):
        if sport == "mlb":
            raise RuntimeError("boom")
        return []
    monkeypatch.setattr(dc, "capture_depth_snapshot", boom_snapshot)
    summary = dc.run_capture_pass(["mlb", "tennis"], base_dir=tmp_path)
    assert summary["sports"]["mlb"]["n_markets"] == 0
    assert summary["sports"]["tennis"]["n_markets"] == 0


def test_list_tickers_skips_markets_more_than_a_day_out(monkeypatch):
    """S105: the per-pass ticker budget must reach markets that can be IN PLAY.
    Kalshi opens game markets days ahead, and 88.1 pct of the captured
    depth_history/mlb rows were for a game 1-3 days out -- the budget never
    reached the live slate. is_future_game is stubbed so the test is
    clock-independent."""
    future = "KXMLBGAME-FUTURE-AAA"
    listing = {"markets": [{"ticker": future, "event_ticker": "KXMLBGAME-FUTURE"},
                           {"ticker": "KXMLBGAME-LIVE-AAA", "event_ticker": "KXMLBGAME-LIVE"}]}
    monkeypatch.setattr(dc, "is_future_game", lambda t, now: t == future)
    rows = dc.capture_depth_snapshot(
        "mlb", http=lambda url: (listing if "/markets?" in url
                                 else _book([["0.50", "1"]], [["0.50", "1"]])))
    assert rows, "the live ticker must still be captured"
    assert {r["ticker"] for r in rows} == {"KXMLBGAME-LIVE-AAA"}
