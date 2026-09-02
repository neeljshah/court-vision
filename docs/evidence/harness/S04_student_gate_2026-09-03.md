# S04 student gate -- 2026-09-03

GAP S04 | sport all | worktree a12 | log cx_s04_student_gate

Contract: [VERIFIER_CONTRACT.md](../tracking/VERIFIER_CONTRACT.md), sections B
and Q1-Q8. This is a deterministic CONSTRUCT harness result, not a real
teacher trial. The preregistered rule is sealed in the output JSON before the
first metric, and each temporary ledger receives its row before the first
Brier calculation.

| Construct corpus | Rows | ID baseline Brier | Student Brier | Student + IDs Brier | Delta Brier | DM 95 pct CI | Deflated p | Launch K | n_eff | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| outcome sigmoid(latent[player_id]); teacher noise | 1,000 | 0.243247 | 0.290193 | 0.281802 | -0.046946 | [-0.060505, -0.033387] | 1.972956e-11 | 1 | 1,000 | NULL |
| outcome sigmoid(teacher); teacher orthogonal to ID | 1,000 | 0.252282 | 0.218487 | 0.218954 | 0.033795 | [0.022299, 0.045291] | 1.106825e-08 | 1 | 1,000 | TEACHES |

Both cases score every one of their 1,000 rows in all three arms; no rows are
excluded. The fixed-seed test uses one unique game cluster per row, so each
construct has 1,000 clusters and ICC=0.0 from the student residuals. `n_eff`
is recomputed from those scored residuals, never supplied as a constant. The
second construct checks the fixed bars unchanged: delta Brier >= 0.004,
DM interval excluding zero, deflated p < 0.05 at launch K, and student minus
student+IDs Brier <= 0.004 (-0.000466).

The test also makes `feature_avail={}` and reproduces `LeakError`. It monkeypatches
the first Brier call to confirm that the temporary ledger row is already
appended and that its `k_cumulative` equals the pre-metric JSON value. The
temporary ledgers are separate from `data/cache/eval_gate/backtest_fwer.jsonl`.

Test output:

```text
3 passed in 5.88s
```

Acceptance record: before was zero passing cases because the module was absent;
after is 2/2 deterministic construct cases at n >= 1,000, with the required
NULL and TEACHES verdicts. `n = 2 (CONSTRUCT)`; every listed construct is
enumerated. Eye check = n/a (S-row); reproduction = rerun
`python -m pytest scripts/platformkit/eval_gate/test_student_gate.py -q` and
recompute the JSON arm scores from the fixed synthetic rows.

NOT VERIFIED:

- No real teacher is evaluated or sealed. The first real teacher remains
  blocked on S26.
- This construct validates the gate behavior only; it does not establish a
  calibration result for any production model.
- No output was deployed and no feature flag changed.

Self-check: B1 no exclusions; B2 additive files only; B3 no absent-evidence
quarantine; B4 no persistent claim path; B5 no deployment; B6 no moved module;
B7 not applicable to an S-row; B8 scoring is walk-forward OOS; B9 the
denominator is all unique construct rows; B10 bars unchanged. Q1 prereg SHA is
written before scoring; Q2 temporary ledger is charged before Brier; Q3 bars
are byte-identical to the module rule; Q4 all arms use `walk_forward`; Q5 no
real AHEAD claim is made; Q6 calibration language only; Q7 the exhaustive
two-case construct is the denominator; Q8 premise remeasured module absent
before implementation.
