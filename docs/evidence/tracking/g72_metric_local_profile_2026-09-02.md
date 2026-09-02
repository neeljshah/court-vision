# G72 metric-local profile

**Date:** 2026-09-02

## Result

ACCEPT. The additive baseball-family metric_local profile now evaluates only the G69 non-spatial metrics. The G69 fixture produces PASS_METRIC_LOCAL with passed=false; it is not a court-feet pass. Ten pre-change court-feet reports replay byte-identically, including every report field.

- Court-feet replay n: 10. all_byte_identical=true; all_fields_identical=true.
- Metric-local fixture n: 1 constructed 90-row / 30-frame report.
- Test: python -m pytest scripts/platformkit/test_tracking_harness_g72_metric_local.py -q -> 2 passed.
- No producer, baseball adapter, historical baseball report, pod, daemon, or feature flag was changed.

## Implemented scope

The coordinate declaration is exact. metric_local is accepted only for baseball, NPB, and KBO with calibration=mound_lateral_px_per_ft. The harness dispatches only an exact coordinate_space=metric_local declaration to the local profile. image_px is in neither profile: no cast, range inference, fallback, or promotion exists.

The local profile evaluates only frame/game/duplicate counts, ball presence and capability, coverage, detections per frame, track persistence, sample sufficiency, source/sampling metadata, and exact paired-coordinate zero_step_share as a repeated-output diagnostic. It does not compute a Euclidean local step or liveness composite.

Every spatial field is the literal string not_applicable: oob_pct, ball_in_bounds_pct, jump_p95, jump_p95_ft_per_s, median_step_distance, distinct_position_ratio, stationary_track_share, and liveness_verdict. They are neither zero nor null.

## Court-feet replay

The immutable pre-change snapshot is [court_feet_before_reports.json](g72_metric_local_profile/court_feet_before_reports.json). It holds all ten report field maps plus the pre-change SHA-256 for each full QualityReport.to_json() byte sequence. The changed harness rebuilds each fixture, diffs every key/value, and compares the complete JSON SHA-256. The replay output is [court_feet_replay.json](g72_metric_local_profile/court_feet_replay.json).

Before court-feet report block (basketball_good; SHA-256 f9c3efd6964350647aff32cafe917ad653b1461e6b9d48db978de84e70a9c7f1):

```json
{
  "sport": "basketball",
  "config_version": "2026-09-01-v1",
  "n_frames": 60,
  "n_unique_games": 1,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 60,
  "coverage_pct": 1.0,
  "det_per_frame": 7.0,
  "median_track_len": 60.0,
  "ball_valid_pct": 1.0,
  "ball_valid": "evaluated",
  "ball_valid_applicable": true,
  "ball_telemetry_available": null,
  "ball_telemetry_rule": "unknown_no_sidecar",
  "jump_p95": 0.02,
  "oob_pct": 0.0,
  "zero_step_share": 0.0,
  "median_step_distance": 0.02,
  "distinct_position_ratio": 0.3889,
  "stationary_track_share": 0.0,
  "liveness_verdict": "LIVE",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": true,
  "verdict": "PASS",
  "failures": [],
  "ball_in_bounds_pct": 1.0,
  "insufficient_data": false,
  "sampling_interval_s": null,
  "sampling_interval_reason": "source metadata unavailable",
  "jump_p95_ft_per_s": null
}
```

After court-feet report block (same SHA-256):

```json
{
  "sport": "basketball",
  "config_version": "2026-09-01-v1",
  "n_frames": 60,
  "n_unique_games": 1,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 60,
  "coverage_pct": 1.0,
  "det_per_frame": 7.0,
  "median_track_len": 60.0,
  "ball_valid_pct": 1.0,
  "ball_valid": "evaluated",
  "ball_valid_applicable": true,
  "ball_telemetry_available": null,
  "ball_telemetry_rule": "unknown_no_sidecar",
  "jump_p95": 0.02,
  "oob_pct": 0.0,
  "zero_step_share": 0.0,
  "median_step_distance": 0.02,
  "distinct_position_ratio": 0.3889,
  "stationary_track_share": 0.0,
  "liveness_verdict": "LIVE",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": true,
  "verdict": "PASS",
  "failures": [],
  "ball_in_bounds_pct": 1.0,
  "insufficient_data": false,
  "sampling_interval_s": null,
  "sampling_interval_reason": "source metadata unavailable",
  "jump_p95_ft_per_s": null
}
```

## Metric-local fixture

Before, the G69 fixture failed before metric calculation; its numeric zeros were _failed_report placeholders:

