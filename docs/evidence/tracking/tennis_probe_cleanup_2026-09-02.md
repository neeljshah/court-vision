# Tennis probe cleanup -- 2026-09-02

The five probes below measured private `TennisAdapter` helpers from the
pre-`court_lines` solver. They are retired, rather than retargeted, because
retaining their old output keys would label obsolete gate counts and thresholds
as current-solver measurements. Historical evidence remains in place.

| Script | Decision | Replacement |
|---|---|---|
| `scripts/platformkit/tennis_gate_funnel.py` | RETIRE | `scripts.platformkit.tennis_camera_lock_measure` reports current raw solves, locks, drift-checked reuse, and decoded-frame coverage. |
| `scripts/platformkit/line_detector_ab.py` | RETIRE | `domains.tennis.tracking.court_lines` is the shipped detector and `tennis_camera_lock_measure` is the current end-to-end measure. |
| `scripts/platformkit/tennis_threshold_sweep.py` | RETIRE | `court_lines` owns its fixed evidence cascade; `tennis_camera_lock_measure` measures the unchanged production path. |
| `scripts/platformkit/tennis_resolution_anchor_ab.py` | RETIRE | `domains.tennis.tracking.court_diagnostics.held_out_service_t_error` measures the current selected court lines. |
| `scripts/platformkit/tracking/tennis_vertical_probe.py` | RETIRE | `tennis_camera_lock_measure` measures the current `court_lines` plus `camera_lock` path. |

The retired source lives under `scripts/platformkit/_retired/` with a header
naming its replacement. No solver threshold or harness value changed. The
adapter helpers remain because current `court_lines`, `court_diagnostics`,
`tennis_metric_probe`, and `homography_eligibility` still consume them.
