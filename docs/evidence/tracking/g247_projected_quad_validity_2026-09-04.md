# G247: Projected court-quad validity from a G242-exact replay

## Verdict

**ACCEPT (measurement only): no pre-registered projected-quad check separates the G244 VALID and INVALID classes on the exact 89-frame G242 replay.** The control reproduced G242's match and inlier count at every named frame (89/89 exact, zero mismatches). Convexity, winding, corner ordering, projected area, bounding-box aspect ratio, out-of-bounds corners, and matrix condition number all have explicit VALID/INVALID range overlap below. No threshold was fit, tested, or proposed.

This closes G244's retention gap, not its negative. With G242's literal-match result and G244's retained-diagnostic negative, no available signal in this one-clip experiment indicates court validity; every hold claim remains render-bound. The 89-frame denominator is one clip, one seed, one arena, and one labeller's blind labels. No clean in-sample separation occurred, so the spec's conditional out-of-sample labeling and confirmation step was not triggered.

## Lane, source identity, and disk guard

I began at 2026-09-04 05:42:01 -05:00 after checking `track-a6`: G246 was already landed at `891ff3132`, and I did not interrupt it. A pod process listing by executable and full argument showed the permanent residents plus one active S256 measurement; a second lane was free, satisfying the N=2 limit. No pod code was deployed: the worker was sent on stdin and retained only its named temporary JSON.

The required guard ran before the worker created its temporary artifact: `du -sm /workspace/nba-ai-system/data` reported 33051 MB. The authoritative `dd if=/dev/zero of=/workspace/nba-ai-system/g247_disk_probe.bin bs=1M count=1 conv=fsync` probe passed; its 1,048,576-byte probe was removed. The worker's 93,494-byte temporary JSON was copied and then removed. No corpus source, render, G242 12.4 MB artifact, or either abandoned `footage_bridge` partial was deleted. The committed G247 artifact is 142,822 bytes.

| Input opened | Full path | Bytes | Resolution / role |
|---|---|---:|---|
| Video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080; 174,430 declared frames; read-only pod corpus |
| G236b reference | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g236b_reindex_validated_frame_artifact\best_match_1920x1080.jpg` | 623,686 | 1920x1080; exact seed-decode reference |
| G140 labels | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g140_corner_targets\corner_pixel_targets.csv` | 15,633 | Four native 1920x1080 labels at scale 1.0 |
| G242 control table | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g242_seed_reacquisition_whole_game_artifact\per_sample_table.csv` | 8,834 | 89 named expected match/inlier pairs; SHA-256 `469a4a70683515077279f55c055c7ce06e26d17269deecd630b5aa34ac179146` |
| G244 blind labels | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g244_blind_validity_labels_2026-09-04.csv` | 8,114 | 89 committed blind labels; SHA-256 `c95071bc687eaff41b30dc46d635f4a835421a3f16e117a7988c6547cfbfdadf` |
| G196 route blob | `C:\Users\neelj\nba-track-a3\scripts\platformkit\tracking\g196_homography_from_labelled_corners.py` | 16,321 | Read-only exact G242 source; SHA-256 `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3` |
| G215 route blob | `C:\Users\neelj\nba-track-a3\scripts\platformkit\tracking\g215_temporal_homography_propagation.py` | 8,158 | Read-only exact G242 source; SHA-256 `b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a` |
| G222 route blob | `C:\Users\neelj\nba-track-a3\scripts\platformkit\tracking\g222_direct_to_seed_propagation.py` | 7,296 | Read-only exact G242 source; SHA-256 `2b99a30f3ff6dd1d633e0d088dee150c379f655e2fb78556589b5a948743d8c4` |

The current a5 copies of G196 and G215 have different bytes. The worker deliberately refused them and streamed the exact G242-identified read-only blobs above; this prevented source drift from being silently called a replay.

## Exact G242 control

