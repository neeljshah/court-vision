# S304: S108 as-of feature guards

## Scope and preregistration

This is the exhaustive local construct required by `docs/evidence/tracking/specs/S304_spec.md`, checked against sections B and Q1-Q9 of `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It opens no corpus file, evaluator, pod, ledger, or register. The preregistration is `docs/evidence/harness/S304_s108_features_asof_guards_2026-09-04_prereg.md`; its pre-test seal is `38e294679e91920b894ce28b345b1d6eff65277743e111cbfd4cc125d9eb9a70`.

The seal is SHA-256 of the UTF-8 bytes above `Seal-SHA256:`, after CRLF-to-LF normalization. The normalized prefix is 2,676 bytes. Recomputing it from the preregistration file yielded the embedded seal before the test was first run.

## Premise

The direct-importer census over every `tests/**/*.py` file returned `NO_DIRECT_IMPORTER_TESTS`. The public behavior locations are `asof_sources` at `scripts/platformkit/eval_gate/s108_features.py:28`, `_add` at `scripts/platformkit/eval_gate/s108_features.py:35`, and `build` at `scripts/platformkit/eval_gate/s108_features.py:40`.

## Construct result

| Behavior | Exact fixture assertion | Result |
| --- | --- | --- |
| Name refusal before value access | `home_final` is `[0.0, 1.0]`, raises the `pd.to_numeric` guard if read, is refused, and `asof_rating` is `[10.0, 20.0]` in `X` | PASS |
| Duplicate-key source refusal | Duplicate `event_id` source containing `asof_rating` and `asof_speed` is refused whole; neither column enters `X` | PASS |
| First source wins; second fills gaps | Sources `[1.0, NaN]` and `[9.0, 2.0]` assemble as `[1.0, 2.0]` | PASS |
| Missingness indicator | `[1.0, NaN]` should retain `asof_rating`, add `[0.0, 1.0]` in `asof_rating__isna`, and report `n_missing_cols == 1` | XFAIL: NEW GAP |

The fourth assertion is a strict expected failure, not a skip. Current `build` drops a source with only one finite value as `constant or empty on the screen side` before its missingness indicator is constructed. The acceptance bar is assertion coverage and it is met: all 4 behaviors are asserted with their fixed values; the measured functional outcome is 3 passed and 1 strict xfail. Verdict: ACCEPT WITH CORRECTIONS.

## Reproduction and identity

Test line: `python -m pytest tests/platformkit/eval_gate/test_s108_features.py -q`

Observed output: `3 passed, 1 xfailed in 3.91s`.

`scripts/platformkit/eval_gate/s108_features.py` SHA-256 is `b59eea4051a5232bc44612c73540cdd127e2bbd84bce980ad771265a30388c0e`, identical to the preregistration baseline. The additive test is `tests/platformkit/eval_gate/test_s108_features.py`.

No delta or predictive comparison was calculated. If a later comparison is added, delta is baseline loss minus candidate loss; positive means the candidate has lower loss. There are no evaluator records, losses, scored ticks, corpus inputs, pod jobs, or ledger charges in this construct.

## Contract self-check

B1-B10: no metric filtering, schema mutation, fall-through route, claim loop, deploy, moved module, sampled head slice, self-fit result, recycled denominator, or changed bar. Q1 holds through the pre-test LF-normalized preregistration seal. Q2, Q4, Q5, and Q9 are not applicable because this is not a charged or scored comparison. Q3 holds: the bar remains 4/4. Q6 holds: this memo uses calibration-only language. Q7 holds: n = 4 is an exhaustive construct. Q8 holds: the importer census was re-measured before the test was created.

## NOT VERIFIED

- The missingness-indicator behavior is not implemented for the fixed one-finite-value fixture; it is the named NEW GAP.
- Candidate commit SHA is 8a8b8a38d883d53b5bf6a8356fe333a6357a9ea2; the landing into master is an explicit-path extraction.
- The verifier reran this test against committed candidate bytes (3 passed, 1 xfailed); see docs/evidence/harness/S304_VERIFY_2026-09-07.md:8.
