# S306 preregistration: S106 requote importer test

Date: 2026-09-07
Spec: `docs/evidence/tracking/specs/S306_spec.md`
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Scope is a local, archive-free construct test. No store is opened, no evaluator
run is launched, and no model-side comparison is made. The only implementation
file exercised is `scripts/platformkit/eval_gate/s106_requote.py`; its SHA-256
before the test work is
`6556ed197cbf6e2f18cd60d4c5237c35379f09821b31542a6803cec8fe5b2c7a`.

The fixed fixture has three rows. Its `seq_by` mapping maps only
`(A, 2026-07-05T20:00:00Z)` to sequence 2. The assertions are fixed before
the test exists:

1. The matched row becomes cluster `A#2`.
2. The unmatched `B` row remains sequence 1 and cluster `B#1`.
3. `_attach` preserves the three-row input count and reports two unmatched rows.
4. `_pair` reproduces the fixture's before-CI calculated directly by `_quote`
   against `game` before the corrected cluster is used. The exact fixture has a
   literal `#` cluster and the test requires equality to 1e-12.

This is CONSTRUCT evidence only (n = 4 enumerated behaviours), not a scored
calibration claim. When a delta is named by code comments, its sign convention
is improvement = baseline loss minus candidate loss; positive means candidate
better. No such delta is reported here.

Seal-SHA256-LF: dc33d5e72bdf47962f26183f09071f60ebf0ee62b1151f0088208a23157f5dd0
