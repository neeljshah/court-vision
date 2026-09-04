# G233 basketball seeded court coordinates

## Verdict: CLOSED AT LIMIT (measurement only)

The direct-to-seed map was finite on all 1,201 decoded frames from source frame 1600 through 2800. Of 2,927 projected direct-detector person feet, 2,415 (82.5077 percent) landed inside the declared 94 by 50 foot rectangle. That fraction is necessary descriptive evidence, never sufficient. The evenly spaced eye check finds that the rendered court model does not visibly remain on the painted court at the seed itself. This run therefore does not establish physically sensible basketball court positions or a nonzero usable propagation horizon. It is not an accuracy result.

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A and B. It changes no production code, adapter, coordinate contract, tracking directory, threshold, or bar. The pod route was not run: G211b's zero-row route result was not retried. The detector was called directly.

## Machine, hold check, source, and code identity

S1 machine: this measurement ran on the pod because the required native corpus source is there. At `2026-09-04T06:05:49Z`, before the probe or measurement, the process census found `keep_track_daemon.sh`, `track_daemon`, `inplay_capture_runner`, and `foundry_runner`; it found no `G###`, measurement, or `run_clip` job. Those permanent residents were neither waited on, stopped, restarted, nor overwritten.

The sole source opened read-only was `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`: 2,931,985,407 bytes, 1920x1080, 30 fps, and 174,430 frames. The run decoded source frames 1600 through 2800 inclusive. It used the direct YOLO person detector at confidence 0.35 every third frame plus the seven render frames, for 405 detector samples. It did not use tracking identities or a route output.

The exact local G196, G215, G222, and G233 sources were streamed to standard input of the pod Python process; no harness file was copied into the pod checkout. The remote detector source was imported read-only.

| Source | SHA-256 |
|---|---|
| `scripts/platformkit/tracking/g196_homography_from_labelled_corners.py` | `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3` |
| `scripts/platformkit/tracking/g215_temporal_homography_propagation.py` | `b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a` |
| `scripts/platformkit/tracking/g222_direct_to_seed_propagation.py` | `2b99a30f3ff6dd1d633e0d088dee150c379f655e2fb78556589b5a948743d8c4` |
| `scripts/platformkit/tracking/g233_basketball_seeded_court_coordinates.py` | `c2c4a7d7b1b3e3efdc175c8613f5b118bf818c4f04ff2509632e78123b5d14f7` |
| `/workspace/nba-ai-system/src/tracking/player_detection.py` | `c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7` |

## Fixed seed and direct measurement

G196 seed construction was reused unchanged. The seed is `wnba__wnba_01_1080p__s01__f001600`, source frame 1600. Its four image points are `[(350,400), (835,420), (390,696), (990,730)]`. The unchanged `court_points_for_sport("wnba")` construction uses the 16-foot lane, not the NCAA 12-foot lane: `[(17,0), (33,0), (17,19), (33,19)]` feet. The obtained image-to-court homography is:

```text
[[ 0.0500717550,  0.0122540472,   2.3351407384],
 [-0.0047586809,  0.1153980130, -44.4936668603],
 [ 0.0000305449,  0.0011147253,   1.0000000000]]
```

Each decoded frame was matched direct-to-seed through G222's unchanged ORB, ratio-test, and RANSAC arithmetic. The geometry was eligible on 1,201 of 1,201 decoded frames. The direct detector's every class-0 box foot was projected with that frame map. Its bounding-box-bottom foot convention is a detector approximation, not a hand label and not ground truth.

## G230-style in-court and distance-outside distributions

The eligible denominator is every projected direct-detector person foot: 2,927 projections. No detection was removed for being outside the rectangle. Distance outside is the Euclidean distance to the 94 by 50 foot rectangle, zero for an inside projection, exactly as G230's descriptive vocabulary requires (with the basketball plane substituted for tennis's 78 by 36 foot plane).

| Span | Projected detections | Inside rectangle | In-court fraction | Outside distance ft: median / p90 / p99 / max |
|---|---:|---:|---:|---|
| All 405 detector samples, frames 1600-2800 | 2927 | 2415 | 82.5077% | 4.174 / 14.346 / 18.162 / 39.416 |
| Distance 0 | 9 | 9 | 100.0000% | none |
| Distance 200 | 13 | 9 | 69.2308% | 2.324 / 8.326 / 10.226 / 10.437 |
| Distance 400 | 4 | 4 | 100.0000% | none |
| Distance 600 | 12 | 10 | 83.3333% | 3.741 / 5.475 / 5.865 / 5.908 |
| Distance 800 | 5 | 4 | 80.0000% | 1.837 / 1.837 / 1.837 / 1.837 |
| Distance 1000 | 4 | 4 | 100.0000% | none |
| Distance 1200 | 9 | 9 | 100.0000% | none |

