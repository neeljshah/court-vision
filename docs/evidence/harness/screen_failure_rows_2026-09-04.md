# S176 Screen Failure Rows - FALSIFIED

## Contract

This landing follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`.
The S176 premise was checked before source changes, replay construction, or test execution.

## Premise result

| Check | Required premise | Observed | Result |
|---|---|---|---|
| Shipped database path | `data/cache/eval_gate/s85_screen_2026-09-03.sqlite` exists and opens read-only | The path is absent in this worktree. | FALSIFIED |
| Source module location | Foundry modules named by the spec are available for a possible repair | Present under `scripts/platformkit/foundry/` and `scripts/platformkit/foundry_runner.py`, not at the literal root `foundry/` paths. | Informational |

Because the read-only S85 store is absent, its required MD5, queue/result census,
14-family breakdown, and 167-row no-outcome count cannot be reproduced. No store was
opened and no substitute store was selected. The required denominator of 1,125 is
therefore not established in this worktree.

## Stop result

S176 requires a stop and a FALSIFIED report when the census differs. No production or
harness source was changed, no replay was constructed, and no test was run. The
requested `SCREEN_FAILED` schema and claim-path changes are not applied because the
premise guard did not pass.

## Verifier self-check

| Check | Result |
|---|---|
| B1 circular metric | Not applicable: no metric was computed. |
| B2 additive schema | Pass: no schema change. |
| B3 fall-through loss | Not evaluated: source untouched. |
| B4 re-claim loop | Not evaluated: source untouched. |
| B5 pre-verification deployment | Pass: no deployment. |
| B6 orphans | Pass: no source moved or retired. |
| B7 head-slice evidence | Not applicable: no sample or metric. |
| B8 self-fit as independent | Not applicable: no scored comparison. |
| B9 degenerate denominator | Not applicable: denominator unavailable. |
| B10 moved bar | Pass: no bar changed. |
| Q1 prereg sealed before scoring | Not applicable: no scoring. |
| Q2 ledger charged before metric | Not applicable: no charged trial or metric. |
| Q3 no bar moved | Pass: no bar changed. |
| Q4 CPCV leak contract | Not applicable: no OOS score. |
| Q5 two corpora for any ahead | Not applicable: no ahead verdict. |
| Q6 calibration language only | Pass: this memo contains no performance or market claim. |
| Q7 construct enumeration | Not reached: the seed store is absent. |
| Q8 premise first | Pass: the S85 file existence was checked before action. |
| Q9 archive differential | Not applicable: no scored differential. |

## NOT VERIFIED

- S85 MD5 and the 1,125-row queue/result census.
- The 14-family breakdown and 167 no-outcome rows.
- The proposed result-row behavior and second claim pass.
- The new per-file test, which is intentionally not created after the premise stop.

Verdict: FALSIFIED.
