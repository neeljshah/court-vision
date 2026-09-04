# G243b: Amateur High-School Seed Gate

CLUSTERED SEED RENDER: FAIL -- independent arc, sidelines, and visible centre-circle geometry do not align.

SPREAD SEED RENDER: FAIL -- independent arc, sidelines, and visible centre-circle geometry do not align.

**VERDICT: CLOSED AT LIMIT.** Both mandated seed gates fail for n=1 clip, 1 seed, 2 label sets, and 3 independent labellings. Per G243b's hard stop, no direct-to-seed propagation, matcher/inlier/RMS series, detector projection, in-court fraction, or labels-per-hour calculation was run. This is a measurement result, not a tuning prompt.

This measurement-only row follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changed no production module, threshold, coordinate contract, matcher setting, daemon, keeper, corpus source, `src/`, or `domains/` file.

## Lane hold, source premise, and disk guard

I began at 2026-09-04 05:00:59 -05:00 in `C:\Users\neelj\nba-track-a6`, branch `track-a6`. Immediately beforehand, the exact executable-and-argument check found `pythonw.exe` PID 18132 running tag `g241b_seed_horizon_to_failure` with cwd `C:/Users/neelj/nba-track-a5`; it was not interrupted. That was the permitted second measurement lane. Permanent residents were not touched.

Before any fit, I re-measured the mandatory source on the declared pod corpus machine:

| Field | Independently measured value |
|---|---|
| Exact source path | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Byte size | 24,523,745 |
| SHA-256 | `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` |
| ffprobe identity | 1280x720; 30/1 fps; 120.100000 s; 3,601 decoded video frames (`-count_frames`) |

`df` was not used. The binding pod probe `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g243b_disk_probe.bin bs=1M count=1 conv=fsync status=none` passed, wrote 1,048,576 bytes, and was removed. `du -sm /workspace/nba-ai-system/data` was 33,024 MB. The two abandoned partials were observed but not changed: `baseball__npb_05.mp4.part`, 2,490,710,544 bytes, 2026-09-04 03:38:36 UTC; and `football__football_m8UWuQoflJo.mp4.part`, 4,999,500,276 bytes, 2026-09-04 03:25:21 UTC.

For frame-exact local inspection only, the verified source was copied under the committed artifact directory. The disposable source copy, visual survey, candidate frames, and label views were deleted after gate review: 29,615,737 bytes freed. No corpus source was deleted.

## Court model and seed

`scripts/platformkit/tracking/g196_homography_from_labelled_corners.py: court_points_for_sport` has exactly two accepted keys:

| Key | Returned ordered paint points, ft | Assumption |
|---|---|---|
| `ncaa_basketball` | `[(19,0),(31,0),(19,19),(31,19)]` | 94x50 ft, 12-ft lane, 19-ft paint depth |
| `wnba` | `[(17,0),(33,0),(17,19),(33,19)]` | 94x50 ft, 16-ft lane, 19-ft paint depth |

Neither key was used. The source footage is a high-school gym view (school-team scoreboard, school gym markings, and a visibly narrow high-school lane), so this row uses its own explicit high-school model: x=0..50 ft across court and y=0..84 ft baseline-to-baseline, a 12-ft lane, 19-ft paint depth, 6-ft centre circle radius, and 19 ft 9 in three-point radius. The scoring extent would therefore have been 84x50 ft, not either existing 94-ft model. The footage supports the high-school classification and lane choice; it is not a tape-measure ground truth of dimensions.

The seed is zero-based frame 2760, selected from a half-second, whole-clip visual survey because it has the clearest available left paint, both sidelines, an independent three-point arc, and a substantial visible centre-circle segment. It was decoded frame-exactly with `ffmpeg -i VIDEO -vf select=eq(n\,2760) -vsync 0 -frames:v 1 -f rawvideo -pix_fmt bgr24 pipe:1`, with no input-side `-ss`; the retained exact decode is [seed_frame_2760.jpg](g243b_seeded_calibration_amateur_2026-09-04_artifact/seed_frame_2760.jpg).

At 1280x720, this source has fewer pixels per foot than G233d's 1920x1080 broadcast source. Thus a pixel error here is a larger real-world error; the pixel figures below must not be compared directly with G233d without that caveat.

## Three independent labellings and both gates

Each row below was labelled from a fresh view of the same exact seed before render review. Labelling 1 is the fitted input; no label was adjusted after a gate result. The clustered set is the four paint corners. The spread set uses both paint-free-throw corners and the top/bottom of the centre circle, deliberately wider in the visible court geometry.