The construction is unchanged: seed frame 19599; labels `(350,400)`, `(835,420)`, `(390,696)`, `(990,730)` at scale 1.0; `court_points_for_sport("wnba")` equals `[(17,0),(33,0),(17,19),(33,19)]`; ORB `nfeatures=2000, fastThreshold=12`; Hamming ratio `< 0.75`; at least four matches; `cv2.findHomography(..., RANSAC, 3.0)`; finite motion; and one sequential decode of frames 0 through 174429, sampled at stride 2000 through 174000 plus the explicit seed.

The seed image-to-court matrix equals G242's published matrix to maximum absolute difference 0.0. The independent frame-100000 re-decode had BGR MAD 0.0 against the sequential image; the sequential seed had MAD 0.0 against the exact seed and the G236b reference MAD was 1.087048. **All 89/89 per-frame match and inlier pairs equal the committed G242 control table, with zero mismatches.** The control is stated first because a mismatch would have stopped this row before geometry analysis.

## Retained geometry and check definitions

The [artifact](g247_projected_quad_validity_artifact/g247_measurement.json) retains every 3x3 image-to-court homography, four projected corners in G196 role order, direct diagnostics, control comparison, all derived check values, input hashes, and the class summaries. It retains no overlay or video duplicate.

The source role order is `[near baseline left, near baseline right, near free-throw left, near free-throw right]`; the perimeter order used only for polygon operations is the fixed index order `[0,1,3,2]`. Convexity requires four nonzero same-signed consecutive cross products. Signed area uses the shoelace formula on that perimeter; winding inversion is a sign change from the seed. Corner ordering is consistent only when the perimeter is finite, unique, convex, and has seed winding. Projected area ratio is absolute signed area divided by seed absolute signed area. Bounding-box aspect ratio is x-span/y-span. An outside corner has x outside `[0,1920)` or y outside `[0,1080)`. Condition number uses the 3x3 image-to-court matrix normalized by its `[2,2]` entry.

For Boolean rows below, 1 means true and 0 means false. CANNOT_JUDGE remains its own class and is not used in any VALID/INVALID overlap count.

| Check / retained field | Class | n | Min | Median | P90 | Max |
|---|---|---:|---:|---:|---:|---:|
| Convexity (`is_convex`) | VALID | 27 | 1 | 1 | 1 | 1 |
| Convexity (`is_convex`) | INVALID | 28 | 1 | 1 | 1 | 1 |
| Convexity (`is_convex`) | CANNOT_JUDGE | 34 | 1 | 1 | 1 | 1 |
| Signed area px2 | VALID | 27 | 157807.783 | 161503.322 | 164123.579 | 182508.010 |
| Signed area px2 | INVALID | 28 | 125679.027 | 161247.077 | 165148.213 | 187168.435 |
| Signed area px2 | CANNOT_JUDGE | 34 | 91689.337 | 161256.213 | 166891.859 | 451733.316 |
| Winding inverted relative to seed | VALID | 27 | 0 | 0 | 0 | 0 |
| Winding inverted relative to seed | INVALID | 28 | 0 | 0 | 0 | 0 |
| Winding inverted relative to seed | CANNOT_JUDGE | 34 | 0 | 0 | 0 | 0 |
| Corner order consistent with seed | VALID | 27 | 1 | 1 | 1 | 1 |
| Corner order consistent with seed | INVALID | 28 | 1 | 1 | 1 | 1 |
| Corner order consistent with seed | CANNOT_JUDGE | 34 | 1 | 1 | 1 | 1 |
| Projected area ratio to seed | VALID | 27 | 0.975658 | 0.998506 | 1.014706 | 1.128369 |
| Projected area ratio to seed | INVALID | 28 | 0.777020 | 0.996922 | 1.021041 | 1.157182 |
| Projected area ratio to seed | CANNOT_JUDGE | 34 | 0.566876 | 0.996978 | 1.031821 | 2.792873 |
| Bounding-box aspect ratio | VALID | 27 | 1.802000 | 1.943124 | 1.958523 | 1.968958 |
| Bounding-box aspect ratio | INVALID | 28 | 1.733011 | 1.943857 | 2.063147 | 2.362922 |
| Bounding-box aspect ratio | CANNOT_JUDGE | 34 | 0.968034 | 1.941140 | 2.095335 | 2.280947 |
| Outside-corner fraction | VALID | 27 | 0 | 0 | 0 | 0 |
| Outside-corner fraction | INVALID | 28 | 0 | 0 | 0 | 0 |
| Outside-corner fraction | CANNOT_JUDGE | 34 | 0 | 0 | 0 | 0.25 |
| Homography condition number | VALID | 27 | 9609.184 | 12810.706 | 13241.339 | 13518.295 |
| Homography condition number | INVALID | 28 | 8552.119 | 12827.342 | 16219.556 | 21143.176 |
| Homography condition number | CANNOT_JUDGE | 34 | 5402.321 | 12782.844 | 18787.126 | 31897.328 |

