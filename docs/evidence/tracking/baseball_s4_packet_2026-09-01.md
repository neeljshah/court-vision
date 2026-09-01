# Baseball S4 packet - 2026-09-01

## Retraction - 2026-09-01

The blanket claim that field homography is impossible for the baseball S4
corpus is PULLED. The original evidence selected only mound-gated pitch-camera
frames, then generalized that selected framing to all baseball broadcast
frames. The blind 75-frame provisional label pass from the full-timeline NPB
census falsified that generalization: about 35-45 percent of those genuine NPB
frames contain at least two simultaneous landmarks, well above the
pre-registered 10 percent falsification threshold.

The two other census sources are void: `mlb_x6YpMlNYbrU` is a webcam podcast
and `kbo_lrK_Hv6BEE0` is a studio talk show. Neither is census evidence nor a
member of the S4a declared corpus.

## What the original calibration numbers actually measured

Every numeric observability result retained from the original packet is
pitch-cam-scoped, not a statement about all baseball broadcast framing:

- The two independent 1280x720 MLB centre-field clips, 500 sampled frames per
  clip at stride 3, were pitch-cam-scoped samples.
- The 18-ft mound chord, lateral-FOV p50 of about 42 ft, observed 26.9-42.3 ft
  range, and p95 of 66.2 ft are pitch-cam-scoped measurements.
- The 90-ft infield requirement, 127.28-ft first-to-third lateral span, and
  0/24 usable mound-frame count are pitch-cam-scoped observations.
- Score-bug obscuration and merged home-plate dirt were pitch-cam-scoped
  failure modes. They do not rule out a wide-view landmark solve.

Those measurements remain useful evidence about the narrow pitch-camera
regime. They are not evidence of field-homography impossibility across the
full broadcast.

## Rescoped honest claims

1. Continuous full-field coordinate tracking remains unsupported. It now
   awaits the 4-or-more-landmark wide-view count from the completed 300-frame
   NPB label pass; the current provisional count is not enough to make that
   broader capability claim.
2. Pitch-camera frames can anchor plate-region scale through the 60.5-ft
   home-plate-to-mound rule distance. This is a partial-calibration lane, not
   an impossibility result and not a validated full-field homography.
3. The declared `image_px` corpus contains NPB-family clips confirmed to be
   game broadcasts only. It excludes the void MLB and KBO talk-show sources.
   Consumers may use its rows for observed-pixel detector and temporal-
   identity research, never as field coordinates.

## Corrected S4a decode classification

The prior `non_play=300/300` S4a result was a classifier defect, not a content
finding. The emission path reused the strict mound/plate pitch-geometry gate
as a non-play test. Genuine wide infield and other confirmed-game frames fail
that calibration gate by design.

The corrected confirmed-game emission preserves the full 300-frame NPB census
denominator and reports `solved=0`, `unsolved=300`, `non_play=0`. `unsolved`
means no validated full-field solve is attached; it does not mean the frame is
outside a game broadcast. The resulting manifest and count sidecar are in
`scripts/platformkit/a3_artifacts/s4a_npb_reemission/`.

## Consumer contract

No consumer may infer field locations, field-space harness metrics, or a
full-field homography from this packet. Any future continuous full-field claim
requires the separate wide-view landmark count and a validated coordinate
solution.
