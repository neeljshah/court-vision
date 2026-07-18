"""Per-file test for LIVE-EDGE D1 live_session loop (fixture ticks, no live
timing dependency).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_live_session.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.live_edge.bus import FileCursor, append_events
from scripts.platformkit.live_edge.shadow import live_session as ls
from scripts.platformkit.live_edge.shadow import shadow_ledger as sl


def _odds_bus_row(ts_knowable="2026-07-14T19:55:53+00:00", devig=0.519):
    return {
        "source": "odds:soccer_intl",
        "ts_captured": ts_knowable,
        "ts_knowable": ts_knowable,
        "payload": {
            "sport": "soccer_intl", "game_id": "KXWCGAME-26JUL15ENGARG",
            "home": "Reg Time: England", "away": "Reg Time: Argentina",
            "market_type": "total", "side": "under", "line": 2.25, "odds": 1.826,
            "book": "pinnacle", "devigged_prob": devig, "captured_at": ts_knowable,
            "commence_time": None,
        },
    }


def test_process_odds_row_builds_shadow_row_honest_noop():
    """Soccer has no ACTIVE mechanism -> conditioned == unconditioned, mechanism_applied None."""
    bus_row = _odds_bus_row()
    result = ls.process_odds_row(bus_row, wall_ts="2026-07-14T19:56:00+00:00")
    assert result is not None
    row = result["row"]
    assert row["market"] == "pregame.total"
    assert row["unconditioned_pred"] == pytest.approx(0.519)
    assert row["conditioned_pred"] == pytest.approx(0.519)
    assert row["mechanism_applied"] is None
    assert row["edge_claimed"] is False
    assert result["latency_sec"] == pytest.approx(7.0)  # 19:56:00 - 19:55:53


def test_process_odds_row_skips_non_devig_payload():
    bus_row = {"source": "odds:soccer", "ts_knowable": "2026-07-14T19:55:00+00:00",
               "payload": {"sport": "soccer", "game_id": "x"}}
    assert ls.process_odds_row(bus_row, wall_ts="2026-07-14T19:55:01+00:00") is None


def test_sec_delta_handles_bad_timestamps():
    assert ls._sec_delta("not-a-ts", "2026-07-14T19:55:01+00:00") is None
    assert ls._sec_delta("2026-07-14T19:55:00+00:00", "2026-07-14T19:55:10+00:00") == pytest.approx(10.0)


def test_percentile_empty_and_basic():
    assert ls._percentile([], 50) is None
    assert ls._percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(3.0)  # nearest-rank, round(1.5)=2 -> idx 2


def test_run_iteration_reads_fresh_bus_rows_and_appends_shadow(tmp_path, monkeypatch):
    """Fixture: seed the bus with one odds tick directly (bypassing bus_ingest's
    file-tailing, which is imported/owned elsewhere), stub ingest_all to a no-op,
    and prove run_iteration reads it via the offset cursor and writes one shadow row."""
    bus_dir = tmp_path / "bus"
    shadow_dir = tmp_path / "shadow"
    cursor_dir = tmp_path / "cursors"
    date = "2026-07-14"
    append_events([_odds_bus_row()], bus_dir=bus_dir)

    monkeypatch.setattr(ls.bus_ingest, "ingest_all", lambda cursor=None, bus_dir=None: {"stub": 0})
    monkeypatch.setattr(ls, "read_events", lambda d, offset=0, asof=None: _read_from(bus_dir, d, offset))

    ingest_cursor = FileCursor("test_ingest", cursor_dir=cursor_dir)
    bus_cursor = FileCursor("test_bus_offset", cursor_dir=cursor_dir)
    result = ls.run_iteration(ingest_cursor=ingest_cursor, bus_cursor=bus_cursor,
                               date=date, shadow_dir=shadow_dir)

    assert result["n_bus_rows_seen"] == 1
    assert result["n_shadow_rows"] == 1
    out_path = sl.shadow_path(date, shadow_dir=shadow_dir)
    assert out_path.is_file()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["market"] == "pregame.total"

    # second call with the same underlying bus file must see 0 new rows (offset advanced)
    result2 = ls.run_iteration(ingest_cursor=ingest_cursor, bus_cursor=bus_cursor,
                                date=date, shadow_dir=shadow_dir)
    assert result2["n_bus_rows_seen"] == 0
    assert result2["n_shadow_rows"] == 0


def _read_from(bus_dir, date, offset):
    from scripts.platformkit.live_edge.bus import read_events as real_read_events
    return real_read_events(date, offset=offset, bus_dir=bus_dir)


def test_run_live_session_stops_on_staleness(tmp_path, monkeypatch):
    """No new bus rows ever -> staleness_stop_sec should end the loop well
    before max_iterations, without any real sleeping (sleep_fn stubbed)."""
    monkeypatch.setattr(ls.bus_ingest, "ingest_all", lambda cursor=None, bus_dir=None: {"stub": 0})
    monkeypatch.setattr(ls, "read_events", lambda d, offset=0, asof=None: ([], offset))

    fake_clock = {"t": 0.0}
    monkeypatch.setattr(ls.time, "monotonic", lambda: fake_clock["t"])

    def fake_sleep(_sec):
        fake_clock["t"] += 1000.0  # jump well past any staleness_stop_sec

    result = ls.run_live_session(max_iterations=50, sleep_sec=1.0, staleness_stop_sec=5.0,
                                  shadow_dir=tmp_path, sleep_fn=fake_sleep)
    assert result["iterations_run"] < 50
    assert result["total_shadow_rows"] == 0
    assert result["latency_p50"] is None
