"""scripts.platformkit.autonomy.heartbeat_reaper -- stale-heartbeat -> restart.

The supervisor restarts a daemon that DIES. It does NOT, on its own, restart a
daemon that is still ALIVE but HUNG -- a wedged loop whose heartbeat has gone
stale keeps reading READY forever. That is the stale-as-green honesty rail
violation called out in reliability-bulletproofing.md (RB-P0-03): a hung loop
must read DEGRADED/RED, never green.

This reaper wires the previously-UNUSED ``ops.circuit_breaker`` into that gap.
For each supervised service it tracks one :class:`CircuitBreaker` keyed by the
service name. On every supervise tick the supervisor feeds the reaper the
service's heartbeat AGE (seconds) and its freshness window:

  * heartbeat fresh  -> ``record_success`` (breaker heals back to CLOSED)
  * heartbeat STALE  -> ``record_failure`` (breaker trips OPEN after threshold)
  * heartbeat ABSENT -> treated as STALE *only if* the service is expected to
    beat (``expects_heartbeat=True``); a NONE-readiness service that legitimately
    writes no heartbeat is never reaped on absence alone.

When a breaker is OPEN the reaper emits a ``restart`` verdict for that service,
plus a DISTINCT status string ``STALE_HUNG`` (never ``READY``) so the status
surface shows the honest degraded state. The breaker's cooldown + HALF_OPEN
trial give a natural rate cap so a flapping/slow-to-recover daemon is not
restart-hammered.

Design: pure (no I/O, no spawning); injectable clock; NEVER raises; stdlib-only;
ASCII-only; <=300 LOC. The reaper DECIDES; the caller (supervisor) ACTS.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ops.circuit_breaker import CircuitBreaker, OPEN

# Distinct honest status strings -- NEVER "READY".
STALE_HUNG = "STALE_HUNG"     # alive but heartbeat stale past its window
HEALTHY = "HEALTHY"           # heartbeat fresh
NO_HEARTBEAT = "NO_HEARTBEAT"  # expected a heartbeat, file absent

# Verdicts the reaper hands back to the supervisor.
RESTART = "restart"
KEEP = "keep"


class HeartbeatReaper:
    """Per-service stale-heartbeat detector backed by circuit breakers.

    Parameters
    ----------
    fail_threshold : int
        Consecutive stale observations before a service's breaker trips OPEN and
        a restart is signalled. >1 absorbs a single late beat (no flap-restart).
    cooldown_sec : float
        Seconds the breaker stays OPEN before a HALF_OPEN probe -- the restart
        rate cap (a relaunched daemon gets this long to start beating again).
    clock : callable() -> float
        Injectable epoch clock (default time.time) for deterministic tests.
    """

    def __init__(
        self,
        *,
        fail_threshold: int = 2,
        cooldown_sec: float = 60.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._fail_threshold = max(1, int(fail_threshold))
        self._cooldown_sec = float(cooldown_sec)
        self._clock = clock
        self._breakers: Dict[str, CircuitBreaker] = {}
        # Last classification per service, for status surfacing.
        self._last_status: Dict[str, str] = {}
        # Services that have beaten at least once -- a heartbeat that APPEARED
        # and then went stale is a hung loop; one that NEVER appeared (a daemon
        # that simply does not emit yet) must NOT be restart-looped on absence.
        self._ever_beat: set = set()

    # ------------------------------------------------------------------ #
    def _breaker(self, name: str) -> CircuitBreaker:
        cb = self._breakers.get(name)
        if cb is None:
            cb = CircuitBreaker(
                name,
                fail_threshold=self._fail_threshold,
                cooldown_sec=self._cooldown_sec,
                clock=self._clock,
            )
            self._breakers[name] = cb
        return cb

    # ------------------------------------------------------------------ #
    def observe(
        self,
        name: str,
        *,
        age_sec: Optional[float],
        fresh_sec: float,
        alive: bool = True,
        expects_heartbeat: bool = True,
    ) -> Dict[str, Any]:
        """Record one heartbeat observation for *name*; return a verdict dict.

        Returns ``{"name", "status", "verdict", "breaker"}`` where ``status`` is
        one of HEALTHY / STALE_HUNG / NO_HEARTBEAT and ``verdict`` is RESTART or
        KEEP. NEVER raises -- a malformed observation degrades to KEEP/HEALTHY so
        the reaper can never itself wedge the supervise tick.
        """
        try:
            cb = self._breaker(name)

            # A dead service is the supervisor's job (restart policy), not ours.
            if not alive:
                cb.record_success()  # reset streak; death handled elsewhere
                return self._verdict(name, HEALTHY, KEEP, cb)

            # A service that legitimately writes no heartbeat is never reaped on
            # absence. We only treat absence as a failure once the service has
            # beaten at least once (a heartbeat that APPEARED then vanished is a
            # hung/crashed loop); perpetual absence (a daemon that never emits)
            # is KEEP -- the supervisor's own dead-proc path owns true crashes.
            if age_sec is None:
                if expects_heartbeat and name in self._ever_beat:
                    cb.record_failure()
                    status = NO_HEARTBEAT
                else:
                    cb.record_success()
                    return self._verdict(name, HEALTHY, KEEP, cb)
            else:
                self._ever_beat.add(name)
                # Negative age (future-stamped / clock skew) is suspect -> treat
                # as not-fresh so a constant-future stamp can't read green forever.
                fresh = 0.0 <= float(age_sec) <= float(fresh_sec)
                if fresh:
                    cb.record_success()
                    return self._verdict(name, HEALTHY, KEEP, cb)
                cb.record_failure()
                status = STALE_HUNG

            verdict = RESTART if cb.status().get("state") == OPEN else KEEP
            return self._verdict(name, status, verdict, cb)
        except Exception:  # noqa: BLE001 -- reaper must never crash the tick
            return {"name": name, "status": HEALTHY, "verdict": KEEP,
                    "breaker": {}}

    def _verdict(self, name: str, status: str, verdict: str,
                 cb: CircuitBreaker) -> Dict[str, Any]:
        self._last_status[name] = status
        return {"name": name, "status": status, "verdict": verdict,
                "breaker": cb.status()}

    # ------------------------------------------------------------------ #
    def note_restarted(self, name: str) -> None:
        """Tell the reaper the supervisor just relaunched *name*.

        Resets the breaker so the freshly-spawned child gets a clean window to
        start beating again (no immediate re-trip from the pre-restart streak).
        """
        try:
            cb = self._breakers.get(name)
            if cb is not None:
                cb.reset()
            self._last_status[name] = HEALTHY
        except Exception:  # noqa: BLE001
            pass

    def status(self) -> List[Dict[str, Any]]:
        """Snapshot every tracked service's last status + breaker state."""
        rows: List[Dict[str, Any]] = []
        for name, cb in self._breakers.items():
            rows.append({
                "name": name,
                "status": self._last_status.get(name, HEALTHY),
                "breaker": cb.status(),
            })
        return rows


__all__ = [
    "HeartbeatReaper",
    "STALE_HUNG",
    "HEALTHY",
    "NO_HEARTBEAT",
    "RESTART",
    "KEEP",
]