```json
{
  "sport": "baseball",
  "config_version": "2026-09-01-v1",
  "n_frames": 0,
  "n_unique_games": 0,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 0,
  "coverage_pct": 0.0,
  "det_per_frame": 0.0,
  "median_track_len": 0.0,
  "ball_valid_pct": 0.0,
  "ball_valid": "not_evaluated",
  "ball_valid_applicable": true,
  "ball_telemetry_available": true,
  "ball_telemetry_rule": "producer_declaration",
  "jump_p95": 0.0,
  "oob_pct": 0.0,
  "zero_step_share": 0.0,
  "median_step_distance": 0.0,
  "distinct_position_ratio": 0.0,
  "stationary_track_share": 0.0,
  "liveness_verdict": "SUSPECT",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": false,
  "verdict": "FAIL",
  "failures": [
    "coordinate_contract: rows declare coordinate_space metric_local not accepted for sport baseball; a preserved detection corpus is never a scorable game"
  ],
  "ball_in_bounds_pct": null,
  "insufficient_data": false,
  "sampling_interval_s": null,
  "sampling_interval_reason": "source metadata unavailable",
  "jump_p95_ft_per_s": null
}
```

After, the same fixture has real non-spatial values, explicit non-applicability for spatial fields, and a scoped result:

```json
{
  "sport": "baseball",
  "config_version": "2026-09-01-v1",
  "n_frames": 30,
  "n_unique_games": 1,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 30,
  "coverage_pct": 1.0,
  "det_per_frame": 3.0,
  "median_track_len": 30.0,
  "ball_valid_pct": 1.0,
  "ball_valid": "evaluated",
  "ball_valid_applicable": true,
  "ball_telemetry_available": true,
  "ball_telemetry_rule": "producer_declaration",
  "jump_p95": "not_applicable",
  "oob_pct": "not_applicable",
  "zero_step_share": 0.0,
  "median_step_distance": "not_applicable",
  "distinct_position_ratio": "not_applicable",
  "stationary_track_share": "not_applicable",
  "liveness_verdict": "not_applicable",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": false,
  "verdict": "PASS_METRIC_LOCAL",
  "failures": [],
  "ball_in_bounds_pct": "not_applicable",
  "insufficient_data": false,
  "sampling_interval_s": null,
  "sampling_interval_reason": "source metadata unavailable",
  "jump_p95_ft_per_s": "not_applicable"
}
```

## Binding conditions

1. **Scoped results never count as court-feet passes.** The local profile always emits passed=false, even with PASS_METRIC_LOCAL. The test proves a normal court-feet report alone contributes to a boolean pass count when paired with the local scoped result. Reader audit found that tracking_brain.scorecard would put a future local report in games_scored, the pass-rate denominator, and metric summaries even though it cannot add it to the pass numerator. That mixed-scope summary defect is named as G73; it is not silently changed in this row.
2. **Spatial fields are not applicable.** The test asserts the literal not_applicable value for every G69 spatial field.
3. **Court-feet is untouched.** Ten varied court-feet reports across basketball, tennis, soccer, baseball, NPB, and football have no field or byte movement. No threshold or rung value changed.
4. **image_px remains rejected.** The test relabels the G69 rows image_px and asserts the unchanged coordinate-contract failure. No fallback exists.

## VERIFIER_CONTRACT self-check

**A7:** Every memo evidence path exists now: [before snapshots](g72_metric_local_profile/court_feet_before_reports.json), [replay](g72_metric_local_profile/court_feet_replay.json), [court block before](g72_metric_local_profile/court_feet_before_report.json), [court block after](g72_metric_local_profile/court_feet_after_report.json), [local block before](g72_metric_local_profile/metric_local_before_report.json), [local block after](g72_metric_local_profile/metric_local_after_report.json), and [test output](g72_metric_local_profile/test_output.txt).

| Check | Self-check |
|---|---|
| B1 circular metric | No rows are excluded. The local fixture contains all 90 constructed rows; court replay fixtures are exhaustive. |
| B2 non-additive schema | No existing report field is added, removed, or renamed. Court-feet JSON bytes are unchanged; only new declaration/profile behavior and evidence/test files are added. |
| B3 fall-through loss | Exact unsupported declarations, including image_px, still fail closed. Metric-local dispatch requires the exact permitted declaration and calibration. |
| B4 re-claim loop | No queue, claim, producer, or failure-path state changed. |
| B5 pre-verification deploy | No pod copy, deployment, daemon action, restart, or kill was performed. |
| B6 orphans | No module was moved or retired. The new profile is imported by the harness and covered by the new per-file test. |
| B7 head-slice evidence | The G69 fixture is exhaustively constructed; the ten replay fixtures are an explicit complete fixed set, not a head slice. |
| B8 self-fit as independent | No fit, homography, residual, or accuracy assertion is made. |
| B9 degenerate denominator | Counts use all rows and distinct frames in each fixture; no recycled metric is used as a denominator. |
| B10 moved bar | No existing threshold, court-feet rule, or rung value changed. |

## NOT VERIFIED

- Whether the current baseball producer can emit metric_local with the required validated local-scale declaration.
- Any tracking-quality result for real baseball footage.
- Whether historical baseball rows should be rescored or a baseball producer should be switched; both are explicitly out of scope.
- Any pod deployment; the verifier owns landing code on the pod.
