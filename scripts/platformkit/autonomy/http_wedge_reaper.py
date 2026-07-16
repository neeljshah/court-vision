"""scripts.platformkit.autonomy.http_wedge_reaper -- kill-the-wedge for
HTTP-readiness ProcSpecs (the gap heartbeat_reaper does NOT cover).

THE GAP
-------
heartbeat_reaper.py restarts an ALIVE-but-HUNG proc only for HEARTBEAT-readiness
services (a stale on-disk heartbeat file). An HTTP-readiness service (m1_api_paper
:8099 today) has NO heartbeat file -- its readiness probe is "GET /health == 200".
When its event loop wedges (blocked, CPU spinning) the port stays LISTENING (the
OS socket backlog is still open) but every HTTP probe times out. heartbeat_reaper
never sees this: no heartbeat file means "not expected to beat" -> KEEP forever.
Documented incident: :8099 wedged ~2.8h with nothing killing it.

DETECTION RULE (PINNED by the charter -- do not loosen without re-ratifying)
-----------------------------------------------------------------------
A proc is WEDGED only when BOTH hold simultaneously:
  (a) N >= 3 CONSECUTIVE HTTP probe timeouts (each > 10s) against its port
      WHILE the port is still LISTENING (a closed port is a crash, not a wedge --
      that is the supervisor's normal dead-proc path, not ours).
  (b) process CPU > 50% SUSTAINED for > 2 minutes (a wedge that is quietly idle,
      e.g. blocked on I/O with low CPU, is NOT killed by this rule -- conservative
      by design; false-negatives are safer than false-positive kills of a slow
      but legitimately-idle process).

Action on WEDGED: kill THAT PID ONLY (never any other proc); the supervisor's
normal restart/backoff path relaunches it. This module NEVER spawns/restarts --
it only DECIDES and (via the injected killer) kills.

2026-07-15 AMENDMENT (bounded dead-time ceiling, docs/research/execution-quality/
live_coherence_audit_2026-07-15.md): the AND-gate above kept a real, low-CPU
(I/O-blocked) :8099 wedge alive for 65 ticks (5.5min+ confirmed dead, prior
episode 2.8h) -- CPU never crossed 50% and the CPU probe read null. Per the
orchestrator/user's explicit "no lag, keep everything live" directive, an
INDEPENDENT ceiling is added ABOVE the pinned AND-gate (untouched): if the SAME
port times out continuously (still LISTENING) for DEADTIME_CEILING_SEC (10 min)
of WALL TIME -- regardless of tick count or CPU -- kill anyway
(``reason="deadtime_ceiling"``). Bounds worst-case dead-time to ~10 min.

STATE PERSISTENCE
------------------
Consecutive-timeout + sustained-high-CPU streaks must survive across ticks (the
caller constructs a fresh WedgeReaper each tick in some deployments). State is a
small per-name JSON dict persisted the same way heartbeat_reaper-adjacent modules
persist state: atomic tmp+os.replace, ASCII, under data/frontend/ops/ (mirrors
reaper_status_bridge.py / output_freshness.py's DEFAULT path convention).

Design: the DECISION core (``observe``) is pure (no I/O, no spawning, injectable
clock); persistence (state load/save/decisions-write) lives in the companion
``http_wedge_reaper_io`` module (kept separate so THIS module -- the decision
core -- stays comfortably under the <=300 LOC rail, and so tests exercise the
decision logic with in-memory dicts, never touching a real socket, PID, file,
or wall clock). NEVER raises; stdlib-only; ASCII-only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_http_wedge_reaper.py -q
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

# Persistence helpers live in the companion io module; re-exported here for a
# single, stable import surface (``from ...http_wedge_reaper import load_state_file``
# keeps working even though the implementation moved to keep this file <=300 LOC).
from scripts.platformkit.autonomy.http_wedge_reaper_io import (
    DEFAULT_DECISIONS_PATH,
    DEFAULT_STATE_PATH,
    load_state_file,
    save_state_file,
    write_decisions,
)

# Verdicts.
KILL = "kill"
KEEP = "keep"

# PINNED thresholds (charter lane A). Changing these is a re-ratification, not a
# routine tune.
CONSECUTIVE_TIMEOUT_THRESHOLD = 3       # N consecutive probe timeouts
TIMEOUT_FLOOR_SEC = 10.0                # a probe must exceed this to count as "timed out"
CPU_PCT_THRESHOLD = 50.0                # sustained CPU% floor
CPU_SUSTAINED_SEC = 120.0               # how long CPU must stay above the floor

# 2026-07-15 amendment: independent, CPU-agnostic ceiling (see module docstring).
DEADTIME_CEILING_SEC = 600.0            # 10 min of unbroken timeouts -> kill anyway

def _new_state(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "consecutive_timeouts": 0,
        "cpu_high_since": None,   # epoch when CPU first crossed the threshold, or None
        "timeout_streak_since": None,  # epoch the current unbroken timeout streak began
        "last_verdict": KEEP,
        "last_kill_at": None,
    }


class HttpWedgeReaper:
    """Per-service consecutive-timeout + sustained-CPU wedge detector.

    Parameters
    ----------
    clock : callable() -> float
        Injectable epoch clock (default time.time) for deterministic tests.
    consecutive_timeout_threshold, timeout_floor_sec, cpu_pct_threshold,
    cpu_sustained_sec : the PINNED thresholds above, overridable only for tests
        (production callers should use the module defaults).
    """

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        consecutive_timeout_threshold: int = CONSECUTIVE_TIMEOUT_THRESHOLD,
        timeout_floor_sec: float = TIMEOUT_FLOOR_SEC,
        cpu_pct_threshold: float = CPU_PCT_THRESHOLD,
        cpu_sustained_sec: float = CPU_SUSTAINED_SEC,
        deadtime_ceiling_sec: float = DEADTIME_CEILING_SEC,
    ) -> None:
        self._clock = clock or time.time
        self._n_threshold = max(1, int(consecutive_timeout_threshold))
        self._timeout_floor = float(timeout_floor_sec)
        self._cpu_threshold = float(cpu_pct_threshold)
        self._cpu_sustained_sec = float(cpu_sustained_sec)
        self._deadtime_ceiling_sec = float(deadtime_ceiling_sec)
        self._state: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    def load_state(self, state: Dict[str, Dict[str, Any]]) -> None:
        """Seed in-memory per-name state from a previously-persisted dict
        (see :func:`load_state_file`). Malformed entries are dropped, never
        crash. Safe to call before the first ``observe``."""
        try:
            if not isinstance(state, dict):
                return
            for name, row in state.items():
                if isinstance(name, str) and isinstance(row, dict):
                    self._state[name] = dict(_new_state(name), **row)
        except Exception:  # noqa: BLE001 -- a corrupt seed must never crash the reaper
            pass

    def dump_state(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot of all tracked per-name state, for persistence."""
        return {k: dict(v) for k, v in self._state.items()}

    # ------------------------------------------------------------------ #
    def observe(
        self,
        name: str,
        *,
        port_listening: bool,
        probe_timed_out: bool,
        probe_elapsed_sec: Optional[float],
        cpu_pct: Optional[float],
    ) -> Dict[str, Any]:
        """Record one probe+CPU observation for *name*; return a verdict dict.

        Parameters
        ----------
        port_listening : whether the port is currently accepting TCP connections
            (a CLOSED port is a crash -- the normal dead-proc path owns that, so
            this reaper never counts it as a wedge signal and resets the streak).
        probe_timed_out : whether the HTTP readiness probe timed out this tick.
        probe_elapsed_sec : how long the probe took (or the configured timeout
            value if the caller only knows it exceeded the deadline); used only
            to confirm the timeout exceeded ``timeout_floor_sec`` (>10s per the
            charter). None is treated as "unknown duration" -> does not count.
        cpu_pct : the process's recent CPU utilization in percent (0-100+); None
            is UNKNOWN and never counts toward the sustained-high-CPU window
            (fail toward NOT killing on missing data).

        Returns ``{"name", "verdict", "detail"}`` where verdict is KILL or KEEP.
        NEVER raises -- a malformed observation degrades to KEEP so the reaper
        can never itself wedge the supervise tick.
        """
        try:
            now = float(self._clock())
            st = self._state.setdefault(name, _new_state(name))

            if not port_listening:
                # Port closed -> this is a crash (supervisor's normal path), not
                # a wedge. Reset all streaks so a later relaunch starts clean.
                st["consecutive_timeouts"] = 0
                st["cpu_high_since"] = None
                st["timeout_streak_since"] = None
                return self._verdict(st, KEEP, {
                    "reason": "port_not_listening", "port_listening": False,
                })

            # -- timeout streak -------------------------------------------------
            counts_as_timeout = bool(probe_timed_out) and (
                isinstance(probe_elapsed_sec, (int, float))
                and float(probe_elapsed_sec) > self._timeout_floor
            )
            if counts_as_timeout:
                st["consecutive_timeouts"] = int(st.get("consecutive_timeouts", 0)) + 1
                if st.get("timeout_streak_since") is None:
                    st["timeout_streak_since"] = now
            else:
                st["consecutive_timeouts"] = 0
                st["timeout_streak_since"] = None

            # -- sustained-CPU streak -------------------------------------------
            cpu_high_since = st.get("cpu_high_since")
            cpu_ok = isinstance(cpu_pct, (int, float)) and float(cpu_pct) > self._cpu_threshold
            if cpu_ok:
                if cpu_high_since is None:
                    cpu_high_since = now
                    st["cpu_high_since"] = cpu_high_since
            else:
                cpu_high_since = None
                st["cpu_high_since"] = None

            cpu_sustained = (
                cpu_high_since is not None
                and (now - float(cpu_high_since)) >= self._cpu_sustained_sec
            )

            timeout_tripped = st["consecutive_timeouts"] >= self._n_threshold
            timeout_streak_since = st.get("timeout_streak_since")
            deadtime_sec = (
                round(now - float(timeout_streak_since), 1)
                if timeout_streak_since is not None else 0.0
            )
            deadtime_tripped = (
                timeout_streak_since is not None
                and (now - float(timeout_streak_since)) >= self._deadtime_ceiling_sec
            )
            detail = {
                "port_listening": True,
                "consecutive_timeouts": st["consecutive_timeouts"],
                "n_threshold": self._n_threshold,
                "cpu_pct": cpu_pct,
                "cpu_sustained_sec": (
                    round(now - float(cpu_high_since), 1) if cpu_high_since is not None else 0.0
                ),
                "cpu_threshold_pct": self._cpu_threshold,
                "cpu_sustained_required_sec": self._cpu_sustained_sec,
                "timeout_tripped": timeout_tripped,
                "cpu_tripped": cpu_sustained,
                "deadtime_sec": deadtime_sec,
                "deadtime_ceiling_sec": self._deadtime_ceiling_sec,
                "deadtime_tripped": deadtime_tripped,
            }

            def _reset_streaks() -> None:
                st["consecutive_timeouts"] = 0
                st["cpu_high_since"] = None
                st["timeout_streak_since"] = None

            if timeout_tripped and cpu_sustained:
                st["last_kill_at"] = now
                # Reset streaks post-kill-decision so the caller's relaunch gets
                # a clean window (mirrors heartbeat_reaper.note_restarted intent,
                # but the CALLER kills; we just clear our own bookkeeping here so
                # a repeated observe() before the relaunch lands doesn't double-count).
                _reset_streaks()
                return self._verdict(st, KILL, detail)

            if deadtime_tripped:
                # 2026-07-15 ceiling: CPU-independent -- a wedge stuck low-CPU/
                # I/O-blocked for the full ceiling window is killed anyway.
                st["last_kill_at"] = now
                detail["reason"] = "deadtime_ceiling"
                _reset_streaks()
                return self._verdict(st, KILL, detail)

            return self._verdict(st, KEEP, detail)
        except Exception:  # noqa: BLE001 -- reaper must never crash the tick
            return {"name": name, "verdict": KEEP, "detail": {"reason": "observe_raised"}}

    def _verdict(self, st: Dict[str, Any], verdict: str,
                 detail: Dict[str, Any]) -> Dict[str, Any]:
        st["last_verdict"] = verdict
        return {"name": st["name"], "verdict": verdict, "detail": detail}

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot every tracked service's last verdict + streak state."""
        return self.dump_state()


__all__ = [
    "HttpWedgeReaper",
    "KILL",
    "KEEP",
    "CONSECUTIVE_TIMEOUT_THRESHOLD",
    "TIMEOUT_FLOOR_SEC",
    "CPU_PCT_THRESHOLD",
    "CPU_SUSTAINED_SEC",
    "DEADTIME_CEILING_SEC",
    "DEFAULT_STATE_PATH",
    "DEFAULT_DECISIONS_PATH",
    "load_state_file",
    "save_state_file",
    "write_decisions",
]
