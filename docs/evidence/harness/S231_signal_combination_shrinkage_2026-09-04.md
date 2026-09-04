# S231 Signal Combination Shrinkage

Verdict: FALSIFIED at premise step 0. No weighting module, per-arm series,
weight vectors, or focused test was created because the archived S114 anchors
did not reproduce within the required tolerance.

## Scope, contract, and preregistration

This ran locally in `C:\Users\neelj\nba-track-a17` on branch `track-a17`.
The reason is that step 0 is a read-only archived-series reproduction. No pod,
data registry, FWER ledger, register, feature flag, or serving path was read
or changed.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Preregistration: `docs/evidence/harness/S231_signal_combination_shrinkage_prereg_2026-09-04.md`.
Its pre-seal SHA-256 is
`DB5404DD9A9979B1B0FB7E6DC1BF3CC3744EFAD823F25A6CC61E018DAB5C86F3`,
created before the metric computation.

## Inputs and reproduction

One store was opened for the comparison:

```text
data/cache/eval_gate/s114_ingame_ensemble_series.csv
44,158,218 bytes
no resolution
SHA-256 916993FD8CB51B9F1907B3DD4E818198B50B3B09433479BE4B5F1CC8EE326B8B
```

The series has 192,635 rows, 673 unique `game` clusters, and zero duplicate
`(game, ts)` pairs. The accompanying archived metadata was identity-checked
separately, after the series comparison:

```text
data/cache/eval_gate/s114_ingame_ensemble.json
29,727 bytes
no resolution
SHA-256 8DE6ED1C35BCD184B470854E6ADA4E1698B10A01DCC0002AA1EC63BB2D194DA5
```

For every series row, the recomputation used mean squared loss
`mean((p - y)^2)` and reported the raw-line Brier difference as
`brier(raw) - brier(arm)`. The result is:

| Anchor | S114 target | Archived-series result | Absolute difference |
|---|---:|---:|---:|
| k=1 vs raw in-play line | -0.000484000000000 | -0.000537356817711 | 0.000053356817711 |
| k=5 vs raw in-play line | -0.000400000000000 | -0.000243149839129 | 0.000156850160871 |
| k=5 over k=1 | +0.000083000000000 | +0.000294206978582 | 0.000211206978582 |

The maximum absolute anchor difference is `0.000156850160871`, exceeding the
S231 limit of `0.000000001`. Therefore the premise is false for the archived
series currently present in this worktree.

## Consequence

S231 explicitly requires no weighting fit if either k=1 or k=5 fails the
premise reproduction. Accordingly, inverse-variance, James-Stein, ridge/logit,
and confidence-ensemble arms were not evaluated. There are no per-arm
intervals, effective sample sizes, member counts, weight vectors, or caller
changes to report. The immutable +0.0000830 ceiling was not evaluated and was
not changed.

Caller list: none; no helper was created or touched. Test line: NOT RUN; the
specified new test is contingent on a permitted new weighting helper, which
the falsified premise prohibits.

## NOT VERIFIED

- Unbuilt weighting arms, intervals, effective sample sizes, per-arm series,
  weight vectors, and future-row focused test.

## Verifier self-check

- B1-B10: no scoring denominator was altered, no schema or caller changed,
  no deployment occurred, and no existing file was moved or edited.
- Q1: the preregistration was sealed before the one scored premise comparison.
- Q2: SCREEN-only; no ledger was read, charged, or written.
- Q3: the S231 limit and ceiling are copied unchanged above.
- Q4 and Q9: no new out-of-sample arm or meta-learner was fitted; the result
  is a direct reproduction from S114's archived, game-clustered differential.
- Q5: no AHEAD finding is made.
- Q6: calibration measurement only.
- Q7: the premise series denominator is 192,635 rows over 673 game clusters.
- Q8: this memo records the required premise remeasurement first.
