# G241: G233d control mismatch stopped the horizon extension

**NOT VALIDATED - STOP BEFORE EXTENSION.** The required G233d 1,200-frame control
reproduced every direct-to-seed G222 propagation record exactly, but it did not reproduce
the G233d detector/projection records or their physical-plausibility aggregates. G241
therefore stops here, as its method requires; no frame beyond distance 1,200 was measured.
There is consequently no failure horizon, cut/zoom inventory, cause-of-failure finding, or
new labels-per-hour calculation.

This measurement-only STOP follows
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production source, label, label CSV,
court model, matcher setting, coordinate contract, daemon, keeper, corpus source, `src/`,
or `domains/` file was changed or deployed.

## Hold, machine, and disk guard

The pod `/workspace/nba-ai-system` was used because it holds the read-only corpus video.
At G241 launch, an exact executable-and-argument process check found no G240 process; no
process was interrupted, and permanent residents were untouched. `df` was not used.

Before the control wrote a temporary artifact, `du -sm /workspace/nba-ai-system/data`
reported `32759` MB. The required
`dd if=/dev/zero of=/workspace/nba-ai-system/g241_disk_probe.bin bs=1M count=1 conv=fsync`
passed, wrote 1,048,576 bytes, and that exact probe file was removed. The G233d wrapper
retrieved and removed its exact `/tmp/g233d_seed_0emlggwt` directory. Its retained local
payload is 18 files and 14,587,692 bytes; the remote pre-removal byte total was not captured,
so the only independently known freed-byte count is 1,048,576. No corpus source was deleted.

## Frozen inputs and identity

| Input | Full path | Bytes | Identity |
|---|---|---:|---|
| Corpus | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080, 174430 frames, 30 fps |
| Labels | `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` | 15,633 | SHA-256 `9ede0561441a062125bb708ee4496e7d22786608872e345d4079c70113000096` |
| G233d control | `docs/evidence/tracking/g233d_seed_gate_validated_frame_artifact/g233d_measurement.json` | 4,472,890 | committed comparison artifact |
| G241 control | `docs/evidence/tracking/g241_seed_horizon_to_failure_artifact/control_g233d_1200/g233d_measurement.json` | 4,331,092 | reproduced control artifact |

The CSV rows read for `wnba__wnba_01_1080p__s01__f001600` are the unchanged G233d labels:
baseline-left `(350,400)`, baseline-right `(835,420)`, free-throw-left `(390,696)`, and
free-throw-right `(990,730)`, all at 1920x1080. The control used frame 19599, scale factor
**1.0** (no scaling), and `court_points_for_sport("wnba")`, the WNBA 16-foot lane:
`[(17,0),(33,0),(17,19),(33,19)]`.

This is the landed G233d wrapper and G222 direct-to-seed construction with the sole intended
measurement difference deferred to a farther run. The control necessarily retains G233d's
capture-based seed read; G233d's already-landed frame-accurate G236b validation is not
substituted or retuned here.

The control payload records these source SHA-256 values: G196
`f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`, G215
`dd23887aca61f50a65be51085033b398c97d056985fb8892eb5ab37009c5031a`, and G222
`7788d31c7ae4f705af0ec494547a28e160fb6b3980c383a6896b932499cea450`. The pod-read
`/workspace/nba-ai-system/src/tracking/player_detection.py` was 9,992 bytes with SHA-256
`c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7`.

## Required G233d control reproduction

The 1,200 post-seed direct records are exactly equal, record-for-record, to G233d:

| Direct-to-seed quantity | G233d | G241 control |
|---|---:|---:|
| Records / direct eligible | 1,200 / 1,200 | 1,200 / 1,200 |
| Matched features, min-max | 452-1,863 | 452-1,863 |
| Inliers, min-max | 421-1,848 | 421-1,848 |
| Inlier ratio, min-max | 0.8399014778-0.9919484702 | 0.8399014778-0.9919484702 |
| RMS reprojection px, min-max | 0.2993646860-0.7026225924 | 0.2993646860-0.7026225924 |
| Unequal paired records | 0 | 0 |

