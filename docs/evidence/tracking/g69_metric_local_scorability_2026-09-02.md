# G69 metric-local harness scorable check

**Date:** 2026-09-02

**Scope:** contract and measurement only. This evidence changes no code,
threshold, contract clause, or verdict. It does not attempt a baseball
court-feet homography. The calibration strategy rules that solve out for the
dominant centre-field pitch view: its usable ground-plane references are
near-collinear on the pitch axis.

## Question and traced answer

The question is whether a clean `metric_local` row set is scorable by the
current harness, separately from any real baseball producer failure.

It is **not scorable today**. The trace is:

1. `tracking_harness.evaluate` calls `identify_tracking_schema`, then
   `normalize_tracking_frame`, before computing `n_frames`, coverage, bounds,
   jumps, or liveness.
2. For normalized rows, `normalize_tracking_frame` calls
   `_validate_coordinate_space`.
3. `_validate_coordinate_space` subtracts the row declarations from
   `SPORT_COORDINATE_SPACES[sport]`. `coordinate_provenance.py` contains only
   `court_feet` for `baseball`, `npb`, and `kbo`; `metric_local` is absent from
   both that map and `ALLOWED_COORDINATE_SPACES`.
4. Therefore the clean fixture fails before the metric calculations. This is a
   fail-closed rejection, not a silent scoring or a quality failure.

This falsifies the preferred outcome in the G69 spec: `metric_local` is not
already scorable, so baseball's coordinate-contract failure can be explained
by the contract itself. This does not prove that every real baseball report
has no additional producer issue.

## Constructed fixture and reproduction

The fixture is deliberately non-court data: `x` is a lateral local-feet
coordinate at the mound row and `y` is the source-image row. The declaration
is `coordinate_space=metric_local` and the calibration label is
`mound_lateral_px_per_ft`. This is exactly why it must never satisfy a
court-feet rectangle or a feet-per-second jump check.

- Fixture: `g69_metric_local/metric_local_clean_rows.csv`
- Capability declaration: `g69_metric_local/tracking_capability.json`
- Fixture audit: 90 rows; 30 frames; 60 player rows; 30 ball rows; zero
  duplicate `(frame, track_id)` keys.
- Fixture SHA-256:
  `9899EC90BAE4117F4C93439617E535FFFE977669FAEA94BBDD71B4B3E3445C1A`
- Run revision: `eb7eb5e04c8177e6e70482ba2a0dab53d07ed71b`
- Environment: `DESKTOP-VUIITL8`, 2026-09-02T14:34:44-05:00, Python 3.10.0,
  pandas 2.2.3.

The direct command shown in the harness docstring (`python
scripts/platformkit/tracking_harness.py ...`) cannot resolve the package
import in this worktree. The successful, equivalent package invocation was:

```text
python -m scripts.platformkit.tracking_harness docs/evidence/tracking/g69_metric_local/metric_local_clean_rows.csv baseball
```

It exited 1, as expected for this rejected fixture. Exact harness stdout is
also committed at `g69_metric_local/harness_metric_local_output.txt`:

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

The zero-valued fields are `_failed_report` placeholders, not evaluated
metrics. In particular, they are not evidence that the fixture had zero
coverage or a suspect liveness score.

## Metric-local applicability, metric by metric

For this baseball calibration, only lateral distance at the mound row is
metric. Depth remains image-row position. A metric that combines `x` and `y`
therefore has no common physical unit.

