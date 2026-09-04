# G233d: Validated WNBA Seed Gate

## PASS - the distance-zero projected WNBA court lands on the painted court

The four red paint-corner marks are fitted inputs, not gate evidence. The independent near three-point curve and visible sideline align with painted markings; the centre circle is outside this hoop-end crop. This is one eye judgement, not ground truth. See [seed render](g233d_seed_gate_validated_frame_artifact/seed_render_distance_0000.jpg).

This measurement-only landing follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`; no production source, label, label CSV, coordinate contract, threshold, daemon, keeper, corpus source, `src/`, or `domains/` file changed.

## Hold, machine, and disk guard

The pod `/workspace/nba-ai-system` was used because it holds the read-only video. At `2026-09-04 03:22:14 -05:00`, the exact Python executable/argument check found G225 active; it was not interrupted. It was absent at `03:23:00`, and final launch checks at `03:28:52` and `03:31:49` also found it absent. Permanent residents were untouched.

`df` was not used. Before writing, `du -sm /workspace/nba-ai-system/data` was 32622 MB. `dd if=/dev/zero of=/workspace/nba-ai-system/g233d_disk_probe.bin bs=1M count=1 conv=fsync` passed; its 1048576-byte file was removed. An earlier malformed shell wrapper established no probe status and no decode began from it. No corpus source was deleted.

## Inputs, exact decode, labels, and model

| Input | Full path | Bytes | Identity |
|---|---|---:|---|
| Corpus | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2931985407 | 1920x1080, 174430 frames, 30 fps |
| G196 YES still | `C:\Users\neelj\nba-track-a3\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s01__f001600.jpg` | 621798 | 1920x1080; SHA-256 `e9ead024840b53be902376b3cd76918ef36ae9d7b40527c5c413cc21ce9183f8` |
| Label CSV | `C:\Users\neelj\nba-track-a3\docs\evidence\tracking\g140_corner_targets\corner_pixel_targets.csv` | 15633 | SHA-256 `9ede0561441a062125bb708ee4496e7d22786608872e345d4079c70113000096` |

Frame 19599 (zero-based) was decoded with `ffmpeg -i VIDEO -vf select=eq(n\,19599) -vsync 0 -frames:v 1 -f rawvideo -pix_fmt bgr24 pipe:1`; there was no input-side `-ss`. Its native BGR SHA-256 is `686c94a7738c3e1ede2b39ea98cb09f096eead96826ff543baf4585d4c8f4270`, and its native BGR MAD versus G236b's committed `best_match_1920x1080.jpg` is 1.087048. Both still and video are 1920x1080: **scale factor 1.0, no scaling applied.**

I read these CSV values: baseline-left `(350,400)`, baseline-right `(835,420)`, free-throw-left `(390,696)`, free-throw-right `(990,730)`. `court_points_for_sport("wnba")`, not NCAA, supplied the 16-foot-lane points `[(17,0),(33,0),(17,19),(33,19)]`. The image-to-court homography is:

```text
[[0.050071754999888064, 0.01225404716365722, 2.3351407383547964],
 [-0.0047586809476217904, 0.1153980129798286, -44.493666860263815],
 [3.054485397744623e-05, 0.0011147252900901028, 1.0]]
