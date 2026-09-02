"""S19 construct test: bounded orderbook concurrency keeps the one governor path."""
import json
import threading
import time
import urllib.error
from datetime import datetime, timezone

from scripts.platformkit.ingame import mlb_book_capture as capture


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"orderbook_fp": {"yes_dollars": [[40, 1]],
                                             "no_dollars": [[60, 1]]}}).encode("utf-8")


def _live_games(_client, _date, _state):
    return [{"game_pk": str(game), "event_ticker": "EV" + str(game),
             "tickers": ["T%02dA" % game, "T%02dB" % game], "game_state": {}}
            for game in range(9)]


def test_bounded_parallel_fetches_preserve_governor_and_row_order(monkeypatch, tmp_path):
    calls, lock = {"before": 0, "report": 0}, threading.Lock()

    def counted_before(*_args, **_kwargs):
        with lock:
            calls["before"] += 1

    def counted_report(*_args, **_kwargs):
        with lock:
            calls["report"] += 1

    monkeypatch.setattr(capture, "before_request", counted_before)
    monkeypatch.setattr(capture, "report_429", counted_report)

    def run(max_concurrency, path):
        active = {"in_flight": 0, "peak": 0}

        def opener(request, **_kwargs):
            with lock:
                active["in_flight"] += 1
                active["peak"] = max(active["peak"], active["in_flight"])
            try:
                time.sleep(0.2)
                if request.full_url.endswith("/T08B/orderbook"):
                    raise urllib.error.HTTPError(request.full_url, 429, "limited", None, None)
                return _Response()
            finally:
                with lock:
                    active["in_flight"] -= 1

        started = time.monotonic()
        result = capture.capture_once(client=capture.GovernedClient(opener=opener),
                                      now=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                      live_games_fn=_live_games, output=path,
                                      max_concurrency=max_concurrency)
        return result, time.monotonic() - started, active["peak"]

    serial, serial_wall, _ = run(1, tmp_path / "serial.jsonl")
    before = calls["before"]
    reports = calls["report"]
    concurrent, concurrent_wall, peak = run(capture.MAX_FETCH_CONCURRENCY,
                                             tmp_path / "concurrent.jsonl")

    assert concurrent_wall < serial_wall / 2
    assert peak <= capture.MAX_FETCH_CONCURRENCY
    assert calls["before"] - before == 18
    assert calls["report"] - reports == 1
    assert concurrent["n_429"] == 1 and concurrent["cadence_sec"] == 10.0
    assert [row for row in concurrent["rows"] if row["record_type"] == "fetch_error"] == [
        {"record_type": "fetch_error", "venue": "kalshi", "sport": "mlb", "game_pk": "8",
         "ticker": "T08B", "event_ticker": "EV8", "capture_ts": "2026-09-01T00:00:00.000000Z",
         "error": "fetch_failed", "derived_age_ceiling_sec": 5.0}]
    assert serial["rows"] == concurrent["rows"]
    assert (tmp_path / "serial.jsonl").read_bytes() == (tmp_path / "concurrent.jsonl").read_bytes()
