"""ops.circuit_breaker -- CLOSED -> OPEN -> HALF_OPEN state machine for the supervisor.

A CircuitBreaker guards a single named resource (feed, service, or upstream call).
It trips OPEN after N consecutive failures, then enters HALF_OPEN after a cooldown
period to probe whether the resource has recovered.  One trial is allowed through in
HALF_OPEN; a success closes the breaker, a failure re-opens it and resets the timer.

Design constraints:
  - Pure: no I/O, no network, no filesystem.
  - Injectable clock (now callable or datetime) so tests run deterministically.
  - NEVER raises -- the breaker must not itself crash the caller.
  - Thread-safety: not guaranteed (single-threaded supervisor); add a Lock if needed.

States
------
  CLOSED    -- normal operation; failures accumulate
  OPEN      -- tripped; allow() returns False; no calls pass through
  HALF_OPEN -- cooldown elapsed; ONE trial allowed; result determines next state

Public API
----------
CircuitBreaker(name, fail_threshold=3, cooldown_sec=60.0, clock=None)
    name           : str -- identifier used in __repr__ and status dict
    fail_threshold : int -- consecutive failures needed to trip OPEN
    cooldown_sec   : float -- seconds in OPEN before entering HALF_OPEN
    clock          : optional callable() -> float (epoch seconds); default time.time

.record_success() -> None  -- record a success; resets failure streak; HALF_OPEN -> CLOSED
.record_failure() -> None  -- record a failure; may trip to OPEN or re-open from HALF_OPEN
.allow() -> bool           -- True iff state is CLOSED or (HALF_OPEN and trial slot open)
.status() -> dict          -- snapshot of the breaker's state for status.json / logging

INVARIANTS: <=300 LOC; ASCII; never raises; stdlib only.
"""
from __future__ import annotations

import time as _time_module
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------
CLOSED: str    = "CLOSED"
OPEN: str      = "OPEN"
HALF_OPEN: str = "HALF_OPEN"

_VALID_STATES = {CLOSED, OPEN, HALF_OPEN}


class CircuitBreaker:
    """Three-state circuit breaker keyed by *name*.

    Usage::

        cb = CircuitBreaker("pinnacle", fail_threshold=3, cooldown_sec=30.0)
        if cb.allow():
            try:
                result = fetch(...)
                cb.record_success()
            except Exception:
                cb.record_failure()
        else:
            use_cache_or_skip()
    """

    def __init__(
        self,
        name: str,
        *,
        fail_threshold: int = 3,
        cooldown_sec: float = 60.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.name = name
        self._fail_threshold = max(1, int(fail_threshold))
        self._cooldown_sec = float(cooldown_sec)
        self._clock: Callable[[], float] = clock if clock is not None else _time_module.time

        # Mutable state
        self._state: str = CLOSED
        self._failure_count: int = 0
        self._opened_at: Optional[float] = None   # epoch when OPEN was entered
        self._half_open_trial_allowed: bool = False  # True = one trial slot granted

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allow(self) -> bool:
        """Return True if a call should be allowed through.

        CLOSED   -> True  (normal operation)
        OPEN     -> False, unless cooldown has elapsed (transition to HALF_OPEN + True)
        HALF_OPEN -> True iff the trial slot has not yet been consumed this cycle
        """
        try:
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                return self._check_cooldown()
            if self._state == HALF_OPEN:
                return self._half_open_trial_allowed
            return False  # unknown state -- safe default
        except Exception:  # noqa: BLE001 -- breaker must not crash caller
            return False

    def record_success(self) -> None:
        """Record a successful call.

        CLOSED   -> resets failure streak (stays CLOSED)
        HALF_OPEN -> transition to CLOSED (recovery confirmed)
        OPEN     -> no-op (caller should only succeed after allow() returned True)
        """
        try:
            self._failure_count = 0
            if self._state in (HALF_OPEN, OPEN):
                self._transition(CLOSED)
        except Exception:  # noqa: BLE001
            pass

    def record_failure(self) -> None:
        """Record a failed call.

        CLOSED   -> increments streak; trips to OPEN at threshold
        HALF_OPEN -> re-opens (recovery failed); resets cooldown timer
        OPEN     -> increments count; cooldown timer unchanged
        """
        try:
            self._failure_count += 1
            if self._state == HALF_OPEN:
                # Trial failed -- go back to OPEN and restart cooldown.
                self._transition(OPEN)
            elif self._state == CLOSED:
                if self._failure_count >= self._fail_threshold:
                    self._transition(OPEN)
            # OPEN: just accumulate the count, timer unchanged
        except Exception:  # noqa: BLE001
            pass

    def status(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of breaker state."""
        try:
            return {
                "name": self.name,
                "state": self._state,
                "failure_count": self._failure_count,
                "fail_threshold": self._fail_threshold,
                "cooldown_sec": self._cooldown_sec,
                "opened_at": self._opened_at,
                "half_open_trial_allowed": self._half_open_trial_allowed,
            }
        except Exception:  # noqa: BLE001
            return {"name": self.name, "state": "error"}

    def reset(self) -> None:
        """Force the breaker back to CLOSED (for testing / manual recovery)."""
        try:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_trial_allowed = False
            self._state = CLOSED
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _now(self) -> float:
        """Return current epoch seconds; falls back to 0.0 on error."""
        try:
            return float(self._clock())
        except Exception:  # noqa: BLE001
            return 0.0

    def _transition(self, new_state: str) -> None:
        """Update state and bookkeeping; silently ignores unknown states."""
        if new_state not in _VALID_STATES:
            return
        self._state = new_state
        if new_state == OPEN:
            self._opened_at = self._now()
            self._half_open_trial_allowed = False
        elif new_state == HALF_OPEN:
            self._half_open_trial_allowed = True  # grant one trial
        elif new_state == CLOSED:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_trial_allowed = False

    def _check_cooldown(self) -> bool:
        """From OPEN: if cooldown elapsed transition to HALF_OPEN and allow trial."""
        elapsed = self._now() - (self._opened_at or 0.0)
        if elapsed >= self._cooldown_sec:
            self._transition(HALF_OPEN)
            return True
        return False

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CircuitBreaker({self.name!r}, state={self._state}, "
            f"failures={self._failure_count}/{self._fail_threshold})"
        )


__all__ = [
    "CLOSED",
    "OPEN",
    "HALF_OPEN",
    "CircuitBreaker",
]
