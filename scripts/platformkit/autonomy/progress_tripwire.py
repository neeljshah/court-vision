"""scripts.platformkit.autonomy.progress_tripwire -- liveness != progress.

A fresh heartbeat proves a loop is BREATHING; it does NOT prove the loop is
making PROGRESS. A daemon can dutifully beat its heartbeat at the top of every
iteration while its real work cursor (last settled game folded, last candidate
graded, last snapshot appended) is frozen -- a busy-wait that is alive but
accomplishing nothing. The heartbeat-staleness reaper would read that loop as
HEALTHY. That is a stale-as-green crack one level deeper than a dead heartbeat.

This tripwire closes it. The loop reports two clocks:
  * heartbeat_at -- when it last beat (proves liveness).
  * cursor_at    -- when its work cursor last ADVANCED (proves progress).

``classify`` compares the two against now. A loop that is beating fresh but
whose cursor has not advanced past ``stall_sec`` is flagged ``STALLED_CURSOR``
-- distinct from both HEALTHY and the heartbeat-dead STALE_HUNG. ``cursor_age``
is always exposed so an operator (and the status surface) can SEE the gap
between liveness and progress, never infer progress from liveness.

Honest IDLE: a loop that legitimately has nothing to do (offseason, empty
slate) is NOT stalled. The caller passes ``idle=True`` (it polled and there was
genuinely no work) and the tripwire returns ``IDLE`` -- an honest "nothing to
advance", never a fabricated cursor bump and never a false STALLED_CURSOR.

Pure; injectable clock; NEVER raises; stdlib-only; ASCII-only; <=300 LOC.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Distinct statuses -- none of these is ever "READY"/"HEALTHY-green" by accident.
HEALTHY = "HEALTHY"               # beating fresh AND cursor advancing
STALLED_CURSOR = "STALLED_CURSOR"  # beating fresh BUT cursor frozen past stall_sec
HEARTBEAT_STALE = "HEARTBEAT_STALE"  # heartbeat itself stale (dead/hung)
IDLE = "IDLE"                     # honestly no work to advance (not a stall)
UNKNOWN = "UNKNOWN"              # missing timestamps -> cannot assert progress


def classify(
    *,
    heartbeat_at: Optional[float],
    cursor_at: Optional[float],
    now: Optional[float] = None,
    hb_fresh_sec: float = 300.0,
    stall_sec: float = 1800.0,
    idle: bool = False,
) -> Dict[str, Any]:
    """Classify a loop's liveness-vs-progress state. NEVER raises.

    Parameters
    ----------
    heartbeat_at : epoch the loop last beat (None -> unknown).
    cursor_at    : epoch the work cursor last ADVANCED (None -> unknown).
    now          : epoch now (default time.time).
    hb_fresh_sec : heartbeat freshness window.
    stall_sec    : max time the cursor may stand still before STALLED_CURSOR.
    idle         : caller polled and found genuinely no work -> honest IDLE.

    Returns ``{"status", "heartbeat_age", "cursor_age", "detail"}`` -- cursor_age
    is ALWAYS present (or None) so progress is observable separate from liveness.
    """
    try:
        t = float(now) if now is not None else time.time()
        hb_age = _age(t, heartbeat_at)
        cur_age = _age(t, cursor_at)

        # Heartbeat itself stale/dead/unknown -> liveness fails first; defer the
        # progress question (a dead loop's frozen cursor is not "stalled work",
        # it is a dead loop -- the reaper owns that).
        if hb_age is None or hb_age > float(hb_fresh_sec):
            return _row(HEARTBEAT_STALE if hb_age is not None else UNKNOWN,
                        hb_age, cur_age,
                        {"reason": "heartbeat_not_fresh",
                         "hb_fresh_sec": hb_fresh_sec})

        # Heartbeat is fresh from here on -> the loop IS breathing.
        if idle:
            # Honest "nothing to do": fresh beat, no work to advance.
            return _row(IDLE, hb_age, cur_age, {"reason": "no_work_available"})

        if cur_age is None:
            # Beating but we cannot prove the cursor ever advanced -> UNKNOWN,
            # NOT silently HEALTHY (do not infer progress from liveness).
            return _row(UNKNOWN, hb_age, cur_age,
                        {"reason": "cursor_age_unknown"})

        if cur_age > float(stall_sec):
            # The decisive case: fresh heartbeat, frozen cursor.
            return _row(STALLED_CURSOR, hb_age, cur_age,
                        {"reason": "cursor_frozen", "stall_sec": stall_sec})

        return _row(HEALTHY, hb_age, cur_age, {"reason": "progressing"})
    except Exception:  # noqa: BLE001 -- tripwire must never crash the loop
        return _row(UNKNOWN, None, None, {"reason": "classify_raised"})


def _age(now: float, stamp: Optional[float]) -> Optional[float]:
    """Non-negative age of *stamp*; None if missing; clamps future stamps to 0.

    A future-stamped clock (skew / a bad constant-future writer) clamps to 0 so
    it cannot read 'fresh forever' on a negative age -- consistent with the
    health-probe future-stamp hardening.
    """
    if not isinstance(stamp, (int, float)):
        return None
    age = float(now) - float(stamp)
    return age if age > 0.0 else 0.0


def _row(status: str, hb_age: Optional[float], cur_age: Optional[float],
         detail: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": status,
        "heartbeat_age": round(hb_age, 1) if hb_age is not None else None,
        "cursor_age": round(cur_age, 1) if cur_age is not None else None,
        "detail": detail,
    }


__all__ = [
    "classify",
    "HEALTHY",
    "STALLED_CURSOR",
    "HEARTBEAT_STALE",
    "IDLE",
    "UNKNOWN",
]