| Harness field or check | Metric-local status | Reason |
|---|---|---|
| `n_frames`, `n_unique_games`, `n_duplicate_frame_track_rows` | Meaningful as-is | Frame, game, and key counts do not use coordinates. |
| `ball_rows`, `ball_valid_pct`, `ball_valid`, `ball_valid_applicable`, `ball_telemetry_available`, `ball_telemetry_rule` | Meaningful as-is | These measure ball-row presence/capability, not ball location. |
| `coverage_pct` | Meaningful as-is | It counts frames meeting the required number of player IDs. |
| `det_per_frame` | Meaningful as-is | It is a detection count. |
| `median_track_len` | Meaningful as-is | It is track-ID persistence in frames. |
| `insufficient_data` | Meaningful as-is | It is the fixed frame-count flag (`n_frames < 30`). |
| `source_resolution`, `source_frame_rate`, `sampling_interval_s`, `sampling_interval_reason` | Meaningful as-is, informational | They are producer metadata; they do not validate surface geometry. |
| `zero_step_share` | Meaningful as-is only as exact repeated-output diagnostic | A zero vector means the producer repeated both reported coordinates. It is not a physical speed or distance claim. |
| `oob_pct` and `ball_in_bounds_pct` | Not meaningful | The baseball bounds rectangle is a court-feet rectangle. A mound-row local scale defines no such rectangle. |
| `jump_p95` and `jump_p95_ft_per_s` | Not meaningful | Euclidean steps combine lateral local feet with image-row pixels, so neither the current foot bar nor its per-second rendering has a physical unit. |
| `median_step_distance` | Not meaningful | Same mixed-unit Euclidean-distance problem. |
| `distinct_position_ratio` | Not meaningful | It rounds and compares coordinate pairs; its result depends on arbitrary mixed-axis representation and resolution. |
| `stationary_track_share` | Not meaningful | It is derived from cumulative Euclidean step distances. |
| `liveness_verdict` | Not meaningful as a composite | It includes the spatial liveness fields above. A future local profile may retain an explicitly named repeated-output diagnostic, but not this aggregate. |
| `passed`, `verdict`, `failures`, `self_consistency_only` | Not meaningful under the current aggregate | They summarize a full court-feet gate and, today, the coordinate rejection. A local-only profile needs an explicitly scoped result label. |
| `sport`, `config_version`, `n_frames`, `n_unique_games`, `ball_rows` in `QualityReport` | Meaningful as labels/counts | They carry identity or non-spatial counts; they do not establish a coordinate claim. |

`coverage_pct` is consequently the requested example of a surviving tracking
metric. The current feet-valued jump bar and court-rectangle OOB checks do not
survive.

## Smallest proposed contract change (not implemented)

Add one **additive, space-scoped local profile** to the coordinate contract:

1. Define `metric_local` as a distinct coordinate-space token and permit it
   only for baseball/NPB/KBO rows that carry the domain's validated local-scale
   declaration.
2. When that token is declared, run only the meaningful-as-is fields listed
   above. Mark all spatial fields `not_applicable`, rather than zero or pass.
   Emit an additive result label such as `PASS_METRIC_LOCAL` or
   `FAIL_METRIC_LOCAL`; it must never be rendered as a court-feet pass.
3. Keep the existing court-feet profile, thresholds, and rung requirement
   unchanged for every sport that can produce a per-frame court transform.

This is the smallest complete change because adding the token alone would
still send local rows through OOB and feet-jump checks that have no unit, while
changing any court-feet threshold is neither needed nor permitted.

It cannot launder `image_px` into a court-feet claim: acceptance remains an
exact declaration match, never a range or magnitude inference. `image_px`
remains absent from the scorable local and court-feet profiles; there is no
cast, fallback, or promotion from `image_px` to `metric_local` or
`court_feet`. A `metric_local` result labels its coordinate scope and has null
court-spatial metrics, so it cannot assert court bounds, feet-valued jumps, or
a court-feet verdict. The existing `court_feet` branch and its rung remain
strictly separate.

## VERIFIER_CONTRACT self-check

**A7:** At write time, all evidence paths named in this memo exist:
`g69_metric_local/metric_local_clean_rows.csv`,
`g69_metric_local/tracking_capability.json`, and
`g69_metric_local/harness_metric_local_output.txt`. This memo names no
uncommitted external or pod-only path.

| Check | Self-check |
|---|---|
| B1 circular metric | No metric was computed after excluding failures; the fixture exhaustively contains all 90 constructed rows. |
| B2 non-additive schema | No schema/code change was made; the proposed additive token/profile is not implemented. |
| B3 fall-through loss | No gate was changed. The observed fail-closed rejection is reported, not bypassed. |
| B4 re-claim loop | No producer or claim state was changed. |
| B5 pre-verification deploy | No pod copy, deploy, daemon action, or restart occurred. |
| B6 orphans | No module was moved, retired, or edited. |
| B7 head-slice evidence | This is an exhaustive constructed fixture, not a selected head slice; the spec requires no eye check. |
| B8 self-fit as independent | No homography, residual, or fit was performed. |
| B9 degenerate denominator | Counts use all 30 constructed frames and all 90 rows; no recycled metric unit is used as a denominator. |
| B10 moved bar | No threshold, config, or gate value was edited. |

## NOT VERIFIED

- Whether every real baseball report has only this coordinate-contract cause;
  the clean fixture proves the contract blocks `metric_local`, not the absence
  of other real-producer defects.
- Whether the current baseball producer can emit the proposed local declaration
  with the required validated-scale evidence; this row changes no producer.
- Any tracking-quality result for real baseball footage. The fixture tests
  dispatch behavior only.
- The unmeasured high-home shot class. It is irrelevant to this local-profile
  proposal and no homography was attempted.
