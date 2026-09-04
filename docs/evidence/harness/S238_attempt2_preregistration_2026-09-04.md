# S238 attempt 2 preregistration

## Scope

This preregistration covers only the additive S238 STATIC grouped
split-conformal report for the S123 NBA incumbent series. It will apply
`apply_incumbent(rows, "e4" | "ladder_base", embargo_days)` to the archived
NBA tick rows and report held-out grouped empirical coverage at nominal 0.90
and 0.80 with mean and median interval half-width beside every reported cell.

The binding before-condition is specific to S123: S101 has `ARMS =
("market", "model")`, so it does not report incumbent coverage or width.
General width routes exist and do not alter that before-condition.

## Fixed protocol

- Reuse S101 constants unchanged: `COVERAGE_MIN_GROUP = 400`,
  `COVERAGE_MAX_GROUPS = 50`, two minimum groups, nominal levels 0.90 and
  0.80, and the S86 five-fold game-first-date block design.
- Use a shared evaluator from `scripts/platformkit/eval_gate/` for every
  scored quantity, with a game purge and a symmetric nonzero one-day embargo.
  The evaluator callback will construct train-only calibration half-widths,
  hold them fixed on test rows, and return all coverage and width quantities.
- A test cell with fewer than 400 ticks is emitted with its honest count and
  `ABSENT_BECAUSE`; it is never pooled as a substitute for a reported cell.
- The output JSON will retain fold identifiers, tick and game counts, interval
  bounds, and the grouped cell summaries needed for independent reproduction.
- Reproduce S101 market/model STATIC coverage from its unchanged implementation
  and require an absolute difference no greater than 1e-9.

## Acceptance and reporting

The run will print archive-measured ticks and games beside the specification
reference of 465249 ticks and 1593 games, identify which count was used, print
all S123 coverage and half-width cells, and write the JSON and memo named by
the S238 specification. A SCREEN NULL or BEHIND result remains a valid
calibration outcome. No deployment or flag change is in scope.

## Charge at launch

Before the first archive score, the attempt will append its launch row to
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` and record the K value read at launch
in the run artifact. This preregistration itself performs no archive scoring.

SEAL_SHA256: 1496560415D30BA193C41BC1A701DC7804314D1C5DAF33CA346FC269DFDD96B6
