"""Per-file test for scripts.platformkit.props.props_score_timeout.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/props/test_props_score_timeout.py -q
"""
from __future__ import annotations

import threading
import time

import pytest

from scripts.platformkit.props import props_score_timeout as pst


def test_fast_call_returns_result_not_timed_out():
    result, timed_out = pst.score_with_timeout(lambda: [1, 2, 3], timeout_sec=1.0)
    assert timed_out is False
    assert result == [1, 2, 3]


def test_slow_call_past_timeout_reports_timed_out():
    def _slow():
        time.sleep(2.0)
        return "late"
    result, timed_out = pst.score_with_timeout(_slow, timeout_sec=0.1)
    assert timed_out is True
    assert result is None


def test_raising_call_reraises_when_it_returns_in_time():
    def _boom():
        raise RuntimeError("feed exploded")
    with pytest.raises(RuntimeError, match="feed exploded"):
        pst.score_with_timeout(_boom, timeout_sec=1.0)


def test_hung_call_thread_is_daemon_and_caller_returns_promptly():
    # The caller must get control back at ~timeout_sec even though the worker
    # thread itself keeps running (we never force-kill it) -- this is the
    # exact property that prevents a hung feed call from starving the tick.
    started = threading.Event()

    def _hang():
        started.set()
        time.sleep(5.0)
        return "unreachable in the test's timeframe"

    t0 = time.monotonic()
    result, timed_out = pst.score_with_timeout(_hang, timeout_sec=0.2)
    elapsed = time.monotonic() - t0
    assert started.is_set()
    assert timed_out is True
    assert result is None
    assert elapsed < 1.0  # returned promptly, did not wait for the full 5s hang


def test_default_timeout_constant_is_bounded_below_props_sla():
    # m13_props_pred_tick's freshness_sla threshold is 660s (see freshness_sla.py);
    # the default score timeout must stay comfortably below it so a timed-out
    # tick still writes BEFORE the SLA would flag it RED.
    assert 0.0 < pst.DEFAULT_SCORE_TIMEOUT_SEC < 660.0
