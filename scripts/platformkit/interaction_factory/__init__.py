"""scripts.platformkit.interaction_factory -- autonomous generation + honest
testing of composed attribute INTERACTIONS.

The AI writes/combines/tests more signals on its own: a deterministic generator
enumerates TYPED candidate interactions from the per-sport attribute registries
(never all-pairs-blind), and a runner fits baseline vs baseline+interaction with
a cluster-robust p-value, gated by the SAME FWER-tightening curve the combo
lane uses (scripts.platformkit.combo.fwer_budget). Survivors are PROVISIONAL --
belief needs an independent-corpus replication pass (the existing standard).

Calibration/measurement only. edge_claimed:false on every ledger row. An honest
NULL or NOT_TESTABLE is a recorded SUCCESS, never a FAILURE.
"""
