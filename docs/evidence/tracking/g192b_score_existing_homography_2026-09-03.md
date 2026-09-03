# G192b - existing homography direct-score measurement

**Result: the specified direct solver route produced no homography on this
construct.** This is a measurement result, not a zero-error result and not an
assessment that the static fallback is a good homography.

## Construct and method

- `n = 68 targets over 17 frames (CONSTRUCT, exhaustive)`.
- Reconfirmed locally before the pod run: all 68 target rows resolved to 17
  extant JPEGs; CSV dimensions equalled JPEG dimensions for all 17 (zero
  mismatches). No JPEG was resized, label was rescaled, target was excluded, or
  source video was sought.
- Each JPEG was copied only to `/tmp/g192b_inputs_20260903` on the pod and was
  supplied, alone, as `detect_court_homography([image])`. The function imported
  was the existing `src.tracking.court_detector.detect_court_homography`, which
  `unified_pipeline.py` imports at line 330. Its current direct implementation
  is the Hough-line route and returns `None` on failure; it did not invoke
  LoFTR or SIFT in this call path. The static `Rectify1.npy` fallback was not
  substituted, because it is not a returned solve from the requested route.
- B11 repeat: three separate `python3` processes per JPEG on the pod, for 51
  calls total. The raw pod result JSONL SHA-256 was
  `bb13828b9756b3f9ff1c4400d161425cd95b60f5fb0450ae106abd52e2f4a7c6`.
  All 51 calls returned `None`.
- The pod was read-only apart from these bounded `/tmp` inputs, runner, and
  result file. No daemon, keeper, deployment, pipeline source, solver constant,
  corpus file, coordinate contract, gate, bar, or verdict was changed.

## Code identity: pod (A11)

| File | SHA-256 on pod |
|---|---|
| `src/pipeline/unified_pipeline.py` | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `src/tracking/advanced_tracker.py` | `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7` |
| `src/tracking/court_detector.py` (called route, additional identity) | `375d263185a44ea15896ac36906b7a2e846c06fa8a97915d915e73d9e2b58b56` |

## Input inventory (A9)

The earlier all-640x360 premise is not repeated: every row below names its
native JPEG path and its actual native resolution.

