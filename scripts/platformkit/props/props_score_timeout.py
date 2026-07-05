"""scripts.platformkit.props.props_score_timeout -- bounded-timeout scoring call.

2026-07-04 LANE 6 fix: a genuinely HUNG scoring call (e.g. a feed request inside
build_prop_cards with no bounded timeout of its own) previously blocked
props_pred_tick_runner.tick() forever -- the background beater kept the
LIVENESS heartbeat fresh (so the supervisor's heartbeat-fresh probe stayed
READY) while props_snapshot.json itself went stale past the 660s
freshness_sla threshold with no way to recover (observed post-restart
2026-07-04: first tick still running 9+ minutes in, heartbeat content stuck at
tick-start time, snapshot untouched since BEFORE the restart).

Running the scoring call in its own daemon thread with a join timeout means a
hang can no longer starve the snapshot write: the caller gets (None, True) on
timeout instead of blocking, honestly falls through to UNAVAILABLE/synth, and
the NEXT tick retries fresh. The worker thread itself is left to finish/die on
its own (daemon=True) -- we only stop WAITING on it past timeout_sec, we never
kill it (Python threads cannot be force-killed safely).

2026-07-05 SLA-FREEZE fix: the promise above ("honestly falls through to
UNAVAILABLE/synth") was NOT actually kept -- props_pred_tick_runner.tick()'s
post-timeout anti-flicker synth fallback called the SAME feed/parquet-touching
code path that had just timed out, with NO bound of its own. Under sustained
live-slate load the fallback could ALSO run long, so tick() never reached its
atomic write and props_snapshot.json's mtime froze past the 660s SLA even
though this module's own primary timeout was firing every cycle (see
logs/m13_props_pred_tick.err: "score timed out after 240s" on repeat).
score_with_timeout_and_fallback() closes that gap: the fallback call gets its
OWN bounded daemon-thread join (never the unbounded direct call), so this
function always returns within timeout_sec + fallback_timeout_sec and the
caller can always reach its write.

Stdlib-only (threading). ASCII-only. <=120 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/props/test_props_score_timeout.py -q
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple

# Comfortably above one full scoring pass under normal load, comfortably below
# the 660s m13_props_pred_tick freshness_sla threshold so a timed-out tick
# still writes an honest (empty/synth) snapshot BEFORE the SLA would flag it.
DEFAULT_SCORE_TIMEOUT_SEC = 240.0

# Bound on the anti-flicker fallback call ITSELF (a cheap same-engine recompute
# under normal conditions; short because it only runs after the primary score
# already burned timeout_sec -- the tick must still finish well inside the SLA).
DEFAULT_FALLBACK_TIMEOUT_SEC = 45.0


def score_with_timeout(
        score_call: Callable[[], Any], *,
        timeout_sec: float = DEFAULT_SCORE_TIMEOUT_SEC,
) -> Tuple[Optional[Any], bool]:
    """Run *score_call* in its own daemon thread; return (result, timed_out).

    result is None when it timed out (timed_out=True). If score_call raises
    within timeout_sec, the exception is re-raised here (same as calling it
    directly) so existing try/except callers are unaffected on the raise path
    -- only the HANG path changes behavior."""
    box: Dict[str, Any] = {}

    def _run() -> None:
        try:
            box["result"] = score_call()
        except Exception as exc:  # noqa: BLE001 -- surfaced via box, never crashes thread
            box["error"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        return None, True
    if "error" in box:
        raise box["error"]
    return box.get("result"), False


def score_with_timeout_and_fallback(
        score_call: Callable[[], Any],
        fallback_call: Callable[[], Any], *,
        needs_fallback: Callable[[Any], bool] = lambda result: not result,
        timeout_sec: float = DEFAULT_SCORE_TIMEOUT_SEC,
        fallback_timeout_sec: float = DEFAULT_FALLBACK_TIMEOUT_SEC,
) -> Tuple[Optional[Any], str]:
    """Run *score_call* bounded; if it times out OR *needs_fallback(result)* is
    True (default: falsy/empty result -- the same "transient empty" trigger the
    anti-flicker guard has always used), run *fallback_call* ALSO bounded (never
    the raw unbounded call -- the exact gap that froze props_snapshot.json's
    mtime, see module docstring). Returns (result, path) where path is one of
    "primary" (score_call finished in time and needed no fallback), "fallback"
    (fallback_call finished in time), or "timeout" (both timed out / fallback
    also exhausted its budget) -- the caller uses *path* to label the written
    envelope honestly instead of silently degrading. result is None on
    "timeout"; never raises (a raise inside score_call still propagates per
    score_with_timeout's contract, a raise inside fallback_call is swallowed to
    "timeout" since a fallback that itself errors is no better than one that
    hangs)."""
    result, timed_out = score_with_timeout(score_call, timeout_sec=timeout_sec)
    if not timed_out and not needs_fallback(result):
        return result, "primary"
    try:
        fb_result, fb_timed_out = score_with_timeout(
            fallback_call, timeout_sec=fallback_timeout_sec)
    except Exception:  # noqa: BLE001 -- a raising fallback is no better than a hung one
        return None, "timeout"
    if fb_timed_out:
        return None, "timeout"
    return fb_result, "fallback"


__all__ = ["score_with_timeout", "score_with_timeout_and_fallback",
           "DEFAULT_SCORE_TIMEOUT_SEC", "DEFAULT_FALLBACK_TIMEOUT_SEC"]
