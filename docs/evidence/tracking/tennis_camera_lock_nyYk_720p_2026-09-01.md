# Tennis camera-lock measurement: nyYk 720p section

Date: 2026-09-01

## Protocol

- Source: `data/videos/bridge/tennis_nyYk2nPZAwY.mp4`, independently probed as 1280x720 at 50 fps.
- Section: source timestamp 76.32 s, the documented source-frame 3816-4565 window. The re-encoded extract decoded 725 frames (14.5 s); this is the denominator, not the nominal 750-frame window.
- Adapter: `domains.tennis.tracking.adapter.TennisAdapter`, stride 1, `max_frames=750`.
- Camera lock: requires 3 independently accepted fresh solves; reuse requires at least 2 current-frame detected line intersections and drift <= 5.0 px at 720p. A failed or unmeasurable check emits no row and records `unsolved_drift` when a lock exists.
- Frozen harness: unedited `scripts/platformkit/tracking_harness.py`, invoked as `python -m scripts.platformkit.tracking_harness <tracking.csv> tennis`.

## Honest manifest accounting

| Measure | Value |
|---|---:|
| Decoded frames | 725 |
| Evaluated frames | 725 |
| Fresh-solve frames | 0 |
| Fresh full-solve rate | 0 / 725 = 0.0000 |
| Validated-reuse frames | 0 |
| Validated-reuse coverage | 0 / 725 = 0.0000 |
| Emitted player frames | 0 |
| Emitted player rows | 0 |
| `calibration_unavailable` frames | 725 |
| `unsolved_drift` frames | 0 |
| Frames with measured drift | 0 |

The lock cannot form without its minimum three independent fresh accepts, so
the drift distribution has n=0 and p50/p95/max are undefined. This is an
honest fail, not a zero-drift result. No reuse rows were emitted.

## Frozen harness verbatim

```json
{
  "sport": "tennis",
  "config_version": "2026-09-01-v1",
  "n_frames": 0,
  "n_unique_games": 0,
  "n_duplicate_frame_track_rows": 0,
  "ball_rows": 0,
  "coverage_pct": 0.0,
  "det_per_frame": 0.0,
  "median_track_len": 0.0,
  "ball_valid_pct": 0.0,
  "ball_valid_applicable": true,
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
  "failures": [
    "empty"
  ]
}
```

Verdict: FAIL. The camera-lock mechanism is implemented and fail-closed, but
this section supplies zero accepted fresh solves, so no lock and no coverage
multiplier can be honestly claimed.