| Set / labelling | Four image points in role order, px |
|---|---|
| Clustered 1 (fit) | `(45,385) (283,276) (363,424) (624,306)` |
| Clustered 2 | `(48,382) (280,279) (366,420) (620,309)` |
| Clustered 3 | `(42,388) (287,273) (358,427) (628,302)` |
| Spread 1 (fit) | `(363,424) (624,306) (1140,359) (1160,468)` |
| Spread 2 | `(366,420) (620,309) (1137,362) (1164,464)` |
| Spread 3 | `(358,427) (628,302) (1144,356) (1156,472)` |

Per-point maximum pairwise label spreads are clustered `8.485, 9.220, 10.630, 10.630 px` (median 9.925 px, max 10.630 px) and spread `10.630, 10.630, 9.220, 11.314 px` (median 10.630 px, max 11.314 px). Both maxima are below G140's 11.39 px p90, but that is repeatability only, never geometry correctness.

The fitted primary self-fit round-trip RMS is 0.000000000 px for both sets because exactly four inputs determine the homography. It is included only to make its degeneracy explicit and is not evidence. The alternate labelings retain the same eye verdicts: clustered FAIL / FAIL and spread FAIL / FAIL. Relative to the labelling-1 projected four points, the alternate-label RMS values are clustered 4.637 and 5.220 px; spread 5.000 and 5.545 px. Thus neither verdict moves, while the label sensitivity is recorded rather than hidden.

The six retained gate renders are [clustered 1](g243b_seeded_calibration_amateur_2026-09-04_artifact/clustered/render_labelling_1.jpg), [clustered 2](g243b_seeded_calibration_amateur_2026-09-04_artifact/clustered/render_labelling_2.jpg), [clustered 3](g243b_seeded_calibration_amateur_2026-09-04_artifact/clustered/render_labelling_3.jpg), [spread 1](g243b_seeded_calibration_amateur_2026-09-04_artifact/spread/render_labelling_1.jpg), [spread 2](g243b_seeded_calibration_amateur_2026-09-04_artifact/spread/render_labelling_2.jpg), and [spread 3](g243b_seeded_calibration_amateur_2026-09-04_artifact/spread/render_labelling_3.jpg). Their inputs and matrices are retained in [measurement.json](g243b_seeded_calibration_amateur_2026-09-04_artifact/measurement.json).

Both geometry constructions visibly miss the independent painted arc and sidelines, and their projected centre-circle geometry fails to land on the visible circle. The red point markers are fitted inputs, not evidence. There is no useful split: both fail. I therefore stopped before G222 propagation. The 3,601-frame whole-clip bound was not reached; this is a gate failure at distance zero, not an acceptance-based horizon claim.

G242 remains controlling: G222's literal acceptance condition accepted 89 of 89 whole-game sampled frames, including replays, graphics, and the wrong hoop end. Match counts, inliers, inlier ratio, and RMS would not establish a correct court; only renders can do that. This row reports no hold based on acceptance.

## Comparison with G233d

| Quantity | G233d WNBA broadcast | G243b amateur high-school |
|---|---:|---:|
| Source / resolution | WNBA, 1920x1080 | Amateur high-school, 1280x720 |
| Court model | 94x50 ft, 16-ft lane | 84x50 ft, 12-ft lane |
| Seed gate | PASS | Clustered FAIL; spread FAIL |
| Direct horizon | 1,200 frames tested | 0; stopped at seed, not the 3,601-frame bound |
| Direct inliers / RMS | 421-1,848 / 0.299365-0.702623 px | Not run by hard stop |
| In-court fraction | one detector draw, approximately 0.83-0.92 by band | Not run by hard stop |

This n=1 result says the observed amateur seed construction is harder than G233d's successful broadcast construction. It does not establish a property of amateur footage generally, and the lower 720p resolution means a same-size pixel error would imply more real-world error here.

## Verifier self-check and limitations

Focused test: `python -m pytest scripts/platformkit/tracking/test_g243b_amateur_seed_gate.py -q -p no:cacheprovider` -> `2 passed`.

Contract self-check: A7 evidence paths above exist in this commit. B1 has no propagated denominator because the hard stop precluded one; B2-B6 change no schema, lifecycle, deployment, production module, or moved module; B7 reviews all six gate renders, not a head slice; B8 explicitly excludes the self-fit RMS and fitted inputs as evidence; B9 does not recycle a denominator; B10 changes no threshold or matcher. Q does not apply to this tracking measurement row. The new row-local harness is 137 lines and does not grow an allowlisted shared file, so A12 does not apply.

NOT VERIFIED: a passing amateur seed on another frame, clip, camera, or labeller; automatic calibration (still 0/17); ground-truth court dimensions; any propagation, matcher behavior, detector projection, in-court fraction, or labels-per-hour rate; repeatability beyond this one labeller; and any population comparison between amateur and broadcast footage. Plausibility is necessary, never sufficient, and this row did not achieve it.
