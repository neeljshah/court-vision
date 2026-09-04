# G215: Temporal Homography Propagation

## Result

**A G140 hand-labelled WNBA calibration remains visually plausible through 50
frames in this one live-camera run, is visibly off the painted court by 100
frames, and is grossly off by 200-300 frames.** This is a complete measurement
result: per-shot re-calibration or a court-local propagation method is required;
one global, frame-to-frame ORB homography is not enough for this camera motion.

This is one seeded run on one clip, measuring existence and decay shape, not a
rate across clips. There is no pass bar.

## Scope, seed, and coordinate contract

The source is the existing pod corpus video
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` (declared
1920x1080; 2,931,985,407 bytes; 174,430 frames). The bounded run starts at
G140/G196 seed frame 1600, `wnba__wnba_01_1080p__s01__f001600`, then decodes
300 contiguous forward frame steps at stride 1. Thus the requested run length
is 300 frames (about 10 seconds at 30 fps), ending at source frame 1900.

The seed is exactly the G140 role order and pixel labels:

| Role | Image point px |
|---|---:|
| near baseline left | `[350, 400]` |
| near baseline right | `[835, 420]` |
| near free-throw left | `[390, 696]` |
| near free-throw right | `[990, 730]` |

The harness imports G196's unchanged
`court_points_for_sport("wnba")` and `solve_homography`. It therefore preserves
the same `[x,y]` feet contract: 94-by-50-ft court, WNBA 16-ft lane, 19-ft
paint depth, and four seed court points `[17,0]`, `[33,0]`, `[17,19]`,
`[33,19]`. No label after the seed was read or used.

## Method

For each adjacent pair, the standalone
[`g215_temporal_homography_propagation.py`](../../../scripts/platformkit/tracking/g215_temporal_homography_propagation.py)
harness detects ORB features (2,000 maximum), matches with BF/Hamming plus a
0.75 ratio test, and estimates the previous-image-to-current-image homography
using OpenCV RANSAC at its fixed 3 px reprojection threshold. ORB feature
matching was chosen over optical flow because it also permits a direct
seed-to-current comparison at every distance without labels. The method does
not reject, tune, or score frames against an accuracy bar.

With seed image-to-court map `H0` and accumulated seed-image-to-current-image
motion `M0d`, propagation is `Hd = H0 inv(M0d)`. For a self-consistency control,
the harness separately estimates a direct seed-to-current map `M_direct` and
forms `H_direct = H0 inv(M_direct)`. It inverse-projects G196's four near-paint
model corners through both maps. The reported drift is their median and maximum
current-image displacement. The per-step RANSAC RMS is the residual on that
step's retained ORB inliers.

This uses only a few in-memory decoded frames and writes no extracted source
frames. The committed artifacts are the 300-row
[trace](g215_temporal_homography_propagation_artifact/drift_records.csv), full
[JSON](g215_temporal_homography_propagation_artifact/run_summary.json), and the
six overlays below.

## Drift versus distance

The **eligible denominator is the 300 frames actually propagated through**:
all 300 adjacent steps yielded a finite RANSAC homography, and the direct
seed-to-current comparison also yielded a finite map on all 300. This is a
processing denominator, not an accuracy-success denominator.

| Distance from seed, frames | Paint drift median px | Paint drift max px | Step inliers / matches | Step RMS px | Direct inliers / matches | Direct RMS px |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.000 | 0.000 | 1748 / 1809 | 0.649 | 1748 / 1809 | 0.649 |
| 25 | 17.281 | 26.489 | 1854 / 1882 | 0.327 | 1126 / 1244 | 0.259 |
| 50 | 10.876 | 18.531 | 1825 / 1856 | 0.500 | 1166 / 1279 | 0.259 |
| 100 | 38.472 | 65.469 | 1451 / 1581 | 0.141 | 910 / 948 | 0.334 |
| 200 | 42.935 | 74.349 | 1469 / 1616 | 0.139 | 642 / 673 | 0.373 |
| 300 | 187.772 | 255.077 | 1812 / 1834 | 0.505 | 607 / 634 | 0.382 |

Across all 300 steps, step-inlier counts range 1177-1883 and the step RMS range
is 0.000-1.021 px. Those small image-match residuals do **not** establish court
accuracy: the large late self-consistency drift and eye check show that a
globally well-fit feature transform can still be the wrong court-plane map.

## Rendered single-labeller eye check

Yellow is G196's inverse-projected court model; red points are the propagated
near-paint corners. This is the accuracy-bearing review because no target labels
exist after frame 1600. It is a single-labeller judgement, not a blind study.

| Distance | Render | Eye judgement |
|---:|---|---|
| 0 | [seed](g215_temporal_homography_propagation_artifact/render_distance_0000.jpg) | G196's seed overlay broadly follows the fitted paint and independently visible court geometry. |
| 25 | [25 frames](g215_temporal_homography_propagation_artifact/render_distance_0025.jpg) | Still plausibly follows the visible key and near court markings. |
| 50 | [50 frames](g215_temporal_homography_propagation_artifact/render_distance_0050.jpg) | Still visually plausible; the key overlay remains close enough to the painted court. |
| 100 | [100 frames](g215_temporal_homography_propagation_artifact/render_distance_0100.jpg) | Failure visible: the projected key/arc has separated from the painted key. |
| 200 | [200 frames](g215_temporal_homography_propagation_artifact/render_distance_0200.jpg) | Clear failure: projected paint and arc are plainly off the court markings. |
| 300 | [300 frames](g215_temporal_homography_propagation_artifact/render_distance_0300.jpg) | Gross failure: the yellow model no longer corresponds to the painted key. |

The observed eye-check failure lies between 50 and 100 frames at this sampling
resolution. It should not be interpolated into a precise frame threshold.

## What broke in this run

This was a continuous wide live-camera sequence that pans across the court. No
shot cut, replay, crowd-only frame, or obvious abrupt/heavy zoom occurs in the
300-frame run, so none of those failure modes was measured here. The propagation
fails during smooth camera motion alone. The high whole-image ORB inlier counts
while the court overlay fails are consistent with a probable mechanism: features
on crowd, signage, players, and other non-court content can support a global
image transform that is not the court-plane transform. That is an inference,
not a separately verified segmentation diagnosis.

A shot cut would be expected to invalidate correspondence outright, but this
run cannot quantify that effect. The result already answers the design question:
even before a cut, the tested global method requires re-anchoring before the
100-frame eye-check failure.

## Pod disk guard and cleanup

Before any pod artifact was written, `du -sm /workspace/nba-ai-system/data`
reported **28,984 MiB** and a 4 MiB `dd` probe was successfully removed. The
local worktree also passed and removed a 4 MiB probe before local writes.
The pod measurement wrote 4,000,997 bytes of temporary results and a 7,980-byte
temporary harness, both removed after the eight committed artifacts were copied
to this worktree. Two failed launch directories were empty (0 bytes each) and
were removed. The local and pod probes plus all pod run temporary files freed
**12,397,585 bytes** total. A final pod check confirmed no G215 temporary path
remained. No corpus source was modified or deleted; no daemon or keeper was
killed, restarted, or deployed over.

## NOT VERIFIED

- There is no ground truth after the seed. Drift against direct composition is
  self-consistency, not accuracy; render judgement is single-labeller evidence.
- The hand-labelled seed measures propagation only. It does not show that a
  seed can be obtained automatically. G210b's roughly 1-in-17 perfect-line
  oracle ceiling remains the open seed-selection problem.
- This is not a test of the non-deterministic per-frame solver route measured
  in G189/G195/G198; this row does not run that route.
- No rate across clips, camera shots, sports, cut types, replays, crowd frames,
  or zoom regimes was estimated.
- No court-feature mask, shot-boundary detector, keyframe policy, production
  tracker, source file, coordinate contract, threshold, daemon, or keeper was
  changed.

## Verification

- Per-file harness test: `python -m pytest tests/platformkit/test_g215_temporal_homography_propagation.py -q` -> `1 passed`.
- The new harness is 178 LOC, below the 300-LOC rail; the existing LOC rail is
  rerun before commit.
