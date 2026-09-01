# SynthCal tennis Wave 7 - blocked before diagnosis

## Required first action

Wave 7 requires a visual classification from twenty 720p real frames of
`nyYk2nPZAwY`, overlaid with v1 `synthcal_tennis.pt` predicted keypoints and
confidences. No training or implementation change is permitted before that
inspection.

## Operational result

On 2026-09-01, the configured private `pod` SSH endpoint refused the
connection. An independent TCP probe of the configured host and port returned
`False`. The requested video, trained checkpoint, and the locally absent
`TRACKING_RESEARCH_DIGEST_2026-09-01.md` therefore could not be inspected.

No pod process was stopped, no daemon was altered, no GPU training was launched,
and no model code or immutable harness was changed.

## Status

This is not a SynthCal failure result and not an impossibility claim. The
failure class (appearance gap, correspondence error, solver instability, or
non-convergence) remains unassigned because the mandated overlays do not exist.
When pod access is restored, resume with overlay generation and visual review;
only then select at most one bounded refinement and run the pre-registered
two-match real-frame gate.