The overlap, rather than the medians, answers every pre-registered check:

| Check | INVALID range | VALID values inside INVALID range | VALID range | INVALID values inside VALID range |
|---|---|---:|---|---:|
| Convexity (1=true) | 1 to 1 | 27/27 | 1 to 1 | 28/28 |
| Signed area px2 | 125679.027 to 187168.435 | 27/27 | 157807.783 to 182508.010 | 21/28 |
| Winding inverted (1=true) | 0 to 0 | 27/27 | 0 to 0 | 28/28 |
| Corner order consistent (1=true) | 1 to 1 | 27/27 | 1 to 1 | 28/28 |
| Projected area ratio to seed | 0.777020 to 1.157182 | 27/27 | 0.975658 to 1.128369 | 21/28 |
| Bounding-box aspect ratio | 1.733011 to 2.362922 | 27/27 | 1.802000 to 1.968958 | 22/28 |
| Outside-corner fraction | 0 to 0 | 27/27 | 0 to 0 | 28/28 |
| Homography condition number | 8552.119 to 21143.176 | 27/27 | 9609.184 to 13518.295 | 21/28 |

There is no clean separation. The signed-area/winding group is one of the seven preregistered checks; its numeric signed-area result and its required inversion result are both shown so neither is silently omitted. No INVALID map inverted, lost convexity, changed the retained order, or placed a projected corner outside the image. Differences in medians or in CANNOT_JUDGE extrema do not alter the overlap result.

## Multiple comparisons, out of sample, and limitations

This is seven check groups against 89 in-sample frames, with only 27 VALID and 28 INVALID labels. With seven comparisons, one apparent good result could occur by chance; it would not be a discovery without confirmation. Here none even has a clean in-sample range separation, so no threshold is fit and no same-frame accuracy is reported. Because there is no clean separation, no fresh frames were selected and no out-of-sample labels were created; an out-of-sample exercise is required only to confirm a clean in-sample separation, not to select one after the fact.

The limits remain material: one clip, one seed, one arena, wide stride samples, and one G244 labeller rather than ground truth. Eye-label reliability in this programme has never cleared 80 percent blind agreement on any of four measured criteria. CANNOT_JUDGE is 34/89 and was never merged into either geometry class. Nothing here bears on automatic calibration, which remains 0/17. G242 remains controlling: literal G222 acquisition is not a validity signal.

**NOT VERIFIED:** ground truth; a repeat measurement; a second labeller; another seed, clip, arena, camera, or sport; dense frames between stride samples; a geometry-validity threshold or production gate; automatic calibration; and any claim beyond this retained one-clip negative.

## Verification and contract self-check

Focused test run:

```text
python -m pytest scripts/platformkit/tracking/test_g247_projected_quad_validity.py -q -p no:cacheprovider
5 passed in 1.77s
```

No full suite was run. A7: every named evidence path exists in this landing. B1: all 89 named control rows and all 89 blind labels are retained; no row was excluded. B2-B6: no production schema, lifecycle, deployment, reader contract, or moved module changed. B7: the complete G242 stride-2000 denominator is used, not a head slice. B8: fitted four-corner residuals are not presented as evidence; the checks are class summaries of inverse-projected court shape. B9: denominators are 89 unique source frames, partitioned 27/28/34. B10: matcher, seed, court model, and acceptance settings are unchanged. Q does not apply to this tracking measurement. The new route and its focused test are below the 300-LOC rail, so A12 does not require a shared-rail adjustment.
