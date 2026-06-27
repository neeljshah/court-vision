"""tests for scripts.platformkit.autonomy.loop_observer -- A6 self-monitor.

liveness != progress: a fresh heartbeat over a frozen cursor is DEGRADED, a dead
heartbeat is DOWN, an honest idle stays OK but names the reason. Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_loop_observer.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy import loop_observer as lo  # noqa: E402
from scripts.platformkit.autonomy import progress_tripwire as trip  # noqa: E402

NOW = 2_000_000.0


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _status(*, last_seen_epoch=None, daemon_status="no_new_games", ts=None,
            svc_name="paper_loop"):
    last_status = {"status": daemon_status}
    if ts is not None:
        last_status["ts"] = ts
    return {
        "services": [
            {"name": svc_name, "live": True, "fresh": "fresh",
             "last_seen": _iso(last_seen_epoch) if last_seen_epoch else None},
        ],
        "loop": {"last_status": last_status},
    }


def test_honest_idle_no_new_games_is_ok_with_reason():
    """A loop with a fresh heartbeat and 'no_new_games' is honest IDLE -> ok."""
    st = _status(last_seen_epoch=NOW - 10, daemon_status="no_new_games")
    out = lo.observe(now=NOW, status=st)
    assert out["status"] == lo.OK
    assert out["loop_status"] == trip.IDLE
    assert out["idle"] is True
    assert out["idle_reason"] is not None


def test_dead_heartbeat_is_down_not_green():
    """A stale/dead loop heartbeat must be DOWN -- never read healthy."""
    st = _status(last_seen_epoch=NOW - 99999, daemon_status="no_new_games")
    out = lo.observe(now=NOW, status=st, hb_fresh_sec=300)
    assert out["status"] == lo.DOWN
    assert out["loop_status"] == trip.HEARTBEAT_STALE


def test_missing_loop_service_cannot_prove_progress_is_degraded():
    """No loop service present -> heartbeat unknown -> at least DEGRADED, not ok."""
    st = {"services": [{"name": "unrelated", "last_seen": _iso(NOW)}],
          "loop": {"last_status": {"status": "cycle_done", "ts": NOW - 5}}}
    out = lo.observe(now=NOW, status=st)
    assert out["status"] != lo.OK
    assert out["loop_status"] in (trip.HEARTBEAT_STALE, trip.UNKNOWN)


def test_fresh_heartbeat_advancing_cursor_is_ok():
    st = _status(last_seen_epoch=NOW - 5, daemon_status="cycle_done", ts=NOW - 20)
    out = lo.observe(now=NOW, status=st, stall_sec=1800)
    assert out["status"] == lo.OK
    assert out["loop_status"] == trip.HEALTHY


def test_fresh_heartbeat_frozen_cursor_is_degraded_not_green():
    """The decisive case: beating fresh, cursor frozen past stall -> DEGRADED."""
    st = _status(last_seen_epoch=NOW - 5, daemon_status="cycle_done", ts=NOW - 9000)
    out = lo.observe(now=NOW, status=st, hb_fresh_sec=300, stall_sec=1800)
    assert out["status"] == lo.DEGRADED
    assert out["loop_status"] == trip.STALLED_CURSOR


def test_observe_uses_compose_fn_when_no_status_given():
    sentinel = {"services": [{"name": "paper_loop", "live": True,
                              "fresh": "fresh", "last_seen": _iso(NOW - 5)}],
                "loop": {"last_status": {"status": "no_new_games"}}}
    out = lo.observe(now=NOW, compose_fn=lambda **kw: sentinel)
    assert out["status"] == lo.OK
    assert out["idle"] is True


def test_observe_never_raises_on_garbage_status():
    out = lo.observe(now=NOW, status={"services": "not-a-list"})
    assert out["status"] in (lo.OK, lo.DEGRADED, lo.DOWN)
    # garbage must never read green-when-it-cannot-prove-progress
    assert out["status"] != lo.OK or out["loop_status"] == trip.IDLE


def test_severity_map_has_no_accidental_green():
    # Only HEALTHY and honest IDLE map to OK; stall/hung/unknown never do.
    assert lo._TRIP_TO_SEVERITY[trip.STALLED_CURSOR] == lo.DEGRADED
    assert lo._TRIP_TO_SEVERITY[trip.HEARTBEAT_STALE] == lo.DOWN
    assert lo._TRIP_TO_SEVERITY[trip.UNKNOWN] == lo.DEGRADED
