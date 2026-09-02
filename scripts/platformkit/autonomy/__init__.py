"""scripts.platformkit.autonomy -- A5/A6 self-healing + self-monitoring substrate
(flag-OFF, additive).

Modules:
  heartbeat_reaper  -- wires ops.circuit_breaker so a STALE heartbeat (hung loop,
                       not just a crash) trips a breaker and signals a restart;
                       a hung loop must NOT read READY forever.
  resource_governor -- psutil-OPTIONAL fail-safe governor; under low/unknown
                       headroom returns a DISTINCT status DEFERRED_RESOURCE (an
                       under-run that is NEVER misread as honest-reject/plateau).
  progress_tripwire -- exposes cursor_age so liveness != progress: a fresh
                       heartbeat must NOT hide a stalled cursor.
  work_queue        -- durable lease-based task queue (enqueue/lease/ack/nack +
                       visibility-timeout re-lease) persisted atomically under
                       data/cache/autonomy/; the loop pops its OWN next task.
  schedule_policy   -- pure season-aware chooser: when idle, decide which sport /
                       candidate family is due; an honest IDLE when nothing is
                       (idle != fabricated work; idle != green-when-dead).
  status_composer   -- A6: the ONE canonical autonomy status the UI renders. Merges
                       services (liveness+freshness, inheriting health_aggregator
                       ._row_severity), loop (cycle/verdict/candidate), ratchet
                       history, per-sport high-water marks, and an explicit honest
                       idle_reason. Monotone-DOWN: a stale feed is RED, never green.
  loop_observer     -- A6 self-monitor: per-loop liveness-vs-progress verdict via
                       progress_tripwire over the canonical status -- a fresh
                       heartbeat over a frozen cursor is DEGRADED, a dead one DOWN.
  heartbeat_orphan_sweep -- prunes STALE + manifest-unowned daemon_heartbeats/*.txt
                       leftovers (dead-daemon stems) so the orphan note self-heals;
                       fail-CLOSED + idempotent -- never deletes a live/fresh stem.

Rails: additive + reversible + flag-OFF; never flips a flag ON; never writes
data/registry/; ASCII-only; <=300 LOC/file; stdlib + optional psutil only.
"""
from __future__ import annotations

__all__ = [
    "heartbeat_reaper",
    "resource_governor",
    "progress_tripwire",
    "work_queue",
    "schedule_policy",
    "status_composer",
    "loop_observer",
]
