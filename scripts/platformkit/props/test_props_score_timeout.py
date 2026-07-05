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


# ---------------------------------------------------------------------------
# score_with_timeout_and_fallback -- 2026-07-05 SLA-freeze fix: the fallback
# call must ALSO be bounded, or a slow fallback re-creates the exact freeze
# this module exists to prevent (see module docstring).
# ---------------------------------------------------------------------------

def test_primary_success_never_calls_fallback():
    calls = []
    result, path = pst.score_with_timeout_and_fallback(
        lambda: "fast result", lambda: calls.append("fallback ran"),
        timeout_sec=1.0, fallback_timeout_sec=1.0)
    assert result == "fast result"
    assert path == "primary"
    assert calls == []  # fallback never invoked when primary succeeds


def test_primary_timeout_then_fast_fallback_reports_fallback_path():
    def _hang():
        time.sleep(5.0)
        return "unreachable"
    result, path = pst.score_with_timeout_and_fallback(
        _hang, lambda: "fallback result",
        timeout_sec=0.1, fallback_timeout_sec=1.0)
    assert result == "fallback result"
    assert path == "fallback"


def test_both_primary_and_fallback_hang_reports_timeout_not_a_freeze():
    # THE EXACT REGRESSION: an unbounded fallback that also hangs previously
    # meant the caller (tick()) never got control back, so props_snapshot.json's
    # write was never reached. This must return promptly with path="timeout".
    def _hang():
        time.sleep(5.0)
        return "unreachable"
    t0 = time.monotonic()
    result, path = pst.score_with_timeout_and_fallback(
        _hang, _hang, timeout_sec=0.1, fallback_timeout_sec=0.1)
    elapsed = time.monotonic() - t0
    assert result is None
    assert path == "timeout"
    assert elapsed < 2.0  # returned promptly; did not wait for either 5s hang


def test_fallback_raising_reports_timeout_not_propagated():
    # A fallback that errors is no better than one that hangs -- swallow to
    # "timeout" so the caller still gets an honest degraded result, never a raise.
    def _hang():
        time.sleep(5.0)
    def _boom():
        raise RuntimeError("fallback exploded")
    result, path = pst.score_with_timeout_and_fallback(
        _hang, _boom, timeout_sec=0.1, fallback_timeout_sec=1.0)
    assert result is None
    assert path == "timeout"


def test_primary_raising_still_propagates_through_fallback_wrapper():
    # A raise (not a hang) within timeout_sec must still surface to the caller,
    # matching score_with_timeout's existing raise contract -- fallback wrapping
    # must not swallow a genuine primary exception.
    def _boom():
        raise RuntimeError("primary exploded")
    with pytest.raises(RuntimeError, match="primary exploded"):
        pst.score_with_timeout_and_fallback(
            _boom, lambda: "fallback", timeout_sec=1.0, fallback_timeout_sec=1.0)


def test_default_fallback_timeout_is_short_and_bounded():
    # The fallback runs AFTER the primary already burned its full timeout, so
    # it must be short enough that primary+fallback together still finish well
    # inside the 660s freshness_sla threshold.
    assert 0.0 < pst.DEFAULT_FALLBACK_TIMEOUT_SEC < 120.0
    assert (pst.DEFAULT_SCORE_TIMEOUT_SEC + pst.DEFAULT_FALLBACK_TIMEOUT_SEC) < 660.0
