# G241b: Corrected geometry control and camera-shot horizon

## PASS: the corrected 1,200-frame geometry control is exactly equal to G233d

All 1,200 post-seed direct-to-seed records are equal record-for-record on the only
G241b gate fields: matched features, inliers, inlier ratio, RMS reprojection residual,
and finite-map status. There are zero unequal pairs and all maps are finite. Detector
and projection values were not part of this gate.

This measurement-only landing follows
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production source, label, label CSV,
court model, matcher setting, coordinate contract, daemon, keeper, corpus source,
`src/`, or `domains/` file changed or was deployed.

## Hold, machine, target, and disk guard

The pod `/workspace/nba-ai-system` was used because it holds the read-only source
video. At launch, executable-plus-argument process inspection found the permanent
residents intact and two CPU-oriented transient measurement jobs; the RTX 3090 was at
7 percent utilization with 310 MiB used, leaving the stated second tracking lane
available. No process was interrupted.

The target was 10,000 post-seed frames. It is the predeclared useful bound in the
specification (`ceil(108000 / 10000) = 11`) and is far enough beyond G233d's stopped
1,200-frame span to encounter ordinary broadcast shot changes. `df` was not used. At
`2026-09-04T09:22:15+00:00`, `du -sm /workspace/nba-ai-system/data` was 32,937 MB.
The required `dd ... conv=fsync` probe wrote 1,048,576 bytes and passed; the exact
probe was then verified and removed. A first shell cleanup inherited a CRLF byte and
did not remove the probe; the corrected path-checked removal freed those same
1,048,576 bytes.

The 1,200-frame control pod temporary (780,265 bytes) was copied as retained evidence
then removed. The extended pod duplicate was copied and removed; its retained local
evidence is 6,094,908 bytes. A read-only scene-inventory temporary log was 3,660 bytes
and was verified and removed. Known temporary bytes freed are therefore at least
1,832,501; no corpus source was deleted.

## Frozen inputs and code identity

| Input | Full path | Bytes | Identity |
|---|---|---:|---|
| Corpus | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080, 174430 frames, 30 fps |
| Labels | `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` | 15,633 | SHA-256 `9ede0561441a062125bb708ee4496e7d22786608872e345d4079c70113000096` |
| G233d geometry reference | `docs/evidence/tracking/g233d_seed_gate_validated_frame_artifact/g233d_measurement.json` | 4,472,890 | committed direct-series comparison |

The unchanged G233d seed is source frame 19599, at scale 1.0 (no scaling), with
baseline-left `(350,400)`, baseline-right `(835,420)`, free-throw-left `(390,696)`, and
free-throw-right `(990,730)`. The WNBA 16-foot-lane court points remain
`[(17,0),(33,0),(17,19),(33,19)]`. The streamed source SHA-256 values, identical in
the control and extension, are G196 `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`,
G215 `dd23887aca61f50a65be51085033b398c97d056985fb8892eb5ab37009c5031a`, and G222
`7788d31c7ae4f705af0ec494547a28e160fb6b3980c383a6896b932499cea450`.
The pod-read detector file `/workspace/nba-ai-system/src/tracking/player_detection.py`
was 9,992 bytes with SHA-256
`c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7`.

## Corrected control and extended direct geometry

| Direct-to-seed quantity, distances 1-1200 | G233d | G241b control |
|---|---:|---:|
| Records / finite maps | 1,200 / 1,200 | 1,200 / 1,200 |
| Matched features, min-max | 452-1,863 | 452-1,863 |
| Inliers, min-max | 421-1,848 | 421-1,848 |
| Inlier ratio, min-max | 0.8399014778-0.9919484702 | 0.8399014778-0.9919484702 |
| RMS reprojection px, min-max | 0.2993646860-0.7026225924 | 0.2993646860-0.7026225924 |
| Unequal paired records | 0 | 0 |

The extension has 10,000/10,000 finite direct maps: its direct matcher never returned
an ineligible map. Across that requested bound, matches are 81-1,863, inliers 44-1,848,
ratio 0.381356-0.991948, and RMS 0.204551-1.876235 px.

| Distance | Matches | Inliers | Ratio | RMS px |
|---:|---:|---:|---:|---:|
| 1 | 1863 | 1848 | 0.991948 | 0.320121 |
| 1000 | 596 | 552 | 0.926174 | 0.347362 |
| 2000 | 611 | 556 | 0.909984 | 0.321901 |
| 3000 | 524 | 499 | 0.952290 | 0.441021 |
| 4000 | 116 | 60 | 0.517241 | 0.569182 |
| 5000 | 463 | 365 | 0.788337 | 0.607194 |
| 6000 | 294 | 257 | 0.874150 | 0.464084 |
| 7000 | 343 | 305 | 0.889213 | 0.499834 |
| 8000 | 366 | 265 | 0.724044 | 0.366475 |
| 9000 | 269 | 229 | 0.851301 | 0.366882 |
| 10000 | 164 | 119 | 0.725610 | 0.598171 |

