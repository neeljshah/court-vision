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

Stdlib-only (threading). ASCII-only. <=60 LOC.

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


__all__ = ["score_with_timeout", "DEFAULT_SCORE_TIMEOUT_SEC"]
