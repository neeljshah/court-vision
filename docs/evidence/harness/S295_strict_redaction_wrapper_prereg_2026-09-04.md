# S295 Strict Redaction Wrapper Preregistration

## Scope

This preregistration covers only the local S295 construct. No data store is opened. The input is a generated, eight-state fixture with one unique evaluator state per scored tick, a declared probability feature, vintage timestamps, labels, and separately planted raw settled labels.

## Fixed comparison and evaluator route

The protected arm serializes only the declared `p` feature and the declarative `feature_probability` predictor specification into a fresh subprocess. That subprocess invokes `walk_forward` or `cpcv_evaluate` from `scripts/platformkit/eval_gate/`. The walk-forward route retains its configured purge and embargo. The CPCV route uses `embargo_days=1`, which is nonzero and symmetric, plus its shared purge.

The unprotected before-condition invokes `walk_forward` with the default false redaction and a closure over the raw planted settled-label array. It is expected to produce a lower Brier loss than the declared-feature valid fixture; if it cannot alter loss, S295 is FALSIFIED at its stated limit.

## Fixed attacks and acceptance

The six exhaustive attacks are the Cartesian product of `walk_forward` and `cpcv_evaluate` with three fixed callback forms: closure, module-global lookup, and default-argument lookup. Each attack must be rejected before scoring because the protected interface accepts a declarative predictor specification, not a callback. The valid declarative fixture must replay its shared-evaluator Brier loss with absolute error at most `1e-12`.

The primary metric is planted leak detections: `6/6` required, with a Wilson 95 percent interval reported. The secondary metric is valid-caller Brier replay error. All archived losses are derived only from shared-evaluator records. The fixed construct is exhaustive (`n=6`), so no sampling rail applies.

For every loss delta, improvement = baseline loss minus candidate loss; positive = candidate better. The frozen calibration comparison bar is `+0.004`; S295 makes no calibration-ahead claim, and a valid-fixture replay delta is expected to be zero.

## Durable records and environment

The JSON artifact will retain the generated declared input payload, every rejection exception, every shared-evaluator record used in the valid replay, per-record Brier losses, mode, stable tick key, state count, and RSS before and after the subprocess. The local machine is used because this is a tiny generated construct and no pod data or deployment is needed.

Seal SHA-256: 6e4a9b70c8425d661678c1d3620cc6d7346a511313d943e2be4ec7d7d1478e75
