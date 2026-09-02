# S05 Calibration Report Preregistration

Scope: produce an evidence-only calibration report for NBA, MLB, soccer, and tennis cached gate corpora.

Predeclared inputs: `load_gate_corpus(sport)` only; cached inputs remain read-only. Every row with a finite corpus probability and a binary `y` is scored. Missing or invalid rows are counted as dropped.

Predeclared method: use `buckets` verbatim; use `fit_per_regime` with its existing GLOBAL fallback below `min_n=200`; derive scored outputs through `walk_forward_recalibrate` expanding inner folds. Reliability is ten bins. The comparison reports ECE, Murphy reliability/resolution/uncertainty, sharpness, and `max_loser_wp`.

Predeclared verdict: `IMPROVES` only when ECE decreases, Murphy reliability decreases, and Murphy resolution does not decrease. Otherwise the verdict is `FLATTENED`. A corpus with fewer than 200 usable rows is `INSUFFICIENT` and carries no metric values. An input rejected by its read-only loader is `INPUT_UNAVAILABLE` and is not counted toward artifact completeness.

Predeclared acceptance bar: four artifacts, one per sport, each with ten bins and per-bin n, max-loser-WP, ECE before/after, three Murphy terms, sharpness, named prediction column, dropped-row count, and verdict. The denominator is four sports.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q. No serving path, feature flag, registry file, evaluation-gate threshold, or charged ledger is changed.

Seal SHA-256 of the pre-seal content above: `9051BB6E3BD89F7309A799F9739C8E61EA6DB3530E52AD87666568220591DF8A`.
