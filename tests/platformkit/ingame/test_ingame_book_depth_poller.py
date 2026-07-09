"""Per-file test for ingame_book_depth_poller (discover+poll+sidecar+bounded serve).

OFFLINE + deterministic: http injected, clock injected (no real sleep, no network),
sidecar_dir is tmp_path.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_poller.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.ingame import ingame_book_depth_poller as poller

_MARKETS_BODY = {"markets": [{"ticker": "KXMLBGAME-TEST-AAA"}, {"ticker": "KXMLBGAME-TEST-BBB"}]}
_ORDERBOOK_BODY = {
    "orderbook_fp": {"yes_dollars": [["0.50", "10"]], "no_dollars": [["0.48", "10"]]}
}
_TRADES_BODY = {"trades": []}


def _http_kalshi(url: str):
    if "/markets?" in url and "series_ticker" in url:
        return _MARKETS_BODY
    if "orderbook" in url:
        return _ORDERBOOK_BODY
    if "trades" in url:
        return _TRADES_BODY
    raise AssertionError("unexpected url %s" % url)


def test_poll_kalshi_depth_discovers_and_writes_sidecar(tmp_path):
    """mlb has 4 wired series (game/total/spread/team_total); the stub returns the
    same 2 tickers per series -> 8 raw discoveries, capped to 5 by
    max_markets_per_sport (the bound applies to the FLATTENED ticker list)."""
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    summary = poller.poll_kalshi_depth(["mlb"], http=_http_kalshi, sidecar_dir=tmp_path,
                                       now=lambda: now_dt, max_markets_per_sport=5)
    assert summary["n_snapshotted"] == 5
    sidecar = tmp_path / "kalshi" / "2026-07-06.jsonl"
    assert sidecar.is_file()
    lines = sidecar.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 5
    row = json.loads(lines[0])
    assert row["venue"] == "kalshi" and row["sport"] == "mlb"


def test_poll_kalshi_depth_bounded_per_sport(tmp_path):
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    summary = poller.poll_kalshi_depth(["mlb"], http=_http_kalshi, sidecar_dir=tmp_path,
                                       now=lambda: now_dt, max_markets_per_sport=1)
    assert summary["n_snapshotted"] == 1


def test_poll_kalshi_depth_single_series_sport(tmp_path):
    """tennis has 2 moneyline-only series (ATP+WTA); the stub returns the same 2
    tickers per series -> 4 raw discoveries, capped to 3."""
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    summary = poller.poll_kalshi_depth(["tennis"], http=_http_kalshi, sidecar_dir=tmp_path,
                                       now=lambda: now_dt, max_markets_per_sport=3)
    assert summary["n_snapshotted"] == 3


def test_poll_kalshi_depth_no_series_for_sport_is_empty(tmp_path):
    summary = poller.poll_kalshi_depth(["not_a_sport"], http=_http_kalshi, sidecar_dir=tmp_path)
    assert summary["n_snapshotted"] == 0


_TRADES_WITH_PRICES = {"trades": [
    {"created_time": "2026-07-06T00:00:01.000000Z", "yes_price_dollars": "0.55", "count": "2"},
]}


def _http_kalshi_with_trades(url: str):
    if "/markets?" in url and "series_ticker" in url:
        return _MARKETS_BODY
    if "orderbook" in url:
        return _ORDERBOOK_BODY
    if "trades" in url:
        return _TRADES_WITH_PRICES
    raise AssertionError("unexpected url %s" % url)


def test_poll_kalshi_depth_persists_trades_with_prices_and_dedups(tmp_path):
    """Trades tape prices land in the parallel kalshi_trades sidecar; the
    existing kalshi depth summary row is unchanged (no leaked _new_trades/
    _trade_watermark keys); a second poll with the same tape dedups to zero
    new trades via the threaded watermark."""
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    watermarks: dict = {}
    prev: dict = {}
    summary = poller.poll_kalshi_depth(["tennis"], http=_http_kalshi_with_trades, sidecar_dir=tmp_path,
                                       now=lambda: now_dt, max_markets_per_sport=1,
                                       prev_by_ticker=prev, trade_watermark_by_ticker=watermarks)
    assert summary["n_trades"] == 1
    depth_row = summary["rows"][0]
    assert "_new_trades" not in depth_row and "_trade_watermark" not in depth_row

    trades_sidecar = tmp_path / "kalshi_trades" / "2026-07-06.jsonl"
    assert trades_sidecar.is_file()
    trade_lines = trades_sidecar.read_text(encoding="ascii").strip().splitlines()
    assert len(trade_lines) == 1
    trade_row = json.loads(trade_lines[0])
    assert trade_row["price"] == 0.55
    assert trade_row["ticker"] == "KXMLBGAME-TEST-AAA" and trade_row["sport"] == "tennis"

    depth_sidecar = tmp_path / "kalshi" / "2026-07-06.jsonl"
    depth_lines = depth_sidecar.read_text(encoding="ascii").strip().splitlines()
    on_disk_row = json.loads(depth_lines[0])
    assert "_new_trades" not in on_disk_row and "_trade_watermark" not in on_disk_row
    assert set(on_disk_row) == set(depth_row)  # existing summary row shape unchanged

    # second poll, same tape + threaded watermark -> no duplicate trade line
    summary2 = poller.poll_kalshi_depth(["tennis"], http=_http_kalshi_with_trades, sidecar_dir=tmp_path,
                                        now=lambda: now_dt, max_markets_per_sport=1,
                                        prev_by_ticker=prev, trade_watermark_by_ticker=watermarks)
    assert summary2["n_trades"] == 0
    assert len(trades_sidecar.read_text(encoding="ascii").strip().splitlines()) == 1


def test_poll_kalshi_depth_sticky_retention_survives_discovery_churn(tmp_path):
    """2026-07-11 fix: a ticker no longer returned by discovery (pushed off the
    top-N page by newer markets) stays in the poll set via active_by_sport --
    it is NOT dropped just because one tick's discovery didn't re-list it."""
    tick = {"n": 1}  # set by the test before each poll_kalshi_depth call, not per http call

    def _http(url: str):
        if "/markets?" in url and "series_ticker" in url:
            # tick 1: AAA only; tick 2: discovery churns to a totally different ticker
            if tick["n"] == 1:
                return {"markets": [{"ticker": "KXMLBGAME-TEST-AAA"}]}
            return {"markets": [{"ticker": "KXMLBGAME-TEST-CCC"}]}
        if "orderbook" in url:
            return _ORDERBOOK_BODY
        if "trades" in url:
            return _TRADES_BODY
        raise AssertionError("unexpected url %s" % url)

    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    active: dict = {}
    misses: dict = {}
    s1 = poller.poll_kalshi_depth(["tennis"], http=_http, sidecar_dir=tmp_path,
                                  now=lambda: now_dt, max_markets_per_sport=5,
                                  active_by_sport=active, miss_counts=misses)
    assert {r["ticker"] for r in s1["rows"]} == {"KXMLBGAME-TEST-AAA"}
    tick["n"] = 2
    s2 = poller.poll_kalshi_depth(["tennis"], http=_http, sidecar_dir=tmp_path,
                                  now=lambda: now_dt, max_markets_per_sport=5,
                                  active_by_sport=active, miss_counts=misses)
    # AAA is gone from THIS tick's discovery but still gets snapshotted (sticky).
    assert {r["ticker"] for r in s2["rows"]} == {"KXMLBGAME-TEST-AAA", "KXMLBGAME-TEST-CCC"}


def test_poll_kalshi_depth_evicts_after_max_consecutive_misses(tmp_path):
    """A ticker whose snapshot fails max_misses times in a row (genuinely
    closed/unreachable, not a discovery-page miss) IS evicted."""
    def _http(url: str):
        if "/markets?" in url and "series_ticker" in url:
            return {"markets": []}  # no fresh discovery this tick
        raise ConnectionError("market closed")  # every fetch for AAA fails

    active = {"tennis": ["KXMLBGAME-TEST-AAA"]}
    misses: dict = {}
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    for _ in range(3):
        poller.poll_kalshi_depth(["tennis"], http=_http, sidecar_dir=tmp_path,
                                 now=lambda: now_dt, active_by_sport=active,
                                 miss_counts=misses, max_misses=3)
    assert active["tennis"] == []  # evicted after 3 consecutive misses


def test_poll_polymarket_depth_resolves_once_and_caches(tmp_path):
    calls = {"gamma": 0, "book": 0}

    def _http(url: str):
        if "events?slug=" in url:
            calls["gamma"] += 1
            return [{"markets": [{"clobTokenIds": '["TOK1"]'}]}]
        if "book?token_id=" in url:
            calls["book"] += 1
            return {"bids": [{"price": "0.5", "size": "10"}], "asks": [{"price": "0.6", "size": "10"}]}
        raise AssertionError(url)

    token_cache: dict = {}
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    poller.poll_polymarket_depth(["slug-a"], http=_http, sidecar_dir=tmp_path,
                                now=lambda: now_dt, token_cache=token_cache)
    poller.poll_polymarket_depth(["slug-a"], http=_http, sidecar_dir=tmp_path,
                                now=lambda: now_dt, token_cache=token_cache)
    assert calls["gamma"] == 1  # resolved ONCE, cached for the second poll
    assert calls["book"] == 2  # book fetched fresh each poll
    sidecar = tmp_path / "polymarket" / "2026-07-06.jsonl"
    assert len(sidecar.read_text(encoding="ascii").strip().splitlines()) == 2


def test_poll_polymarket_depth_unresolvable_slug_skipped(tmp_path):
    summary = poller.poll_polymarket_depth(["dead-slug"], http=lambda u: [], sidecar_dir=tmp_path)
    assert summary["n_snapshotted"] == 0


def test_poll_once_combines_both_venues(tmp_path):
    def _poly_http(url):
        if "events" in url:
            return [{"markets": [{"clobTokenIds": '["TOK1"]'}]}]
        return {"bids": [{"price": "0.5", "size": "10"}], "asks": [{"price": "0.6", "size": "10"}]}

    hb = poller.poll_once(sports=["tennis"], polymarket_slugs=["slug-a"], sidecar_dir=tmp_path,
                          kalshi_http=_http_kalshi, poly_http=_poly_http,
                          now=lambda: datetime(2026, 7, 6, tzinfo=timezone.utc))
    assert hb["kalshi"]["n_snapshotted"] == 4  # 2 series x 2 tickers, default cap 5
    assert hb["polymarket"]["n_snapshotted"] == 1
    assert "kalshi_prev" in hb["state"]


def test_serve_bounded_always_stops_with_injected_clock(tmp_path):
    clock_calls = []
    fake_time = {"t": 0.0}

    def _fake_sleep(sec):
        clock_calls.append(sec)
        fake_time["t"] += sec

    def _fake_now():
        return fake_time["t"]

    summary = poller.serve_bounded(sports=[], polymarket_slugs=[], interval_sec=5.0,
                                   duration_sec=12.0, sidecar_dir=tmp_path,
                                   clock=_fake_sleep, time_fn=_fake_now)
    assert summary["n_ticks"] >= 1
    assert summary["measurement_only"] is True
    assert len(clock_calls) < 100  # bounded, never an infinite loop


def test_serve_bounded_tick_error_never_stops_loop(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _boom_poll_once(**kwargs):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(poller, "poll_once", _boom_poll_once)
    fake_time = {"t": 0.0}
    summary = poller.serve_bounded(duration_sec=10.0, interval_sec=3.0,
                                   clock=lambda s: fake_time.__setitem__("t", fake_time["t"] + s),
                                   time_fn=lambda: fake_time["t"])
    assert summary["n_ticks"] >= 1
    assert calls["n"] == summary["n_ticks"]
