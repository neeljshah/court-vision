"""scripts.platformkit.improve -- always-on self-improvement daemon glue.

Thin ORCHESTRATION layer over the existing Milestone-8 ratchet (improve/*) and the
per-sport recalibration (scripts.platformkit.self_improve). It adds ONLY the missing
plumbing the ratchet needs to run unattended forever:

  * a versioned artifact STORE with an atomically-swapped `current` pointer + rollback
    (artifact_store.py),
  * a checkpoint/resume cursor so a restart never reprocesses settled games
    (checkpoint.py),
  * the one-cycle + run_forever driver that wires settled-games -> recalibrate ->
    5-gate verdict -> replication(>=2 corpora) -> stage+swap | reject_ledger ->
    proposals.jsonl, with per-source error isolation (selfimprove_daemon.py).

It NEVER edits MEMORY.md, NEVER writes data/registry/, NEVER flips a feature flag.
A SHIP requires the 5-gate unanimous verdict AND replication on >= 2 corpora; one
corpus is REPLICATION_PENDING, never a SHIP. Calibration, not edge. ASCII only.
"""
