# S268 Attempt 2 Preregistration: Sibling Distributional CPCV Route

## Scope

This preregistration fixes the only construct and archive comparisons scored in
attempt 2. It implements `docs/evidence/tracking/specs/S268_spec.md` and
self-checks `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

The machine is local: `C:\Users\neelj\nba-track-a17`, branch `track-a17`.
No deployment, register, ledger, or write under `data/` is authorized.

## Protected route and additive route

Before this preregistration's scoring, `cpcv_engine.py` is restored from
`master` and must have whole-file SHA-256
`e9fe694a721658a067bd452911b7f95627897ba4d6c6dccd86cc080f9fa6935c`.
Attempt 2 adds only the sibling module
`scripts/platformkit/eval_gate/cpcv_distribution.py`. It imports
`cpcv_engine` read-only and reuses its `cpcv_splits` fold construction,
`_blocked_indices` symmetric purge, and test redaction/vintage guard without
changing `cpcv_engine.py`, `cpcv.py`, `walkforward.py`, `PURGE_HOURS`, or
`EMBARGO_DAYS`.

The sibling public function accepts a predictor returning a non-empty empirical
forecast sequence and a `score_fn(forecast, settled_outcome)` callback returning
named finite per-row quantities. It retains split id, state identity, timestamp,
forecast samples, settled outcome, and training count. A debug-only purge-off
switch is allowed solely for the construct fixture, never for archive scoring.

## Fixed comparisons

The construct builds 32 seeded regular states plus one planted same-team state
at 47 hours from the target. All states are valid vintage states. With 33
single-date CPCV groups and one test group, a degenerate point-mass forecast's
mean Brier through the sibling route must match `cpcv_evaluate` to <= 1e-9.
The purge-off comparison must differ from purge-on, and the planted target's
leaky loss must be strictly lower than its honest loss.

The archive input is `data/frontend/prop_history_corpus_mlb.jsonl`, opened
read-only. It has 3,000 rows in 777 date clusters. A declared pre-corpus anchor
only makes the earliest real cluster testable and is excluded from the real-row
denominator. The sibling route produces a per-row paired-loss CSV and compares
unweighted cluster means to these fixed S244 quantities, each with absolute
delta <= 1e-9 or an exact discrepancy and CLOSED AT LIMIT:

| Quantity | Target |
|---|---:|
| CRPS | 0.5098297809224259 |
| Pinball q10 | 0.08655308369594088 |
| Pinball q50 | 0.37323931073931077 |
| Pinball q90 | 0.2013804110232682 |

No comparative calibration conclusion beyond these route checks is made. Q2 is
not applicable: this is a fixed baseline reproduction and the task prohibits
ledger writes. No AHEAD verdict is possible.

## Required outputs and test

- `S268_distributional_evaluator_route_2026-09-04_attempt2.md`
- `S268_distributional_evaluator_route_fixture_2026-09-04_attempt2.json`
- `S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04_attempt2.csv`
- A focused per-file test that reads this working-tree file, normalizes CRLF to
  LF, and hashes the bytes above this seal line. It must assert exact values
  only on the construct fixture and structural properties only on the real
  archive.

S268_ATTEMPT2_PREREG_SEAL_SHA256=cfbeb06cb7678d45b892f9941fcab389b21039d8f8e592eed2ad256ea596eff3