The all-span outside distribution has 512 nonzero distances. The numerator and denominator include detector person boxes in the crowd, bench, broadcast lower third, and court; their presence is not silently treated as a geometry failure or excluded from the fraction. Thus the fraction is descriptive of this direct detector output, not a player-only correctness rate.

## Evenly spaced eye check

Yellow is the inverse-projected G196 court model and red is a direct-detector foot with its projected court coordinates. The seven frames are evenly spaced over the complete 1,200-frame decision interval. A red mark can be visibly near a player while still have a wrong court coordinate, so these are single-labeller plausibility judgements, not accuracy labels.

| Distance | Render | Observation |
|---:|---|---|
| 0 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_0000.jpg) | The four fitted-corner overlay itself does not visibly trace the painted near key; its upper edge is in seating/bench space. |
| 200 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_0200.jpg) | The visible yellow near-key geometry remains displaced from the painted key. |
| 400 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_0400.jpg) | The overlay is still off the visible painted court; no recovery is visible. |
| 600 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_0600.jpg) | The yellow court lines remain displaced from the painted key and baseline area. |
| 800 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_0800.jpg) | The visible court model remains off the painted markings. |
| 1000 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_1000.jpg) | The same mismatch remains; this is not a later detector-only decay. |
| 1200 | [render](g233_basketball_seeded_court_coordinates_artifact/renders/render_distance_1200.jpg) | The model is still visibly displaced from the painted court. |

The painted-court eye check therefore comes off at distance 0, not after a positive propagation distance. The numerical direct map remains finite to 1200, but a finite transform and an in-rectangle fraction cannot rescue an overlay that is visibly off the court. The correct observed useful horizon is zero frames for this source/seed pairing.

## Labels-per-hour consequence

At 30 fps, one hour is `30 * 60 * 60 = 108000` frames. A finite label rate needs a positive eye-checked horizon `N`, using `ceil(108000 / N)` independent seeds per hour under the stated repeated-horizon assumption. Here `N = 0`, so the calculation is undefined and no finite labels-per-hour figure is supported. The G222 1,200-frame image-feature horizon cannot be used for player-foot coordinates on this evidence.

## Disk guard and cleanup

Before measurement, `du -sm /workspace/nba-ai-system/data` was 31,715 MiB; no `df` result was used. An initial shell-quoting attempt did not complete its probe cleanup, so it was treated as a failed guard: the exact probe path was then confirmed absent before any measurement. Two subsequent 4 MiB `dd if=/dev/zero ... bs=1M count=4 conv=fsync` probes each passed and were removed (`4,194,304` bytes each). The pod measurement directory was `/workspace/nba-ai-system/.g233_measurement`, outside every tracking directory; it was copied back before deletion and removed after measuring 5,612,008 bytes. The reported freed temporary bytes are `8,388,608 + 5,612,008 = 14,000,616`. The final pod check found that directory absent. Its data-volume reading after cleanup was 31,790 MiB; resident work may change that descriptive reading.

## Contract self-check and NOT VERIFIED

B1: all 2,927 projected direct-detector boxes are named in the denominator; the 512 outside boxes are retained. B2-B4: no existing schema, status, reader, or claim lifecycle changed. B5: no file was deployed to the pod checkout. B6: no module moved. B7: all seven equally spaced render distances are retained. B8: the exact four-point seed fit is not presented as independent evidence. B9: the denominator is individual direct detector boxes with their source-frame records, not recycled track IDs. B10: G196/G222 seeds, court model, and all method parameters were retained. A7: this memo, `records.json`, and every listed render exist in the committed artifact. A12: the added harness is 168 LOC, below the 300-LOC rail, and the rail test passes.

This consumes a hand label and is therefore not automatic calibration; automatic anchors remain 0/17. Plausibility is necessary, never sufficient, and none is claimed as accuracy. NOT VERIFIED: why this pod/source-frame seed visibly disagrees with the G196/G222 eye-check interpretation; player-foot ground truth; which class-0 detector boxes are players rather than spectators or officials; repeatability of this non-deterministic route-free detector invocation; any second clip, seed, camera, cut, replay, zoom change, or future frame; and any production adapter integration.