| Audit ID | Full input decode path | Native resolution | Targets |
|---|---|---:|---:|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg` | 640x360 | 4 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg` | 1280x720 | 4 |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg` | 1280x720 | 4 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s01__f001600` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s01__f001600.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s03__f004062` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s03__f004062.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s06__f007539` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s06__f007539.jpg` | 1920x1080 | 4 |
| `wnba__wnba_02__s11__f021983` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_02__s11__f021983.jpg` | 1280x720 | 4 |
| `wnba__wnba_04__s06__f012223` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_04__s06__f012223.jpg` | 1280x720 | 4 |
| `wnba__wnba_06__s03__f007237` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s03__f007237.jpg` | 1920x1080 | 4 |
| `wnba__wnba_06__s07__f014099` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s07__f014099.jpg` | 1920x1080 | 4 |
| `wnba__wnba_06__s09__f018997` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s09__f018997.jpg` | 1920x1080 | 4 |
| `wnba__wnba_07__s08__f016801` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_07__s08__f016801.jpg` | 1920x1080 | 4 |

## Solver coverage and stability

| Native resolution | Frames | Targets | Frames solved at least once | Runs returning a matrix | Median / p90 / at or below 11.39 px |
|---|---:|---:|---:|---:|---|
| 1920x1080 | 12 | 48 | 0 | 0/36 | N/A: zero projected targets |
| 1280x720 | 4 | 16 | 0 | 0/12 | N/A: zero projected targets |
| 640x360 | 1 | 4 | 0 | 0/3 | N/A: zero projected targets |
| **Pooled (resolution-mixed; pixel scales are not comparable)** | **17** | **68** | **0** | **0/51** | **N/A: zero projected targets** |

The unsolved-frame count is **17/17**. All 17 three-run groups were stable in
the only observable sense: the state was `None/None/None` each time. There is
no numerical homography for which matrix stability can be assessed.

The pooled error metrics and the count inside the 11.39-px G140 repeatability
floor are **undefined**, not 0: none of the 68 target points had a projection.
Consequently no comparison to the label-noise floor is possible. This preserves
the full denominator rather than turning the unsolved frames into an invisible
zero-target subset.

## Per-target records (B13/Q9)

`projected_px = null` and `error_px = null` mean that all three fresh calls for
that frame returned `None`; no target is excluded.

| Frame | Role | Labelled px | Projected px | Error px | Status |
|---|---|---:|---:|---:|---|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `paint_near_baseline_left_corner` | (38, 223) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `paint_near_baseline_right_corner` | (39, 289) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `paint_near_free_throw_left_corner` | (274, 224) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `paint_near_free_throw_right_corner` | (273, 282) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `paint_near_baseline_left_corner` | (780, 734) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `paint_near_baseline_right_corner` | (1420, 780) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `paint_near_free_throw_left_corner` | (804, 930) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `paint_near_free_throw_right_corner` | (1470, 884) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `paint_near_baseline_left_corner` | (1376, 679) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `paint_near_baseline_right_corner` | (1681, 714) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `paint_near_free_throw_left_corner` | (1353, 831) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `paint_near_free_throw_right_corner` | (1720, 846) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `paint_near_baseline_left_corner` | (530, 420) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `paint_near_baseline_right_corner` | (1100, 435) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `paint_near_free_throw_left_corner` | (550, 680) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `paint_near_free_throw_right_corner` | (1110, 690) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `paint_near_baseline_left_corner` | (123, 396) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `paint_near_baseline_right_corner` | (135, 558) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `paint_near_free_throw_left_corner` | (596, 443) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `paint_near_free_throw_right_corner` | (596, 513) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `paint_near_baseline_left_corner` | (1015, 338) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `paint_near_baseline_right_corner` | (1006, 620) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `paint_near_free_throw_left_corner` | (580, 423) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `paint_near_free_throw_right_corner` | (580, 520) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `paint_near_baseline_left_corner` | (250, 360) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `paint_near_baseline_right_corner` | (286, 645) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `paint_near_free_throw_left_corner` | (720, 535) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `paint_near_free_throw_right_corner` | (725, 700) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `paint_near_baseline_left_corner` | (1600, 380) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `paint_near_baseline_right_corner` | (1620, 640) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `paint_near_free_throw_left_corner` | (865, 475) | null | null | all 3 calls returned None |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `paint_near_free_throw_right_corner` | (900, 620) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s01__f001600` | `paint_near_baseline_left_corner` | (350, 400) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s01__f001600` | `paint_near_baseline_right_corner` | (835, 420) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s01__f001600` | `paint_near_free_throw_left_corner` | (390, 696) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s01__f001600` | `paint_near_free_throw_right_corner` | (990, 730) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s03__f004062` | `paint_near_baseline_left_corner` | (1700, 430) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s03__f004062` | `paint_near_baseline_right_corner` | (1700, 595) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s03__f004062` | `paint_near_free_throw_left_corner` | (950, 483) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s03__f004062` | `paint_near_free_throw_right_corner` | (1010, 610) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s06__f007539` | `paint_near_baseline_left_corner` | (90, 330) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s06__f007539` | `paint_near_baseline_right_corner` | (75, 579) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s06__f007539` | `paint_near_free_throw_left_corner` | (795, 426) | null | null | all 3 calls returned None |
| `wnba__wnba_01_1080p__s06__f007539` | `paint_near_free_throw_right_corner` | (795, 580) | null | null | all 3 calls returned None |
| `wnba__wnba_02__s11__f021983` | `paint_near_baseline_left_corner` | (300, 255) | null | null | all 3 calls returned None |
| `wnba__wnba_02__s11__f021983` | `paint_near_baseline_right_corner` | (960, 265) | null | null | all 3 calls returned None |
| `wnba__wnba_02__s11__f021983` | `paint_near_free_throw_left_corner` | (330, 620) | null | null | all 3 calls returned None |
| `wnba__wnba_02__s11__f021983` | `paint_near_free_throw_right_corner` | (1020, 650) | null | null | all 3 calls returned None |
| `wnba__wnba_04__s06__f012223` | `paint_near_baseline_left_corner` | (100, 280) | null | null | all 3 calls returned None |
| `wnba__wnba_04__s06__f012223` | `paint_near_baseline_right_corner` | (670, 300) | null | null | all 3 calls returned None |
| `wnba__wnba_04__s06__f012223` | `paint_near_free_throw_left_corner` | (140, 600) | null | null | all 3 calls returned None |
| `wnba__wnba_04__s06__f012223` | `paint_near_free_throw_right_corner` | (690, 620) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s03__f007237` | `paint_near_baseline_left_corner` | (1740, 420) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s03__f007237` | `paint_near_baseline_right_corner` | (1740, 710) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s03__f007237` | `paint_near_free_throw_left_corner` | (995, 520) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s03__f007237` | `paint_near_free_throw_right_corner` | (1010, 680) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s07__f014099` | `paint_near_baseline_left_corner` | (300, 450) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s07__f014099` | `paint_near_baseline_right_corner` | (300, 730) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s07__f014099` | `paint_near_free_throw_left_corner` | (1070, 500) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s07__f014099` | `paint_near_free_throw_right_corner` | (1080, 705) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s09__f018997` | `paint_near_baseline_left_corner` | (1800, 400) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s09__f018997` | `paint_near_baseline_right_corner` | (1800, 720) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s09__f018997` | `paint_near_free_throw_left_corner` | (740, 510) | null | null | all 3 calls returned None |
| `wnba__wnba_06__s09__f018997` | `paint_near_free_throw_right_corner` | (740, 700) | null | null | all 3 calls returned None |
| `wnba__wnba_07__s08__f016801` | `paint_near_baseline_left_corner` | (200, 440) | null | null | all 3 calls returned None |
| `wnba__wnba_07__s08__f016801` | `paint_near_baseline_right_corner` | (200, 750) | null | null | all 3 calls returned None |
| `wnba__wnba_07__s08__f016801` | `paint_near_free_throw_left_corner` | (1100, 480) | null | null | all 3 calls returned None |
| `wnba__wnba_07__s08__f016801` | `paint_near_free_throw_right_corner` | (1100, 740) | null | null | all 3 calls returned None |

## Five-frame eye check

The evenly spaced CSV-order frame indices were 0, 4, 8, 12, and 16. The
renders retain red labelled corners and explicitly state in blue that the
projected corner is unavailable; a blue point would fabricate a result.

- `g192_score_existing_homography_renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg`
- `g192_score_existing_homography_renders/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg`
- `g192_score_existing_homography_renders/wnba__wnba_01_1080p__s01__f001600.jpg`
- `g192_score_existing_homography_renders/wnba__wnba_04__s06__f012223.jpg`
- `g192_score_existing_homography_renders/wnba__wnba_07__s08__f016801.jpg`

Human assessment: the red targets visibly mark the labelled paint-corner
locations, but no human can call label and projection the same point because
the solver supplied no projected point in any render.

## Conclusion and NOT VERIFIED

On this exact direct single-decode procedure, the existing route has **0/17
frame solves and 0/68 evaluable target projections**. Thus it does not establish
that basketball's coordinate-contract problem can be resolved merely by
persisting this route's output. Nor does it establish that the homography is
bad in the sense of a large reprojection error: no matrix was returned to score.

NOT VERIFIED:

- Per-target reprojection median, p90, or count at/under the 11.39-px label
  repeatability floor; all are undefined because no target was projected.
- Whether any multi-frame/video-state pipeline path returns a per-frame
  homography on these images; this row followed the prescribed one-decode
  direct route and did not recover deleted videos or run the pipeline.
- Whether the static `Rectify1.npy` fallback is accurate; it was deliberately
  not passed off as a solved homography.
- Any coordinate-contract, persistence, calibration, learned-keypoint,
  selection, threshold, solver, daemon, or deployment change.

## Orchestrator landing note: this CLOSES the cheap basketball path

Renders relocated to `g192b_renders/` at landing; the `g192_` memo retains the
FALSIFIED record of this row's first dispatch and was not overwritten.

**What is settled.** The direct route -- `src.tracking.court_detector.detect_court_homography`,
the function `unified_pipeline.py:330` imports -- returned `None` on **17 of 17**
labelled frames, across **0 of 51** calls, in three fresh processes per frame.
These are frames SELECTED for paint-corner visibility, which makes the result
harder on the solver, not easier. Error against G140's 11.39 px floor is
**undefined, not zero**, and the lane correctly kept all 68 targets in the
denominator instead of letting unsolved frames vanish (B1).

**So Fable's step 2 is answered and the cheap path is CLOSED.** There is no good
per-clip homography sitting in memory waiting to be persisted, at least not from
this route on these frames. The adjudication's hope that basketball's
coordinate-contract failure was "plumbing, not calibration" does not survive its
own test.

**The boundary, which matters and which the lane drew correctly.** The call path
exercised was the Hough-line implementation; it did NOT invoke LoFTR or SIFT, and
the static `Rectify1.npy` fallback was not substituted because it is not a
returned solve. So this does not establish what the FULL pipeline uses at runtime.

**That opens a sharper question than the one this row asked.** `run_clip.py:581`
asserts a per-clip homography "is solved in memory and discarded". This row shows
the direct solver solving nothing on corner-visible frames. Both cannot be
comfortably true. Either the pipeline reaches a homography by a different path
(LoFTR, SIFT, or the static file), or that comment is optimistic about what the
pipeline actually has. **Which one is the next row**, and it is cheap: instrument
the full pipeline on one clip and record which branch produces the matrix it
projects with, if any.

**Not claimed:** that basketball cannot be calibrated. One route on 17 frames is
not a verdict on the sport. G136 measured four-corner geometry visible in 46.2 pct
of basketball frames (at 66.7 pct labeller agreement), so a calibratable
population plausibly exists; nothing here says otherwise.
