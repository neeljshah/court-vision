"""scripts.platformkit.selfheal -- self-heal escalation ladder (advisory only).

Tracks consecutive-stale streaks per daemon and emits a RESTART_RECOMMENDED feed.
Pure advice: executes NOTHING, flips no flag, never restarts any process.

Modules
-------
escalation_ladder  -- streak accumulator + threshold policy (stateless pure logic)
escalation_runner  -- ticks the ladder, persists streaks, writes escalation_feed.json

SAFETY INVARIANTS: MEASUREMENT-ONLY; no $ field; calibration not edge; <=300 LOC/file;
ASCII only; never raises out of public API; never calls proc.restart/stack_specs/flag.
"""
__all__ = ["escalation_ladder", "escalation_runner"]
