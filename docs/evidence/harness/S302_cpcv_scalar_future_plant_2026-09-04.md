# S302 Scalar CPCV Future Plant Construct

## Scope and preregistration

This is the one-case S302 construct specified in
`docs/evidence/tracking/specs/S302_spec.md`. It tests the scalar route
`scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate` with four frozen
groups, one test group, and `embargo_days=1`. It is not a production
calibration comparison.

The preregistration is
`docs/evidence/harness/S302_prereg_2026-09-04.md`. Its embedded seal is
`53f2d19f50430674e1c190d46da4440c5d1d693b460622a1c8f3f4cafa6c9094`.
The seal is SHA-256 over the LF-normalized bytes before the `Seal-SHA256:`
line (CRLF replaced with LF). It was recomputed from the staged bytes
(`git show :<path>`) and from the committed bytes (`git show HEAD:<path>`) of
the prereg-only commit and matched both. The focused test independently
performs the same normalization and hash check at
`tests/platformkit/eval_gate/test_cpcv_scalar_future_plant.py:49`.

## Premise re-measurement

The pre-existing scalar-engine future-row test is
`scripts/platformkit/eval_gate/test_cpcv_engine.py:112-130`. It captures train
identifiers and asserts `trains["g0"] == {"g3"}`. Its predictor returns 0.5;
there is no assertion that a future planted label changes a target probability.
That confirms the stated before condition.

## Construct and result

The added test is
`tests/platformkit/eval_gate/test_cpcv_scalar_future_plant.py:57`. It contains
one target state, `g0` at `2024-07-01T19:00:00`, and one same-team `AAA` plant,
`g2` at `2024-07-03T18:00:00` (+47 hours). The planted feature is
`label_revealing_future_plant`. The real arm uses the unmodified evaluator.
The control uses a test-fixture monkeypatch only: `_blocked_indices` returns an
empty set. No evaluator default or production route was changed.

The scoring rerun, executed after the prereg-only commit, recorded:

- Plant absent from real target train: `True` (`["g3"]`).
- Real-purge target probability: `0.5`.
- Disabled-purge control target probability: `0.9` (`["g1", "g2", "g3"]`).
- Control minus real difference: `0.4`.
- Enumeration: one planted case and one control, exhaustive by construction.

The machine output is
`docs/evidence/harness/S302_cpcv_scalar_future_plant_2026-09-04.json`; it
archives the paired target probabilities, target identifier, both target train
sets, and the exercised engine hash. No loss CI is claimed by this construct.

## Identity and self-check

`scripts/platformkit/eval_gate/cpcv_engine.py` SHA-256 before and after was
`5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5` over the
local CRLF working-tree bytes the test hashes, which is git blob
`9b152531852a9fd435be82ca69584929fe718da9bd1554ad293cb4cd11717c01` and equals
master. `git diff --quiet -- scripts/platformkit/eval_gate/cpcv_engine.py`
confirmed it is byte-identical. Purge and embargo constants were not touched.
The only focused test run was `python -m pytest -q -s -p no:cacheprovider
tests/platformkit/eval_gate/test_cpcv_scalar_future_plant.py` in worktree
a20; it passed 2 tests in 2.33 seconds. The run is local by construction; no
pod job produced the committed evidence.

## NOT VERIFIED

- The verifier must rerun the one test in master after explicit-path landing.
- No full test suite was run.
