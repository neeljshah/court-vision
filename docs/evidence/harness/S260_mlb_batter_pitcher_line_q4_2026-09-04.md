# S260 MLB Batter-Pitcher Line Q4

## Verdict

CLOSED AT LIMIT. The shared evaluator has no supported continuous-distribution
callback path. Therefore the required all-cluster CRPS and pinball comparison
cannot be scored through `walk_forward` or `cpcv_evaluate` without a new shared
evaluator capability. No replacement S260 row or cluster CSV was generated.

## Sealed preregistration

The preregistration is
`docs/evidence/harness/S260_attempt1c_seal_prereg_2026-09-04.md`, committed in
`e59d75b3618837b6b66981e2f29e2bc8f4280a15`. Its committed LF prefix above the
seal line is 3,212 bytes and its verified SHA-256 seal is
`1A340E5D209B3F5A4AADB237008D0B994CC71F6061821DDF5B144A8BCAED9B77`.
The full committed artifact SHA-256 is
`817FE0DD17DCEEFF24A55B8A435A874DDC42E3DE0F182CF65EC601A31825D685`.
The seal predates the fresh baseline reproduction and capability test.

## Premise and input identity

The recovered scorer is
`scripts/platformkit/mlb_batter_pitcher_line_dist.py`. Its
`score_naive_clusters` function constructs a local chronological date loop and
does not call either contract evaluator. The immutable input opened for the
informational baseline reproduction was
`data/frontend/prop_history_corpus_mlb.jsonl`: 1,283,918 bytes, SHA-256
`97A6EBD51C89C456588119C39128099F6492185D414F49A26031A2C10A6C1D0D`,
resolution not applicable (JSONL).

## Informational custom-loop reproduction

This table reproduces the archived S244 custom-loop baseline only. It is not a
contract-route result and does not satisfy the S260 acceptance bar.

| Calibration quantity | Archived custom loop | Reproduced custom loop | Absolute difference |
|---|---:|---:|---:|
| CRPS | 0.5098297809224259 | 0.5098297809224259 | 0.0 |
| Pinball q10 | 0.08655308369594088 | 0.08655308369594088 | 0.0 |
| Pinball q50 | 0.37323931073931077 | 0.37323931073931077 | 0.0 |
| Pinball q90 | 0.2013804110232682 | 0.2013804110232682 | 0.0 |

The reproduction scored all 777 date clusters and all 3,000 rows. It retained
all 48 named cold-start rows at the fixed point mass 0.0. No denominator was
reduced.

## NOT VERIFIED

No contract-route CRPS or pinball quantity is verified. The fresh reproduction
is informational custom-loop calibration only, and the shared evaluator was
not changed in this pass.

## Exact interface limitation

`scripts/platformkit/eval_gate/walkforward.py:walk_forward` requires
`predict_fn(train_states, test_state, select_inside) -> float`, validates that
the returned value lies in [0, 1], and stores only scalar `p_model`, optional
`p_close`, and integer `y`. Its public result has no field for empirical
samples, forecast quantiles, CRPS, pinball quantities, or a post-prediction
scoring callback.

`scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate` exposes the same
scalar `Predictor` return contract, applies the same [0, 1] validation, and
returns the same binary-oriented record shape plus split diagnostics. It also
has no distribution payload or scoring-callback argument. A callback returning
an empirical sample vector raises `TypeError` at the scalar range validation;
the focused test documents this behavior for both public routes.

The smallest additive change is a backwards-compatible distribution-scoring
entry point in the shared evaluator: accept a typed empirical forecast (sample
sequence) from a predictor, call a supplied post-prediction score callback with
that forecast and the settled continuous outcome, and append the callback's
named quantities to the returned record. The predictor must continue to receive
only the redacted test view; the settled outcome belongs only to the evaluator
after prediction. Existing scalar binary callers remain unchanged. That single
capability would let S260 attach CRPS and q10/q50/q90 scoring to the contract
fold route while retaining its purge and symmetric embargo controls.

## Verification and scope checks

The focused test is
`tests/platformkit/test_s260_mlb_batter_pitcher_line_q4.py`. No input schema
was changed, no row was excluded, no feature flag was changed, and no pod action
occurred. This memo and the sealed preregistration are the only S260 evidence
artifacts; both paths exist in this worktree and are below 50 MB.
