# G233 basketball seeded court coordinates

## Verdict: CLOSED AT LIMIT (measurement only)

The direct-to-seed map was finite on all 1,201 decoded frames from source frame 1600 through 2800, but the eye check shows the inverse-projected court model visibly off the painted near court at distance 0. The useful horizon is therefore zero frames for this source/hand-label pairing. This is not an accuracy result.

The direct detector projected 11,478 class-0 box-bottom feet. Of these, 9,433 (82.1829 percent) were inside the declared 94 by 50 foot rectangle; 2,045 had positive outside distance. This fraction is necessary descriptive evidence, never sufficient: it includes spectators, officials, and lower-third detections as well as players. The pod route was not run; G211b's zero-row route outcome was not retried.

## Method, source, and code identity

The pod was used because it hosts the read-only native source `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` (2,931,985,407 bytes, 1920x1080, 30 fps, 174,430 frames). At `2026-09-04T06:08:16+00:00`, the census found only the permanent keeper/daemon, in-play capture, and foundry residents; none was waited on, stopped, restarted, overwritten, or deployed.

G196 seed construction was unchanged: source frame 1600, image points `[(350,400), (835,420), (390,696), (990,730)]`, and WNBA 16-foot-lane points `[(17,0), (33,0), (17,19), (33,19)]`. Homography:

```text
[[0.0500717550, 0.0122540472, 2.3351407384], [-0.0047586809, 0.1153980130, -44.4936668603], [0.0000305449, 0.0011147253, 1.0000000000]]
```

G222's direct-to-seed feature arithmetic was reused unchanged; the direct `FeetDetector` class-0 call projected every box-bottom foot, without tracking identities or route output. Local sources were streamed over standard input only. The source and route hashes, input identity, and pod disk baseline are retained in [context](g233_basketball_seeded_court_coordinates_a3_artifact/context.txt).

## G230-style descriptive distribution

Every finite box projection is retained in the denominator. Positive outside distance is Euclidean distance to the 94 by 50 foot court rectangle.

| Frames from seed | Projections | Inside | Fraction | Outside ft median / p90 / p99 / max |
|---|---:|---:|---:|---|
| 0-199 | 2088 | 1903 | 91.1398% | 4.591 / 13.145 / 39.094 / 39.416 |
| 200-399 | 1879 | 1575 | 83.8212% | 2.573 / 17.164 / 17.847 / 17.915 |
| 400-599 | 1674 | 1316 | 78.6141% | 4.926 / 17.686 / 17.883 / 17.901 |
| 600-799 | 2158 | 1732 | 80.2595% | 5.111 / 16.494 / 19.290 / 31.971 |
| 800-999 | 1689 | 1386 | 82.0604% | 2.722 / 8.660 / 9.231 / 10.320 |
| 1000-1199 | 1979 | 1511 | 76.3517% | 4.474 / 14.119 / 19.932 / 24.370 |
| 1200 | 11 | 10 | 90.9091% | 1.714 / 1.714 / 1.714 / 1.714 |

## Eye check, labels, and guard

The yellow court model is visibly displaced from painted near-key geometry at [0](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_0000.jpg) and remains displaced at evenly spaced [200](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_0200.jpg), [400](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_0400.jpg), [600](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_0600.jpg), [800](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_0800.jpg), [1000](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_1000.jpg), and [1200](g233_basketball_seeded_court_coordinates_a3_artifact/renders/render_distance_1200.jpg). Thus it comes off at the seed, not later.

At 30 fps, labels per hour is `ceil(108000 / N)`. With eye-checked `N=0`, no finite number is supported; G222's image-feature horizon cannot be applied to player-foot coordinates. Before this run, `du -sm` was 31,818 MiB; `df` was not used. The 4 MiB `dd conv=fsync` guard passed and was removed before output. Its 8,194,490-byte pod artifact was copied back then removed, so 12,388,794 bytes were freed. No corpus source changed.

## Contract self-check and NOT VERIFIED

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`: B1 retains all finite projections; B2-B6 make no schema, lifecycle, deployment, or module change; B7 retains evenly spaced renders; B8 does not treat the four-point fit as independent evidence; B9 uses individual detector boxes; and B10 preserves all fixed values. A7 paths exist: [measurement](g233_basketball_seeded_court_coordinates_a3_artifact/measurement.json), context, and seven renders. A12 does not apply; focused and LOC-rail tests pass.

This consumes a hand label and is not automatic calibration; automatic anchors remain 0/17. Plausibility is necessary, never sufficient, and no accuracy is claimed. NOT VERIFIED: ground truth, player-vs-spectator semantics, repeatability, other clips/seeds/cameras/cuts/zooms, and production adapter integration.