Direct-reference drift is 0.0 by construction and is not independent evidence. The
feature series and independent-geometry renders are the evidence.

## What actually breaks the usable horizon: a camera shot cut

The direct matcher stays finite through 10,000, but the eye check fails much earlier.
At 0, 1000, 2000, and 3000, the projected three-point arc and visible sidelines follow
the independent painted geometry. At the first failed regular render, [distance 4000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_4000.jpg),
the broadcast has cut to a tight player close-up: no painted court remains to support
the full-court overlay. The yellow projected court is visibly off the court. The four
red fitted paint corners are not used as evidence. The [0](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_0000.jpg),
[3000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_3000.jpg),
[5000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_5000.jpg),
[7000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_7000.jpg),
[9000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_9000.jpg),
and [10000](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_10000.jpg)
renders retain the full increasing-distance audit. Wide shots can realign after a cut;
the 9000 close-up and 10000 tight low-angle shot are also visually unusable.

This is not G215's chained-pan decay. A hard scene inventory over the 10,000-frame
span found 15 `scene > 0.40` cut candidates. The first close-up transition is consistent
with the 129.2-second inventory candidate (about distance 3,876); the direct series
then drops abruptly from 310 matches at distance 3,932 to 182 at 3,933 and falls to 81
near distance 4,440. That is a cut followed by a sustained loss of seed-view overlap,
not gradual pan-only decay. A second abrupt drop appears at distance 9,823 (327 to 162
matches), consistent with the later tight-shot evidence. The scene count is a bounded
inventory at its stated threshold, not a population camera-edit rate.

The operational unit is therefore the **camera shot**, not a frame count. The first
sampled visually usable horizon ends at 4,000 frames because a shot cut invalidates a
still-finite map. `ceil(108000 / 4000) = 27` labels per hour is only the repeated-span
arithmetic for that observed first shot; it is not a corpus-wide rate. The arithmetic
`ceil(108000 / 10000) = 11` describes finite direct-map persistence only and is not an
operational labeling claim after the distance-4000 eye failure.

## Advisory detector/projection draw

These figures are descriptive only and are one draw from the known non-deterministic
detector. They are not a control, do not gate extension, and fractions are deliberately
shown to three decimals. Every direct-detector box with a finite projection is retained.

| First 0-1200 frames | Boxes / inside | In-court fraction |
|---|---:|---:|
| G233d | 11,236 / 9,720 | 0.865 |
| G241 | 11,242 / 9,723 | 0.865 |
| G241b | 11,241 / 9,722 | 0.865 |

Relative to G233d, this draw is +5 boxes and +2 inside; relative to G241, it is -1
box and -1 inside. Its full 0-10,000 descriptive aggregate is 82,007 finite boxes,
66,946 inside, fraction 0.816. The 1,000-frame bins have fractions 0.869, 0.795,
0.817, 0.717, 0.644, 0.870, 0.860, 0.823, 0.856, and 0.867 (the final singleton frame
is 0.714). Officials, bench personnel, spectators, and tight-shot detections remain in
this denominator, so plausibility is necessary and never sufficient.

## Verification and limits

Focused test: `python -m pytest scripts/platformkit/tracking/test_g241b_seed_horizon_to_failure.py -q -p no:cacheprovider`
returned `4 passed`. No full test suite was run. Contract self-check: A2 recomputed the
control and extended figures from the retained JSON; A7 confirmed every linked render
and artifact path; A9 names exact inputs; A11 names every exercised route hash. B1
retains every direct record and names the detector denominator; B2-B6 change no schema,
lifecycle, deployment, production module, or module location; B7 uses 0 through 10,000
even-distance direct renders; B8 excludes fitted corners and construction-zero drift;
B9 uses per-frame detector boxes; B10 moves no bar. Q does not apply to this tracking
measurement row.

**NOT VERIFIED:** automatic calibration (this consumes one hand label; automatic remains
0/17); geometry correctness after a cut or tight shot; ground truth; detector identity,
localisation, or repeatability; repeatability of the single-labeller G196 gate; other
clips/cameras/shots; any population labeling throughput; and the cause of every one of
the 15 scene candidates. G140's p90 label repeatability remains 11.39 px.
