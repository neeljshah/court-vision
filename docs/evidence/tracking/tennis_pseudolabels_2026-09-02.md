# G23 Tennis Pseudo-Labels (2026-09-02)

Source: the G18 sequential harness-PASS plans on the pod, processed with the
deployed classical tennis adapter. No solver threshold, camera-lock threshold,
or harness value changed. A label row is emitted only for `solved` fresh
homographies or `camera_lock_drift_checked` reuses.

## Artifacts

- JSONL labels and per-match manifests: `tennis_pseudolabels_2026-09-02/`.
- Source images are not copied by the label format. Each row references its
  broadcast video and decoded source-frame index.
- 40 deterministic, globally evenly spaced rendered labels are in
  `tennis_pseudolabels_2026-09-02/holdout/`.
- The three JSONL files total 3,276,480 bytes, below the 5 MB retention limit.

## Label count and provenance

| match | PASS ranges | labeled frames | fresh | drift-checked reuse |
|---|---:|---:|---:|---:|
| nyyk | 5 | 1,119 | 998 | 121 |
| tennis09 | 1 | 300 | 300 | 0 |
| tennis10 | 4 | 790 | 750 | 40 |
| total | 10 | 2,209 | 2,048 | 161 |

Every label has 14 canonical court keypoints, image-space coordinates,
visibility, range id, solve type, drift pixels, drift evidence count, and
detected-line reprojection residual. A keypoint beyond the decoded frame is
flagged invisible. This run had zero invisible keypoints.

The shared tennis canonical mapping has 12 entries. The generator retains its
ten non-net-post entries and completes the 14-point learner convention with
the four service-line/singles-sideline intersections; the two `net_post_*`
entries are not physical posts and are outside that 14-point convention.

## Holdout eye check

I viewed each of the 40 rendered frames. In every case the four projected
doubles-court corner keypoints land on their corresponding court corners.

| check | result |
|---|---:|
| holdout frames | 40 |
| corners yes | 40 |
| corners no | 0 |
| corner precision by eye | 100.0 pct |
| usability gate (>= 90 pct) | PASS / usable pseudo-label set |

The holdout is an eye check of bootstrap-label geometry, not a manually
annotated accuracy benchmark.

## Target gap

The 2,209 sequential labels are inside the 2,000-2,500 first-checkpoint
target. Additional PASS ranges needed for that count target: 0. This does not
verify learned-model training, PCK@7px, the published 0.933 accuracy / 2.83 px
reference ceiling, or independence from the classical teacher.