```

## Direct-to-seed propagation and projection

The unchanged G222 source was streamed over stdin and called at seed 19599. All 1200 post-seed frames (to source frame 20799) had finite direct maps. Full-span direct matches were 452-1863, inliers 421-1848, inlier ratio 0.839901-0.991948, and RMS residual 0.299365-0.702623 px. The direct-reference drift is 0.0 by construction, so it is not independent evidence.

| Distance | Matches | Inliers | Ratio | RMS px |
|---:|---:|---:|---:|---:|
| 1 | 1863 | 1848 | 0.991948 | 0.320121 |
| 200 | 637 | 610 | 0.957614 | 0.340061 |
| 400 | 549 | 520 | 0.947177 | 0.424835 |
| 600 | 630 | 561 | 0.890476 | 0.449880 |
| 800 | 685 | 657 | 0.959124 | 0.388130 |
| 1000 | 596 | 552 | 0.926174 | 0.347362 |
| 1200 | 679 | 610 | 0.898380 | 0.357861 |

All seven direct and seven chained renders are retained in [paired artifacts](g233d_seed_gate_validated_frame_artifact/paired/); the [even-distance contact sheet](g233d_seed_gate_validated_frame_artifact/paired/direct_seed_even_distance_contact_sheet.jpg) includes 0, 200, 400, 600, 800, 1000, and 1200. The direct court did not come off the painted court in this observed span.

Direct `FeetDetector` inference used every class-0 box bottom-centre. The denominator is all direct-detector boxes with finite projections; positive outside distances are retained. These are descriptive only because non-players can be detected.

| Frames | Boxes / finite | Inside | Fraction | Outside positive: n, median, p90, p99, max ft |
|---|---:|---:|---:|---|
| 0-199 | 1658 / 1658 | 1373 | 0.828106 | 285, 3.208, 7.912, 12.491, 14.541 |
| 200-399 | 1670 / 1670 | 1533 | 0.917964 | 137, 3.041, 8.122, 11.527, 11.934 |
| 400-599 | 1940 / 1940 | 1675 | 0.863402 | 265, 1.612, 11.273, 17.171, 19.663 |
| 600-799 | 1752 / 1752 | 1553 | 0.886416 | 199, 1.076, 5.803, 12.535, 12.600 |
| 800-999 | 1935 / 1935 | 1651 | 0.853230 | 284, 2.379, 8.011, 11.223, 17.048 |
| 1000-1199 | 2269 / 2269 | 1925 | 0.848391 | 344, 3.441, 10.811, 15.598, 20.145 |
| 1200 | 12 / 12 | 10 | 0.833333 | 2, 1.508, 1.907, 1.996, 2.006 |

Full unrounded records are in [measurement JSON](g233d_seed_gate_validated_frame_artifact/g233d_measurement.json). At 30 fps, `ceil(108000 / 1200) = 90` labels per hour under the repeated-span assumption. This is neither a corpus-wide rate nor an extrapolation beyond the tested horizon.

## Identity, cleanup, verifier self-check, and NOT VERIFIED

SHA-256: G196 `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`; G215 `b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a`; G222 `2b99a30f3ff6dd1d633e0d088dee150c379f655e2fb78556589b5a948743d8c4`; launcher `69abb54015b06bae3abbfc998ac6241862219c7d73e7a8519ac8b565d206b3aa`; pod-read `src/tracking/player_detection.py` (9992 bytes) `c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7`.

Removed pod temporaries: 10255451 and 14585020 bytes; removed launcher logs: 887 and 840 bytes. Including the probe, known temporary bytes freed are 25890774. The retained artifacts are committed evidence, not temporary output.

Focused tests: `python -m pytest scripts/platformkit/tracking/test_g233d_seed_gate_validated_frame.py -q -p no:cacheprovider` -> `3 passed`; `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> `1 passed`.

Contract self-check: A7 paths exist; B1 names every finite box and the positive-outside subset; B2-B6 change no schema, lifecycle, deployment, production module, or moved module; B7 uses all seven evenly spaced renders; B8 does not present fitted points or zero direct-reference drift as independent; B9 uses per-frame boxes; B10 moves no bar. Q does not apply to this tracking measurement row.

NOT VERIFIED: automatic calibration (this consumes one hand label; automatic remains 0/17); ground truth and label repeatability beyond G140's 11.39 px p90; longer/cross-camera/cut/zoom horizon; detector correctness, identity, or localisation accuracy; repeatability of the one eye check; and any population labels-per-hour rate. Plausibility is necessary, never sufficient.
