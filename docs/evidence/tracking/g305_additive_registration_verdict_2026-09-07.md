# G305 additive registration verdict - construct complete

Status: NOT VALIDATED. This is an entirely local synthetic additive construct
for the current `2026-09-01-v1` harness. It scores no real registration result,
changes no production default, and writes no real production ledger row.

## Binding readings

1. `scripts/platformkit/tracking_harness.py:272` is
   `"""Return self-consistency health metrics for a recognized tracking table."""`.
   At line 395, the constructed report receives `frame_rate, True, passed,
   verdict, failures,`; `self_consistency_only=True` therefore survives a pass.
2. Lines 25-28 retain bounds `(0, 94, 0, 50)`, six players, attempted-frame
   coverage `0.60`, OOB `0.05`, modal jump `6.0`, and median track length `3.0`.
   Ball handling is at 332, 366, and 375; under-30-frame handling is at 257-262
   and 405-408.
3. `domains/basketball/tracking/geometry.py:28-29` checks `x <= 50, y <= 94`;
   `tracking_harness.py:25` checks `x <= 94, y <= 50`.
4. The current raw harness SHA-256 is
   `c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95`.
   Active lines 353-354 include attempted-frame coverage and median track
   length. The premise-4 WT reading is FALSIFIED in this tree: this worktree
   harness is byte-identical to master at that same SHA-256, so there is no
   second file to diff. The verifier correction establishes
   that this condition is not part of the limiting ACCEPTANCE before-condition.

## Reflection result

The canonical table has 30 pre-inference attempted frames in a sealed manifest
(`b1ac28da603c0bfee91b59a30280a2b861ab0e781aec366949a2fdad61b64b96`), six
player IDs and a ball row per frame, and `court_feet` coordinates. Reflection
changes every x only by `x' = 94 - x`; y, frame, timestamp, class, and ID remain.

| Harness run | verdict | passed | failures | self_consistency_only |
| --- | --- | --- | --- | --- |
| Original canonical table | PASS | true | [] | true |
| Reflected x' = 94 - x table | PASS | true | [] | true |

This documents current behavior only. It does not modify the harness or move a
threshold.

## Axis convention boundary

`geometry_to_harness_point(width_x, length_y)` returns `(length_x, width_y)`;
`harness_to_geometry_point(length_x, width_y)` is its inverse. The corresponding
directional homography functions left-compose the output with the explicit axis
swap. Every round trip is exact to at most 1e-9 ft.

| Named point | Geometry (x <= 50, y <= 94) | Harness (x <= 94, y <= 50) | Reverse |
| --- | --- | --- | --- |
| near_left_corner | (0.0, 0.0) | (0.0, 0.0) | (0.0, 0.0) |
| near_right_corner | (50.0, 0.0) | (0.0, 50.0) | (50.0, 0.0) |
| far_left_corner | (0.0, 94.0) | (94.0, 0.0) | (0.0, 94.0) |
| far_right_corner | (50.0, 94.0) | (94.0, 50.0) | (50.0, 94.0) |
| asymmetric_interior_point | (13.25, 72.5) | (72.5, 13.25) | (13.25, 72.5) |

The exercised homography `((1.2, 0.1, 4.0), (0.05, 0.9, 8.0),
(0.001, 0.002, 1.0))` reproduces exactly after geometry-to-harness-to-geometry.

## Worked additive record (full)

The original verdict's raw JSON string and parsed record are both retained. The
following is the emitted record in full.

