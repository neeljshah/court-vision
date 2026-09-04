# S268 Distributional Evaluator Route Preregistration

## Scope

This preregistration fixes the only comparisons to be scored after this file is
committed. It implements `docs/evidence/tracking/specs/S268_spec.md` and cites
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

## Machine and inputs

The work runs locally in `C:\Users\neelj\nba-track-a17` on branch `track-a17`.
No deployment, ledger, register, or data-file write is authorized. The only
source corpus is opened once, one file at a time:

| Path | Expected rows | Expected date clusters | Resolution |
|---|---:|---:|---|
| `data/frontend/prop_history_corpus_mlb.jsonl` | 3,000 | 777 | none |

## Fixed route and comparison rules

The new public route will be a sibling of `cpcv_evaluate` in
`scripts/platformkit/eval_gate/cpcv_engine.py`. It will call the existing
`cpcv_splits` construction with `embargo_blocks=0`, then apply the existing
`_blocked_indices` purge and symmetric embargo. It will import, without
changing, `PURGE_HOURS=48`, `EMBARGO_DAYS=3`, `_same_team`, and
`_same_matchup` from `walkforward.py`.

Each predictor returns a non-empty empirical sample sequence. A supplied
scoring function receives `(forecast, settled_outcome)` and returns the named
per-row quantities. The route retains the forecast sequence, split id, state
identity, timestamp, settled outcome, and training count in its record.

For the synthetic fixture, use exactly 32 seeded states (`random.Random(268)`) at
daily timestamps, unique regular teams, and valid feature-vintage metadata. One
additional seeded state is a planted leak: its feature holds the selected test
row's settled outcome and it is 47 hours from that test row while sharing a
team. With the normal route it must be purged by the existing 48-hour same-team
rule; with `debug_disable_purge=True` it remains train-eligible. The predictor
returns a degenerate point-mass empirical forecast. The fixture scores Brier as
`{"brier": (forecast[0] - outcome) ** 2}`. It compares normal-route Brier with
the scalar `cpcv_evaluate` Brier on the same fixture, and compares normal-route
Brier with the debug-only purge-disabled rerun. The planted metric must score
strictly better in the leaky rerun than in the normal rerun.

For the MLB reproduction, convert every corpus row into one valid evaluation
state and add one declared non-corpus anchor state before the first corpus date
only to make the first real date CPCV-testable. Use 778 single-date CPCV groups
and one test group. The anchor is never included in the 3,000-row denominator.
The empirical forecast uses only player observations strictly earlier than the
test date from the handed training rows; the route still constructs and purges
the full symmetric CPCV train side. A player with no eligible history has the
fixed point mass `[0.0]`. Score CRPS and pinball q10, q50, q90 for every real
row, write every per-row forecast/loss and every per-date-cluster mean, then
compare the unweighted mean of all 777 cluster means against the S244 values:

| Quantity | Archived target | Bar |
|---|---:|---|
| CRPS | 0.5098297809224259 | absolute delta <= 1e-9, else exact discrepancy and CLOSED AT LIMIT |
| Pinball q10 | 0.08655308369594088 | absolute delta <= 1e-9, else exact discrepancy and CLOSED AT LIMIT |
| Pinball q50 | 0.37323931073931077 | absolute delta <= 1e-9, else exact discrepancy and CLOSED AT LIMIT |
| Pinball q90 | 0.2013804110232682 | absolute delta <= 1e-9, else exact discrepancy and CLOSED AT LIMIT |

The fixture Brier equality bar is absolute delta <= 1e-9. The fixture
purge-on/off delta must be nonzero. No comparative calibration claim beyond
these fixed route checks is made. Q2 is not applicable: this is a fixed
baseline reproduction with no charged candidate trial, and the task prohibits
ledger writes. No AHEAD verdict is possible.

## Required artifacts and verification

- `docs/evidence/harness/S268_distributional_evaluator_route_2026-09-04.md`
- `docs/evidence/harness/S268_distributional_evaluator_route_fixture_2026-09-04.json`
- `docs/evidence/harness/S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04.csv`
- One new focused fixture test, run alone.
- SHA-256 checks establish `cpcv_engine.py` and `walkforward.py` are
  byte-identical to `master`; `cpcv_evaluate` itself is compared as a Git blob.

S268_PREREG_SEAL_SHA256=92ef14c0a3d10364ce2c0e9c5d41f484f9163777a3837d64e2d2059887672b1a
