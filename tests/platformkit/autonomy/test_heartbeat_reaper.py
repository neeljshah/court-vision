"""tests for scripts.platformkit.autonomy.heartbeat_reaper -- stale -> restart.

A hung loop (alive, heartbeat stale) must be flagged RESTART and NEVER read
HEALTHY/green. Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_heartbeat_reaper.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy.heartbeat_reaper import (  # noqa: E402
    HEALTHY,
    KEEP,
    NO_HEARTBEAT,
    RESTART,
    STALE_HUNG,
    HeartbeatReaper,
)


class _Clk:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def adv(self, dt):
        self.t += dt


def test_fresh_heartbeat_is_healthy_keep():
    r = HeartbeatReaper(fail_threshold=2, cooldown_sec=60.0, clock=_Clk())
    v = r.observe("m1_paper", age_sec=10.0, fresh_sec=600.0)
    assert v["status"] == HEALTHY
    assert v["verdict"] == KEEP


def test_stale_heartbeat_trips_to_restart_after_threshold():
    """A sustained-stale heartbeat (alive but hung) must yield RESTART, not green."""
    clk = _Clk()
    r = HeartbeatReaper(fail_threshold=2, cooldown_sec=60.0, clock=clk)
    # First stale obs: streak=1, breaker still CLOSED -> KEEP (absorb one).
    v1 = r.observe("m1_paper", age_sec=5000.0, fresh_sec=600.0)
    assert v1["status"] == STALE_HUNG
    assert v1["verdict"] == KEEP
    # Second consecutive stale obs trips the breaker OPEN -> RESTART.
    v2 = r.observe("m1_paper", age_sec=5000.0, fresh_sec=600.0)
    assert v2["status"] == STALE_HUNG
    assert v2["verdict"] == RESTART
    # The hung loop NEVER reads HEALTHY while stale.
    assert v2["status"] != HEALTHY


def test_recovery_heals_breaker_back_to_keep():
    clk = _Clk()
    r = HeartbeatReaper(fail_threshold=2, cooldown_sec=30.0, clock=clk)
    r.observe("d", age_sec=5000.0, fresh_sec=600.0)
    v = r.observe("d", age_sec=5000.0, fresh_sec=600.0)
    assert v["verdict"] == RESTART
    r.note_restarted("d")
    # After restart + a fresh beat, the service is HEALTHY/KEEP again.
    v3 = r.observe("d", age_sec=12.0, fresh_sec=600.0)
    assert v3["status"] == HEALTHY
    assert v3["verdict"] == KEEP


def test_future_stamp_is_not_fresh_forever():
    """A negative age (constant-future stamp) must NOT read fresh forever."""
    r = HeartbeatReaper(fail_threshold=1, cooldown_sec=60.0, clock=_Clk())
    v = r.observe("skewed", age_sec=-9999.0, fresh_sec=600.0)
    assert v["status"] == STALE_HUNG
    assert v["verdict"] == RESTART


def test_never_emitted_heartbeat_is_kept_not_restart_looped():
    """A daemon that has NEVER beaten is KEEP on absence (no false restart)."""
    r = HeartbeatReaper(fail_threshold=1, cooldown_sec=60.0, clock=_Clk())
    for _ in range(5):
        v = r.observe("never", age_sec=None, fresh_sec=600.0,
                      expects_heartbeat=True)
    assert v["status"] == HEALTHY
    assert v["verdict"] == KEEP


def test_heartbeat_that_appeared_then_vanished_is_restart():
    """Beat once, then file vanishes -> NO_HEARTBEAT -> RESTART (hung/crashed)."""
    r = HeartbeatReaper(fail_threshold=1, cooldown_sec=60.0, clock=_Clk())
    r.observe("vanish", age_sec=5.0, fresh_sec=600.0)        # appeared
    v = r.observe("vanish", age_sec=None, fresh_sec=600.0)   # vanished
    assert v["status"] == NO_HEARTBEAT
    assert v["verdict"] == RESTART


def test_dead_service_is_not_our_job():
    """A dead (not alive) service is the supervisor restart policy's job -> KEEP."""
    r = HeartbeatReaper(fail_threshold=1, cooldown_sec=60.0, clock=_Clk())
    v = r.observe("dead", age_sec=None, fresh_sec=600.0, alive=False)
    assert v["verdict"] == KEEP


def test_observe_never_raises_on_garbage():
    r = HeartbeatReaper(clock=_Clk())
    v = r.observe("g", age_sec="not-a-number", fresh_sec=600.0)  # type: ignore[arg-type]
    assert v["verdict"] == KEEP