```json
{
  "ball_tracking_passed": true,
  "harness_verdict_json": "{\n  \"sport\": \"basketball\",\n  \"config_version\": \"2026-09-01-v1\",\n  \"n_frames\": 30,\n  \"n_unique_games\": 1,\n  \"n_duplicate_frame_track_rows\": 0,\n  \"ball_rows\": 30,\n  \"coverage_pct\": 1.0,\n  \"det_per_frame\": 7.0,\n  \"median_track_len\": 30.0,\n  \"ball_valid_pct\": 1.0,\n  \"ball_valid\": \"evaluated\",\n  \"ball_valid_applicable\": true,\n  \"ball_telemetry_available\": null,\n  \"ball_telemetry_rule\": \"unknown_no_sidecar\",\n  \"jump_p95\": 0.02,\n  \"jump_max\": 0.02,\n  \"oob_pct\": 0.0,\n  \"zero_step_share\": 0.0,\n  \"median_step_distance\": 0.02,\n  \"distinct_position_ratio\": 1.0,\n  \"stationary_track_share\": 0.0,\n  \"liveness_verdict\": \"LIVE\",\n  \"source_resolution\": null,\n  \"source_frame_rate\": null,\n  \"self_consistency_only\": true,\n  \"passed\": true,\n  \"verdict\": \"PASS\",\n  \"failures\": [],\n  \"ball_in_bounds_pct\": 1.0,\n  \"insufficient_data\": false,\n  \"sampling_interval_s\": null,\n  \"sampling_interval_reason\": \"source metadata unavailable\",\n  \"jump_p95_ft_per_s\": null,\n  \"jump_max_modal_stride_frames\": 1,\n  \"attempted_frames\": 30,\n  \"coverage_attempted_frames_pct\": 1.0,\n  \"ball_valid_attempted_frames_pct\": 1.0,\n  \"coverage_pct_denominator\": \"emitted_frames\",\n  \"ball_valid_pct_denominator\": \"emitted_frames\",\n  \"coverage_attempted_frames_pct_denominator\": \"attempted_frames\",\n  \"ball_valid_attempted_frames_pct_denominator\": \"attempted_frames\"\n}",
  "harness_verdict_record": {
    "attempted_frames": 30,
    "ball_in_bounds_pct": 1.0,
    "ball_rows": 30,
    "ball_telemetry_available": null,
    "ball_telemetry_rule": "unknown_no_sidecar",
    "ball_valid": "evaluated",
    "ball_valid_applicable": true,
    "ball_valid_attempted_frames_pct": 1.0,
    "ball_valid_attempted_frames_pct_denominator": "attempted_frames",
    "ball_valid_pct": 1.0,
    "ball_valid_pct_denominator": "emitted_frames",
    "config_version": "2026-09-01-v1",
    "coverage_attempted_frames_pct": 1.0,
    "coverage_attempted_frames_pct_denominator": "attempted_frames",
    "coverage_pct": 1.0,
    "coverage_pct_denominator": "emitted_frames",
    "det_per_frame": 7.0,
    "distinct_position_ratio": 1.0,
    "failures": [],
    "insufficient_data": false,
    "jump_max": 0.02,
    "jump_max_modal_stride_frames": 1,
    "jump_p95": 0.02,
    "jump_p95_ft_per_s": null,
    "liveness_verdict": "LIVE",
    "median_step_distance": 0.02,
    "median_track_len": 30.0,
    "n_duplicate_frame_track_rows": 0,
    "n_frames": 30,
    "n_unique_games": 1,
    "oob_pct": 0.0,
    "passed": true,
    "sampling_interval_reason": "source metadata unavailable",
    "sampling_interval_s": null,
    "self_consistency_only": true,
    "source_frame_rate": null,
    "source_resolution": null,
    "sport": "basketball",
    "stationary_track_share": 0.0,
    "verdict": "PASS",
    "zero_step_share": 0.0
  },
  "hashes": {
    "harness_sha256": "c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95",
    "liveness_sha256": "440a91ad65a82130e2f452c52a49eab9911e1a2b2e539028f2a72b69785263ac",
    "producer_sha256": "1675bae219cec12c207a80af6c2eaface2473e219be56b59bda8251e6e7d9086",
    "schema_sha256": "20b930c307db521d77bfbce1986c14b438641c081481ea1ca22230fed4cb2347"
  },
  "lf_normalized_hashes": {
    "harness_sha256": "59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d",
    "liveness_sha256": "50839e08fbb06112f77a0cc03e80b248dc54cbe1ee53e164fca244256ba150f0",
    "producer_sha256": "1675bae219cec12c207a80af6c2eaface2473e219be56b59bda8251e6e7d9086",
    "schema_sha256": "72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e"
  },
  "mode": {
    "attempted_frame_denominator": "all 30 pre-inference attempted frames",
    "attempted_frame_manifest": {
      "payload": {"denominator": "pre_inference_attempted_frames", "frame_ids": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29]},
      "sha256": "b1ac28da603c0bfee91b59a30280a2b861ab0e781aec366949a2fdad61b64b96"
    },
    "camera_shot_eligibility": "not_measured_synthetic_construct",
    "court_convention": "harness_x_94_y_50_ft",
    "execution": "offline",
    "manual_inputs": false
  },
  "player_tracking_passed": true,
  "q": null,
  "q_times_r": null,
  "q_times_r_necessary_condition": "q * r >= 0.60",
  "r": null,
  "registration_evidence": {
    "sealed_g304_packet_available": false,
    "status": "unmeasured_no_sealed_g304_packet"
  },
  "registration_passed": null
}
```

## Field semantics (verifier corrections)

- `ball_tracking_passed` is computed from `ball_valid_pct`, whose denominator
  is `emitted_frames` (`g305_additive_registration_verdict.py:154-156`), not
  from `ball_valid_attempted_frames_pct`. The two coincide at 1.0 here only
  because this construct emits every attempted frame.
- `player_tracking_passed` mirrors the harness `passed` field verbatim
  (`g305_additive_registration_verdict.py:161`), so it also carries ball and
  liveness failures. It is not a player-only bar.

## Durable records and seals

- `docs/evidence/tracking/g305_original_harness_verdict_2026-09-07.json`
- `docs/evidence/tracking/g305_reflected_harness_verdict_2026-09-07.json`
- `docs/evidence/tracking/g305_additive_registration_record_2026-09-07.json`

The harness raw-byte SHA-256 before and after is
`c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95`.
The record carries raw code hashes and these LF-normalized seals: harness
`59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`, schema
`72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e`, liveness
`50839e08fbb06112f77a0cc03e80b248dc54cbe1ee53e164fca244256ba150f0`, and producer
`1675bae219cec12c207a80af6c2eaface2473e219be56b59bda8251e6e7d9086`.

## Exhaustive construct and limits

The 8/8 CONSTRUCT is near_left_corner, near_right_corner, far_left_corner,
far_right_corner, asymmetric_interior_point, original_harness_run,
reflected_harness_run, and worked_additive_record. It is not a sampled or
scored metric. All 30 manifest frames remain in the denominator.

B1-B10 self-check: no rows were excluded; the record is additive; no gate,
lifecycle, deployment, reader, module, threshold, or shared-harness behavior
moved; and no sampled render, self-fit residual, or recycled denominator exists.
Q1-Q5 do not apply to this unscored construct. Q6 uses calibration-only
language. Q7 is the exhaustive construct; Q8 was remeasured before this pass.

Not verified:

- No real registration result was scored.
- `q` and `r` are schema fields, not measurements; their product is null.
- The pod's actual harness remains unread.
- No sealed G304 packet was available or evaluated.
- The WT-versus-main divergence does not exist here: the two files are
  byte-identical, so premise 4 is falsified rather than carried forward.
- A court-bearing census is not proof of q; visible lines and intersections need
  not yield an identifiable homography.
