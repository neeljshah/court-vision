"""src/sim/agent — Entity-Agent Layer package.

ROADMAP PHASE: Domain 1 — Entity-Agent Layer (D01_entity_agent.md).
GATE: This package is import-safe and default-OFF.  Nothing here changes any live
prediction path until Stage 2 of the migration plan (D01 §8).  All CV_AGENT_* flags
default to OFF (see flags.py when created in the executor phase).

Exports (typed contracts only — executor phase fills build/policy logic):
  SimAgent        — lean frozen hot-path block the possession kernel reads.
  LeverPack       — four unused levers, default-neutral (OFF == no-op).
  AgentProvenance — schema version + tier + content hash + freshness stamps.
  TeamAgent       — composition of SimAgent + scheme block + levers + provenance.
  validate        — structural correctness check; GATE: must pass before flag flips ON.

Nothing in this __init__ imports torch or pandas at module load (lazy inside functions).
The package co-exists with basketball_sim.TeamModel; neither replaces nor patches the other.

# TODO(P1.1): expose build_team_agent, PlayerAgent policy methods once build.py / policy.py
#             are written by the executor phase.
"""
from .schema import AgentProvenance, LeverPack, SimAgent, TeamAgent, validate

__all__ = [
    "SimAgent",
    "LeverPack",
    "AgentProvenance",
    "TeamAgent",
    "validate",
]
