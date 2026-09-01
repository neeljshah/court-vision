# Tennis camera-lock honest measurement: accepting sections

Date: 2026-09-01

## Protocol and code identity

- The jobs ran on pod `213.192.2.83:40048` with `nice -n 15 python`.
- The pod checkout is an unpacked, pre-camera-lock snapshot, so it was not
  altered. Instead, the current-master tennis tracking modules were staged
  under pod `/tmp/tennis-camera-lock-master` and imported ahead of the pod
  source tree. This is a temporary measurement overlay, not a deployment or a
  daemon change.
- Current-master SHA-256: `adapter.py` `0b4c8d07c3c72de91f02f7d927fdda60259115c287bd546189d74fab79345898`;
  `camera_lock.py` `0dc42b53df66fd90d7e2a792910d54745a2556003507cf28e8efcde6d19b4302`.
  The frozen harness was unchanged, SHA-256
  `93cf19288bc45e1c3b459337085934d2e14e21a244a0251f739d33f97226dde6`.
- `raw accepts` means `detect_court_corners` returned corners. `fresh solves`
  are manifest rows whose provenance is `solved`; an accepted raw corner can
  still fail temporal stability. A solved frame is a manifest row with either
  `solved` or `camera_lock_drift_checked` provenance.
- The denominator is every decoded manifest row. No emitted-row denominator is
  used.

## Honest funnel

| Section | Source-frame plan | Decoded | Raw accepts | Fresh solves | Locks formed | Drift-checked reuses | Drift rejects | Solved-frame coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A/B 720p (`nyYk2nPZAwY_720p`) | 600 `linspace(0, 48047)` requests | 599 | 60 | 50 | 5 | 11 | 1 | 61 / 599 = 0.1018 |
| 1080p positive control (`tennis_09`) | sequential 5050-5120 | 71 | 5 | 5 | 2 | 0 | 0 | 5 / 71 = 0.0704 |
| Dead 720p diagnostic (`nyYk2nPZAwY_720p`) | sequential 3816-4565 | 750 | 0 | 0 | 0 | 0 | 0 | 0 / 750 = 0.0000 |

The 1080p control was selected before the measurement by a sequential raw
scan of all frames 0-7506. Its only raw accepts were 5067, 5078, 5086, 5087,
and 5097; section 5050-5120 encloses all five. It is an accepting section,
but it has no accepted missing-corner frames while a lock is ready, so it
provides no reuse observations.

The A/B section does exercise the reuse path: five locks form, eleven rows are
current-frame drift-checked reuses, and one reuse attempt fail-closes as a
drift rejection. This is coverage measurement only; neither result passes the
frozen tracking-quality gate below.

## Frozen harness outputs, verbatim

The harness was run because locks formed in both accepting sections. Thresholds
were not edited.

### A/B 720p (exit code 1)

```json
{
  "sport": "tennis",
  "config_version": "2026-09-01-v1",
  "n_frames": 54,
  "n_unique_games": 1,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 3,
  "coverage_pct": 1.0,
  "det_per_frame": 2.06,
  "median_track_len": 2.0,
  "ball_valid_pct": 0.0556,
  "ball_valid_applicable": true,
  "jump_p95": 10.96,
  "oob_pct": 0.213,
  "zero_step_share": 0.0,
  "median_step_distance": 1.2408,
  "distinct_position_ratio": 1.0,
  "stationary_track_share": 0.4167,
  "liveness_verdict": "UNCALIBRATED",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": false,
  "failures": [
    "median_track_len 2.00 < 3.00",
    "oob 0.21 > 0.08",
    "jump_p95 10.96 > 8.00",
    "ball_valid 0.06 < 0.20"
  ]
}
```

### 1080p positive control (exit code 1)

```json
{
  "sport": "tennis",
  "config_version": "2026-09-01-v1",
  "n_frames": 5,
  "n_unique_games": 1,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 2,
  "coverage_pct": 1.0,
  "det_per_frame": 2.4,
  "median_track_len": 1.0,
  "ball_valid_pct": 0.4,
  "ball_valid_applicable": true,
  "jump_p95": 1.0,
  "oob_pct": 0.0,
  "zero_step_share": 0.0,
  "median_step_distance": 0.8244,
  "distinct_position_ratio": 1.0,
  "stationary_track_share": 0.75,
  "liveness_verdict": "UNCALIBRATED",
  "source_resolution": null,
  "source_frame_rate": null,
  "self_consistency_only": true,
  "passed": false,
  "failures": [
    "median_track_len 1.00 < 3.00"
  ]
}
```

## Dead-section orientation rejection samples

These are the first ten source frames in 3816-4565 whose first production
rejection is `insufficient_oriented_lines` (the prior funnel's orientation
failure). The orientation gate requires at least two horizontal and at least
two vertical Hough segments. Horizontal means `abs(dx) / abs(dy) >= 1.5`;
vertical means `abs(dy) > abs(dx)`. Bounds shown here are the production
bounds, not proposed changes.

| Frame | Horizontal measured / bound | Vertical measured / bound | Unclassified | Segment `abs(dx)/abs(dy)` min-max |
|---:|---|---|---:|---|
| 3987 | 10 / >=2 | 0 / >=2 | 0 | 4.7391 - 30.8333 |
| 4005 | 1 / >=2 | 1 / >=2 | 0 | 0.1339 - 30.5000 |
| 4087 | 7 / >=2 | 1 / >=2 | 0 | 0.0301 - inf |
| 4099 | 28 / >=2 | 1 / >=2 | 0 | 0.0827 - inf |
| 4101 | 33 / >=2 | 1 / >=2 | 0 | 0.0752 - inf |
| 4102 | 33 / >=2 | 1 / >=2 | 0 | 0.1111 - inf |
| 4103 | 37 / >=2 | 1 / >=2 | 0 | 0.1495 - inf |
| 4106 | 28 / >=2 | 1 / >=2 | 0 | 0.0515 - inf |
| 4107 | 34 / >=2 | 1 / >=2 | 0 | 0.0526 - inf |
| 4108 | 30 / >=2 | 1 / >=2 | 2 | 0.0841 - inf |

Most sampled dead frames have abundant horizontal detections but only zero or
one vertical detection, so they do not meet the unchanged `>= 2` vertical
requirement. This identifies the observed footage/gate mismatch without
claiming which side should change.
