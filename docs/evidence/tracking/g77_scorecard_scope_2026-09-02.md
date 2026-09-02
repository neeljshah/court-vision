# G77 scorecard coordinate-profile scope

## Result

ACCEPT. The scorecard now groups reports by coordinate profile before counting,
computing pass rates, or calculating medians. A court_feet headline is explicitly
labelled and its denominator contains court_feet reports only. metric_local
reports remain visible in their own labelled scope; they are not dropped.

## Reproduced defect

The mixed input is [court_feet_pass.json](g77_scorecard_scope/mixed_before/reports/baseball/court_feet_pass.json)
plus [metric_local.json](g77_scorecard_scope/mixed_before/reports/baseball/metric_local.json).
The local report has `verdict=PASS_METRIC_LOCAL`, `passed=false`, and G72's
literal `not_applicable` spatial fields. The pre-change scorecard was executed
from the committed parent version of `tracking_brain.py` against those exact
two reports. Its output is [mixed_before_scorecard.json](g77_scorecard_scope/mixed_before_scorecard.json):
`games_scored=2` and an unlabelled `pass_rate=0.5`, even though only the
court_feet report could contribute to the numerator. Its coverage and
ball_valid medians also blended both profiles.

After, the same mixed input produces [mixed_after_scorecard.json](g77_scorecard_scope/mixed_after_scorecard.json).
The labelled court_feet headline is `games_scored=1`, `pass_rate=1.0`, exactly
the court_feet-only result. The labelled metric_local scope remains present with
`games_scored=1`, `pass_rate=0.0`, and medians only for its applicable coverage
and ball_valid metrics. `main()` renders a PROFILE column for every dashboard
headline. The resolver now carries both `coordinate_profile` and
`coordinate_profiles` so its wrapped scorecard cannot hide the scoped result.

## Constructed cases

All four committed inputs are in [constructed_inputs.json](g77_scorecard_scope/constructed_inputs.json);
their complete outputs and SHA-256 values are in [constructed_outputs.json](g77_scorecard_scope/constructed_outputs.json).

| Case | Produced |
|---|---|
| court_feet_only | Legacy court_feet fields: 1 game, labelled by the dashboard PROFILE column, rate 1.0. |
| metric_local_only | Labelled metric_local scope: 1 game, rate 0.0, coverage and ball_valid medians only. |
| mixed | Labelled court_feet headline: 1 game and rate 1.0; nested labelled metric_local: 1 game and rate 0.0. |
| empty | Legacy empty card: 0 games, rate 0.0, no metrics, and no headline to label. |

For mixed and metric_local-only cards, top-level legacy fields are retained as
backward-compatible aliases and paired with `coordinate_profile`; the complete
per-profile values are under `coordinate_profiles`. Court-feet-only output is
kept byte-identical for existing callers.

## Court-feet replay

Five existing G72 court-feet `QualityReport` snapshots replayed through the
old parent implementation and the changed implementation. Every sorted JSON
scorecard byte sequence had identical SHA-256 before and after; evidence is in
[court_feet_replay.json](g77_scorecard_scope/court_feet_replay.json).

Covered paths: legacy no-profile to court_feet inference; numeric values for
coverage, ball_valid, jump_p95, and oob; pass and fail states; basketball good,
frozen, and out-of-bounds modes; and tennis and baseball threshold maps.

Not covered by this five-input corpus: a pre-existing multi-report aggregation,
the 10-report trend branch, malformed-report skipping, explicit
`coordinate_profile` or `coordinate_space` declarations, and a
`FAIL_METRIC_LOCAL` verdict. The four constructed cases separately cover the
metric_local inference and mixed-profile aggregation, but not those other
unexercised paths.

## Test

Exactly one new per-file test was added and run:
`python -m pytest scripts/platformkit/test_tracking_brain_g77_scorecard_scope.py -q`.
It covers all four constructed cases and asserts the five court-feet replay
SHA-256 values. Output: [test_output.txt](g77_scorecard_scope/test_output.txt).

## VERIFIER_CONTRACT self-check

**A7:** All evidence paths named in this memo exist: the two mixed input
reports, [before output](g77_scorecard_scope/mixed_before_scorecard.json),
[after output](g77_scorecard_scope/mixed_after_scorecard.json),
[constructed inputs](g77_scorecard_scope/constructed_inputs.json),
[constructed outputs](g77_scorecard_scope/constructed_outputs.json),
[replay](g77_scorecard_scope/court_feet_replay.json), and
[test output](g77_scorecard_scope/test_output.txt).

| Check | Self-check |
|---|---|
| B1 circular metric | No report is excluded. Each profile keeps all of its reports and names the scope used for each denominator. |
| B2 non-additive schema | Existing scorecard fields remain as labelled-profile aliases on mixed/local cards; court-feet-only bytes are unchanged. `main`, `next_actions`, and the resolver were checked as readers. |
| B3 fall-through loss | No harness or report gate changed. metric_local reports remain in their own scorecard scope. |
| B4 re-claim loop | No queue, claim, or failure-path state changed. |
| B5 pre-verification deploy | No deploy, copy, SCP, process kill, or feature flag action occurred. |
| B6 orphans | No module moved or retired. The new test imports the scorecard by its full package path. |
| B7 head-slice evidence | The constructed cases are exhaustive by enumeration; the five named replay fixtures are an explicit stated corpus, with limits disclosed above. |
| B8 self-fit as independent | No fitted model, residual, or independent-performance claim is made. |
| B9 degenerate denominator | Each denominator is the count of reports in exactly one named coordinate profile. |
| B10 moved bar | No threshold, harness rung, or report field threshold changed. |

## NOT VERIFIED

- Any real baseball producer emitting metric_local reports into the live report tree.
- Multi-report trend behavior for any profile.
- Explicit producer serialization of `coordinate_profile` or `coordinate_space` on a QualityReport.
- Any pod deployment or service behavior; none was attempted.
