# S31 Student Gate Defects - Construct Evidence

## Scope and contract

This is the two-case, fully enumerated CONSTRUCT row specified in
`docs/evidence/tracking/specs/S31_spec.md`. It was checked against
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q8.

## Step 0: premise re-measurement

Before the change, `_states()` assigned `game_id=f"g{index}"` to all 1,000
rows. Each existing corpus therefore had 1,000 singleton groups, so
`intraclass_correlation()` returned 0.0 at its `total <= count` guard and the
existing tests could not exercise the `< 20` cluster branch. The unmodified
file passed before the change: `3 passed in 15.95s`.

The same source review found `_student_plus_ids()` passing literal `50.0` to
`_id_summary()`, while `run_student_gate()` accepted no `prior_strength`.
Both filed premises were true.

## Limit and change

Limit: n/a; this row enumerates two construct cases. The change adds a
keyword-only `prior_strength: float = 50.0` to `run_student_gate()` and to
`_student_plus_ids()`. The gate passes that one value to both the fixed-effect
baseline and the student-plus-IDs arm. Omitted calls retain 50.0.

## Acceptance reproduction

The sole new test constructs every case: 19 distinct game IDs, 12 correlated
ticks per game, 228 rows total, deterministic seed 31. It excludes no rows.

| Case | Before | After | Result |
| --- | --- | --- | --- |
| Clustered INSUFFICIENT branch | 0/1: existing singleton rows forced ICC 0.0 and 1,000 clusters | 19 clusters, ICC 0.06523890406912343, n_eff 132.74120317820655 | `INSUFFICIENT` because 19 < 20 |
| Non-default ID prior | 0/1: no threading path; student-plus-IDs used 50.0 | `prior_strength=3.0` payload Brier 0.25836680252134037 equals independent walk-forward replay within 1e-12 | Pass |

For the second case, the independent replay calls `_student_plus_ids()` in
each walk-forward prediction at the same prior. Its Brier is
0.25836680252134037. At the old/default strength of 50.0 the same construct
instead gives 0.25012609422354715, so the values now diverge as required.

The construct artifact sealed before scoring with preregistration SHA-256
`d55a6309322ac8e602a999cc032be478c6b74c3e1f1a419740f89a12ec61a0fe` and
recorded launch `k_cumulative=1` in its ledger before the arm metrics.

## Verification

Command run:

```text
python -m pytest scripts/platformkit/eval_gate/test_student_gate.py -q
....                                                                     [100%]
4 passed in 6.26s
```

Reproduction is the same command: the new test asserts the `INSUFFICIENT`
verdict, positive ICC, and independently replayed student-plus-IDs Brier.
The reader check found only the gate's two internal call sites and this test's
call sites. `_DELTA_BRIER_BAR` (0.004), `_P_BAR` (0.05), `_MIN_N_EFF` (30.0),
and `_MIN_CLUSTERS` (20) are untouched.

## Contract self-check

- B1: all 228 construct rows and all 19 clusters are scored; none are excluded.
- B2/B6: parameter additions only; no schema, status, import, or module moved.
- B3/B4: no absent-evidence behavior or claim lifecycle changed.
- B5: no pod action or deployment occurred.
- B7: the construct enumerates all cases, not a head slice.
- B8: every arm, including the independent replay, uses `walk_forward()`.
- B9: the denominator is 19 distinct non-singleton constructed game groups, not recycled IDs.
- B10/Q3: no bar or threshold changed.
- Q1/Q2: the existing gate writes the sealed preregistration before ledger charge
  and scoring; the generated construct artifact reports the SHA and launch K above.
- Q4: all scored arms use the gate's walk-forward path; the new replay matches to 1e-12.
- Q5/Q6: this is not an AHEAD result and uses calibration language only.
- Q7: n=2 CONSTRUCT cases are exhaustive and therefore exempt from sampled-metric n.
- Q8: both premises were re-measured before the additive change.

## NOT VERIFIED

- No real trial is sealed by this construct row.
- S26 still blocks any real teacher.
