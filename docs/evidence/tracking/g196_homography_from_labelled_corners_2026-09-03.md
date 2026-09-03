# G196: Homography from Hand-Labelled Paint Corners

## Result

**Court geometry is recoverable from hand-labelled paint corners in this set.** Three of the five evenly spaced render checks show independently visible, non-fitted three-point curves landing on the court; the other two are tight-crop indeterminates, not clean mismatches. For frames where four true paint corners can be obtained, the observed ceiling is detection/point quality, not a universally degenerate court model. This is recoverability evidence only, not proof that labels are production-accurate.

Run **locally** in `C:\Users\neelj\nba-track-a6`, not on the pod. It read 17 committed JPEGs and solved four-point transforms: no video decode, model inference, `run_clip.py`, pipeline route, daemon, or production-code change.

## Contract and method

The 68-row committed [G140 target CSV](g140_corner_targets/corner_pixel_targets.csv) supplies 17 audit IDs and the four required roles per ID, all `status=target`. Every `source_decode` resolves to a committed JPEG and native dimensions equal the CSV. The [per-frame records](g196_homography_from_labelled_corners_artifact/per_frame_records.json) store the role-ordered four image points, four court points, 3x3 image-to-court matrix, and residual for every frame.

`cv2.getPerspectiveTransform` maps the four ordered image points `[near baseline left, near baseline right, near free-throw left, near free-throw right]` to the near paint rectangle. RANSAC is intentionally not used: four points are the exact projective minimum, leaving no redundant correspondence or alternative sample to score/reject. The inverse projects boundaries, sidelines, half-court, centre circle, paint/free-throw geometry, and three-point arcs back onto each source JPEG; yellow is the model overlay and red marks are source points.

### Court coordinate contract (feet)

Coordinates are `[x, y]`: `x=0..50` runs left sideline to right sideline and `y=0..94` runs from the labelled near baseline toward the other baseline. NCAA uses a 12-ft lane; WNBA uses a 16-ft lane, so their four model points differ:

| League | Near baseline left | Near baseline right | Near free-throw left | Near free-throw right |
|---|---:|---:|---:|---:|
| NCAA basketball | `[19, 0]` | `[31, 0]` | `[19, 19]` | `[31, 19]` |
| WNBA | `[17, 0]` | `[33, 0]` | `[17, 19]` | `[33, 19]` |

NCAA Rule 1 Section 6 Art. 1 states a **12-ft** free-throw lane measured to its outside boundaries; its official court diagram gives the 94-by-50-ft court and 19-ft paint depth. See the [NCAA rules book](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/women/PRWBB_RulesBook.pdf) and [court diagram](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/common/PRXBB_CourtDiagram.pdf). The [official WNBA Rule 1/court diagram](https://cdn.wnba.com/sites/4/2026/05/2026-WNBA-Official-Rule-Book.pdf) uses the same 94-by-50-ft court and 19-ft depth but a **16-ft** outside lane width. The rendered model also uses the published 22 ft 1 3/4 in three-point arc.

## Per-frame results (n=17, exhaustive construct)

`Solved` means a finite nonsingular four-point matrix was constructed. The residual is image point -> court -> image, in pixels. It is a **conditioning/sanity check only**: with exactly four points, the fit is exact by construction, so a small residual proves neither role correctness nor projection accuracy.

| Audit ID | Sport | Source JPEG (absolute path) | Native px | Solved | RMS residual px | Max residual px | Overlay |
|---|---|---|---:|---|---:|---:|---|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg) |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg) |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg` | 640x360 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg) |
| ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg) |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg` | 1280x720 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg) |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg` | 1280x720 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg) |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg) |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340 | ncaa_basketball | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg) |
| wnba__wnba_01_1080p__s01__f001600 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s01__f001600.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_01_1080p__s01__f001600.jpg) |
| wnba__wnba_01_1080p__s03__f004062 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s03__f004062.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_01_1080p__s03__f004062.jpg) |
| wnba__wnba_01_1080p__s06__f007539 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s06__f007539.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_01_1080p__s06__f007539.jpg) |
| wnba__wnba_02__s11__f021983 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_02__s11__f021983.jpg` | 1280x720 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_02__s11__f021983.jpg) |
| wnba__wnba_04__s06__f012223 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_04__s06__f012223.jpg` | 1280x720 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_04__s06__f012223.jpg) |
| wnba__wnba_06__s03__f007237 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s03__f007237.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_06__s03__f007237.jpg) |
| wnba__wnba_06__s07__f014099 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s07__f014099.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_06__s07__f014099.jpg) |
| wnba__wnba_06__s09__f018997 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s09__f018997.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_06__s09__f018997.jpg) |
| wnba__wnba_07__s08__f016801 | wnba | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_07__s08__f016801.jpg` | 1920x1080 | yes | 0.000e+00 | 0.000e+00 | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_07__s08__f016801.jpg) |

