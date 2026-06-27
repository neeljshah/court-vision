"""Per-file test for odds_provider.line_snapshot_daemon (offline, fake clock).

Proves: N ticks accrue history; a game inside the lock window yields a TRUE close
(line_store.get_close -> is_true_close=True); a feed error on one sport is isolated.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_line_snapshot_daemon.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.odds_provider import line_snapshot_daemon as daemon
from scripts.platformkit.odds_provider import line_store


def _agg(as_of_iso, commence_iso, *, status="ok"):
    """A one-game, two-venue moneyline aggregate payload (the shape aggregate() emits)."""
    return {
        "sport": "nba", "status": status, "as_of": as_of_iso,
        "sources": {"espn": "ok"},
        "events": [{
            "event_id": "G1", "sport": "nba", "home": "Knicks", "away": "Spurs",
            "commence_time": commence_iso, "as_of": as_of_iso,
            "prices": {
                "espn:DraftKings": {"home": 1.91, "away": 2.05},
                "kalshi": {"home": 1.90, "away": 2.07},
            },
        }],
    }


def test_n_ticks_write_history_and_capture_true_close(tmp_path):
    tip = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
    # Three ticks: 2h out, 1h out, then 10 min before tip (inside the 30-min lock).
    times = [tip - timedelta(hours=2), tip - timedelta(hours=1),
             tip - timedelta(minutes=10)]
    it = iter(times)
    fake_clock = lambda: next(it)
    no_sleep = lambda _s: None

    ticks = daemon.serve_forever(
        sports=["nba"], clock=fake_clock, sleep=no_sleep, max_ticks=3,
        out_dir=tmp_path, agg_fn=lambda sport, **kw: _agg(
            kw["now"].isoformat(timespec="seconds"),
            tip.isoformat(timespec="seconds")),
    )

    assert len(ticks) == 3
    # Every tick captured the one game; only the LAST tick is inside the lock window.
    nba_reports = [t["sports"][0] for t in ticks]
    assert all(r["sport"] == "nba" and r["status"] == "ok" for r in nba_reports)
    assert [r["at_lock_games"] for r in nba_reports] == [0, 0, 1]
    # 3 ticks x (2 venues x 2 sides) = 12 rows appended.
    assert sum(r["logged"] for r in nba_reports) == 12

    # The history yields a TRUE close (a quote was captured inside the lock window).
    got = line_store.get_close("G1", base=tmp_path)
    assert got is not None
    closes, is_true_close = got
    assert is_true_close is True
    assert ("moneyline", "home") in closes
    # The chosen close is the latest at-lock tick (captured 10 min before tip).
    assert closes[("moneyline", "home")]["captured_at"].startswith("2026-06-18T22:50")


def test_no_close_tick_is_a_proxy_not_fabricated(tmp_path):
    tip = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
    # Only ticks far from tip -> no at-lock quote -> last-observed PROXY.
    times = [tip - timedelta(hours=3), tip - timedelta(hours=2)]
    it = iter(times)
    daemon.serve_forever(
        sports=["nba"], clock=lambda: next(it), sleep=lambda _s: None,
        max_ticks=2, out_dir=tmp_path,
        agg_fn=lambda sport, **kw: _agg(
            kw["now"].isoformat(timespec="seconds"),
            tip.isoformat(timespec="seconds")),
    )
    got = line_store.get_close("G1", base=tmp_path)
    assert got is not None
    _closes, is_true_close = got
    assert is_true_close is False  # proxy, never fabricated


def test_feed_error_on_one_sport_is_isolated(tmp_path):
    tip = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
    now = tip - timedelta(minutes=10)

    def flaky_agg(sport, **kw):
        if sport == "mlb":
            raise RuntimeError("feed down")
        return _agg(kw["now"].isoformat(timespec="seconds"),
                    tip.isoformat(timespec="seconds"))

    ticks = daemon.serve_forever(
        sports=["nba", "mlb"], clock=lambda: now, sleep=lambda _s: None,
        max_ticks=1, out_dir=tmp_path, agg_fn=flaky_agg)

    nba_rep, mlb_rep = ticks[0]["sports"]
    assert nba_rep["sport"] == "nba" and nba_rep["status"] == "ok"
    assert nba_rep["logged"] == 4  # nba still captured
    assert mlb_rep["sport"] == "mlb"
    assert mlb_rep["status"].startswith("error")  # isolated, did not raise
    # nba's true close is intact despite the mlb feed error.
    got = line_store.get_close("G1", base=tmp_path)
    assert got is not None and got[1] is True


def test_poll_once_unavailable_slate_writes_nothing(tmp_path):
    rep = daemon.poll_once(
        "nba", now=datetime(2026, 6, 18, 20, 0, tzinfo=timezone.utc),
        agg=_agg("2026-06-18T20:00:00+00:00", "2026-06-18T23:00:00+00:00",
                 status="unavailable"),
        out_dir=tmp_path)
    assert rep["status"] == "unavailable"
    assert rep["logged"] == 0


def test_phase_aware_interval_fast_near_tip():
    assert daemon._next_interval(5.0) == daemon.FAST_INTERVAL_SEC
    assert daemon._next_interval(120.0) == daemon.SLOW_INTERVAL_SEC
    assert daemon._next_interval(None) == daemon.SLOW_INTERVAL_SEC
