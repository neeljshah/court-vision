# S259 in-game power audit v2 preregistration

## Scope

This preregistration covers the corrective audit requested by
`docs/evidence/tracking/specs/S259_spec.md`. It will enumerate every markdown
memo under `docs/evidence/harness/` whose text contains an in-game spelling, a
confidence-interval spelling, and a numeric calibration-improvement statement.
The enumerated population is construct-only; no screen is excluded silently.

## Frozen comparison and quantities

The frozen bar is +0.004 Brier delta. For each enumerated screen, the auditor
will report `n_ticks`, `n_game_clusters`, unequal-cluster-corrected `n_eff`,
observed improvement, CI half-width, 80 percent-power minimum detectable Brier
delta, and the resulting `UNDERPOWERED` or `REFUTED-AT-BAR` label. S94 will be
audited from its archived differential rather than classified as absent. S102
will use 192635 observations per hypothesis. S210 and S259 output memos are
excluded from the source denominator only.

## Reproduction and execution

Before producing the artifact, the auditor will print the source grep, sorted
file list, count, and the S82 and S117 anchors. The correction will use the
shared `scripts/platformkit/eval_gate/` evaluator with purge and a symmetric,
nonzero embargo when a probability comparison is recomputed; the evaluator
callback will create every such probability. Inputs will be opened one at a
time and the audit will not write under `data/`, or alter an existing evidence
artifact, the register, or either ledger.

## Outputs and checks

The committed outputs will be a new memo, JSON manifest, read-only auditor of
at most 300 lines, and one per-file test. The test will assert S84 inclusion,
the S102 denominator, S94 archived status, and the additive `filter` field.
The final memo will identify this preregistration and its seal, report hashes,
the test command, the printed source count, and the two anchors.

Seal: b0e6c0160209b975d3e8ef5890ae16eb895d8e54f3d405a31c24b92f835c2fe1