## Five evenly spaced human eye checks

The deterministic even indices are 0, 4, 8, 12, and 16 of stable sorted audit IDs. `YES` requires agreement with a visible painted marking beyond the four fitted correspondences. `INDETERMINATE` is neither a pass nor a failure: the needed independent marking is out of crop or occluded.

| Index | Audit ID | Verdict | Human render observation | Render |
|---:|---|---|---|---|
| 0 | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | INDETERMINATE | Tight hoop-end crop and lower-third hide independent long-court paint. | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg) |
| 4 | ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925 | YES | The projected three-point curve follows the painted arc beyond the fitted key. | [render](g196_homography_from_labelled_corners_artifact/renders/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg) |
| 8 | wnba__wnba_01_1080p__s01__f001600 | YES | The independently visible three-point curve lands on the painted court. | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_01_1080p__s01__f001600.jpg) |
| 12 | wnba__wnba_04__s06__f012223 | INDETERMINATE | Tight hoop-end framing and occlusion hide independent sideline, arc, and centre markings. | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_04__s06__f012223.jpg) |
| 16 | wnba__wnba_07__s08__f016801 | YES | The independently visible three-point curve follows its painted court marking. | [render](g196_homography_from_labelled_corners_artifact/renders/wnba__wnba_07__s08__f016801.jpg) |

## NOT VERIFIED / honest limitation

- Four points are the **exact minimum**: no redundancy, independent residual, or outlier rejection exists. G140's p90 label repeatability is **11.39 px**, and that label noise propagates directly into each matrix.
- This does not validate the Hough solver, a learned detector, a production threshold, pipeline integration, production accuracy, or robustness to overlays/occlusions.
- The two indeterminate eye-check frames do not establish a failure rate; they lack an independently visible marking with which to test extrapolation.
- The 17 small numerical round trips are not an accuracy metric and do not make a production-readiness claim.

## Orchestrator verification at landing: the ceiling is DETECTION

**A1:** `test_g196_homography_from_labelled_corners.py` 1 passed in master. 17 renders committed.

**Eye check done by the orchestrator, not delegated**, on
`renders/wnba__wnba_01_1080p__s01__f001600.jpg`: the projected three-point arc
tracks the painted three-point line on the court, and the near baseline lands on
the painted baseline. Alignment is good rather than pixel-perfect, which is what
an 11.39 px label floor and a bare four-point fit predict.

**The argument that makes this evidence rather than tautology:** the homography
was built from the FOUR PAINT CORNERS ONLY. The three-point arc, the sidelines and
the centre circle were not used to fit it. Their landing on the painted geometry is
genuine out-of-sample confirmation that the projective model is broadly correct.
The paint rectangle itself is fitted by construction and carries no information --
and the lane said so rather than presenting its zero residual as quality.

**Contrast with G194, which is the whole point of this row.** Through
`Rectify1.npy` the court model collapses to a single diagonal line across the
crowd. Through four hand-labelled points it lands on the court. Same footage, same
court model, same renderer.

### Conclusion, and it redirects basketball effort

**The geometry IS recoverable from basketball broadcast frames. The ceiling is
DETECTION and point quality, not the court model, the role semantics, or a
fundamental limit of the footage.** A corner detector for basketball is therefore
worth building, and unlike G31's tennis attempt it now has a validated target: we
know that four correct paint corners suffice.

**What is NOT claimed, holding the lane's own line:** that the labels are
production-accurate. Four points is the exact projective minimum with no
redundancy and no outlier rejection; G140's p90 label repeatability is 11.39 px;
2 of the 5 render checks were tight-crop indeterminates rather than clean
confirmations. This is recoverability evidence, and recoverability is exactly the
question that was open.

**Credit where the lane exceeded the spec:** it established that NCAA uses a
**12-ft** lane and WNBA a **16-ft** lane, cited both rule books, and used
different court models per league. Had it assumed one width, every NCAA
homography would have been silently wrong and this row would have produced a
confident wrong answer.