Direct-reference drift is 0.0 by construction and is **not** evidence. Matched-feature
counts and the independent-geometry renders carry the direct-path comparison.

The detector/projection portion does not reproduce: 808 of 1,201 distance records differ.
All records remain in both denominators; nothing was excluded. The changed aggregates are:

| Distance | G233d boxes / inside / fraction | G241 control boxes / inside / fraction |
|---|---|---|
| 0-199 | 1,658 / 1,373 / 0.828106 | 1,661 / 1,373 / 0.826610 |
| 200-399 | 1,670 / 1,533 / 0.917964 | 1,671 / 1,534 / 0.918013 |
| 400-599 | 1,940 / 1,675 / 0.863402 | 1,945 / 1,679 / 0.863239 |
| 600-799 | 1,752 / 1,553 / 0.886416 | 1,751 / 1,552 / 0.886351 |
| 800-999 | 1,935 / 1,651 / 0.853230 | 1,936 / 1,653 / 0.853822 |
| 1000-1199 | 2,269 / 1,925 / 0.848391 | 2,266 / 1,922 / 0.848191 |
| 1200 | 12 / 10 / 0.833333 | 12 / 10 / 0.833333 |
| **All 0-1200** | **11,236 / 9,720** | **11,242 / 9,723** |

The control's direct maps and renders hold through distance 1,200, but G241's required control
is the entire G233d construction, including its projection report. The mismatch is therefore
decisive. It is not a named propagation failure and must not be misreported as a shot cut,
replay, hard zoom, crowd-only frame, or gradual feature-overlap loss.

## Independent-geometry render review

All fourteen G222 renders are retained: seven direct-seed renders in
`docs/evidence/tracking/g241_seed_horizon_to_failure_artifact/control_g233d_1200/paired/direct_seed_renders/`
and seven chained renders in
`docs/evidence/tracking/g241_seed_horizon_to_failure_artifact/control_g233d_1200/paired/chained_renders/`.
The direct renders at [distance 0](g241_seed_horizon_to_failure_artifact/control_g233d_1200/paired/direct_seed_renders/render_distance_0000.jpg)
and [distance 1200](g241_seed_horizon_to_failure_artifact/control_g233d_1200/paired/direct_seed_renders/render_distance_1200.jpg)
visually retain alignment on the visible three-point arc and sideline. The four red labelled
paint corners are fitted inputs and were not used as evidence; the centre circle is outside
this hoop-end view. This limited eye check agrees with G233d's observed control span but does
not resolve the detector/projection mismatch.

## Verification and limits

Focused test: `python -m pytest scripts/platformkit/tracking/test_g233d_seed_gate_validated_frame.py -q -p no:cacheprovider`
returned `3 passed`. No G241 harness was added; no full test suite was run.

Contract self-check: A7 paths named above exist; A9 names each opened input; A11 records the
route identities; B1 retains every paired and projection record; B2-B6 change no schema,
lifecycle, deployment, production module, or module location; B7 retains evenly spaced
0/200/400/600/800/1000/1200 renders; B8 does not treat fitted corners or construction-zero
drift as independent evidence; B9 uses distinct per-frame detector boxes; and B10 moves no
bar or matcher setting. Q does not apply to this tracking measurement row.

**NOT VERIFIED:** a propagation horizon beyond 1,200; any propagation failure cause; a cut,
replay, zoom, crowd-frame, or overlap-loss inventory beyond the control; labels per hour for a
measured horizon; automatic calibration (it remains 0/17); ground truth, detector identity, or
localisation accuracy; repeatability of the single-labeller G196 gate; cross-camera behaviour;
and population-level labeling throughput. This row consumes a hand label, and plausibility is
necessary but never sufficient because detections can include officials, bench personnel, and
spectators.
