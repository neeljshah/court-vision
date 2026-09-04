# G244: Whole-game map validity versus retained match diagnostics

## Verdict

**ACCEPT (measurement only): no retained G242 match diagnostic distinguishes a visibly correct projected court from a visibly wrong one on this blind 89-frame, one-clip, one-seed, one-labeller set.** Matches, inliers, inlier ratio, and RMS all have substantial VALID/INVALID range overlap. This is the full, consequential result: a G222 literal match is not a court-validity signal, so the existing hold claims remain render-bound.

The G241b one-frame drops add a different negative result. The named cut drops are 128 matches at distance 3,933 and 165 at 9,823, but both lie within the ordinary single-frame drop range of -283 through 170. An ordinary 170-match drop exceeds both. The two cuts are therefore **not range-separable from ordinary variation** in this span. This is IN-SAMPLE on two cuts in one clip only; no drop threshold or cut detector is proposed.

No production code, label file, matcher setting, threshold, court model, coordinate contract, daemon, keeper, corpus, `src/`, or `domains/` file changed. No pod was touched, so no disk probe or pod temporary existed and bytes freed are 0.

## Blind-label ordering and inputs

I first opened all 89 committed G242 overlays, judged only independent painted geometry (arc, free-throw circle, sideline, and baseline), and recorded scene type separately from validity. I did not use the four fitted corners. I did not open G242's memo inventory, `per_sample_table.csv`, `g242_measurement.json`, matches, inliers, ratios, or RMS until the blind record was written and committed as [`636d67aeb`](g244_blind_validity_labels_2026-09-04.csv). Only after that commit did I read the G242 inventory and numerical diagnostics.

The local recomputation route is [`scripts/platformkit/tracking/g244_homography_validity_signal.py`](../../../scripts/platformkit/tracking/g244_homography_validity_signal.py), SHA-256 `d7b374508a29acfbff2f5e2f69a10dd1019a83e566ad5d4996e0d14e878c3b92`. It reads the committed inputs directly; no G242 artifact is copied into this landing.

| Input opened | Full path | Bytes | Resolution / role |
|---|---|---:|---|
| Blind record | `docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv` | 8,114 | 89 independent labels |
| G242 direct overlays | `docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/acquired_renders/` | 10,446,708 across 89 JPEGs | every image 960x540; blind visual input |
| G242 contact sheets | `docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/acquired_contact_sheets/` | 1,903,218 across 10 JPEGs | every image 960x540; blind review index |
| G242 diagnostics | `docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/per_sample_table.csv` | 8,834 | 89 named rows, post-commit numerical input |
| G242 measurement | `docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/g242_measurement.json` | 35,989 | 89 retained record schemas, post-commit matrix-availability audit |
| G241b direct series | `docs/evidence/tracking/g241b_seed_horizon_to_failure_artifact/extended_10000/g241b_measurement.json` | 4,675,215 | 10,000 contiguous direct-geometry rows |
| G233d seed render | `docs/evidence/tracking/g233d_seed_gate_validated_frame_artifact/seed_render_distance_0000.jpg` | 658,279 | 1920x1080; visual reference opened during blind review |

The committed source-video identity, used only by the predecessor measurements and not opened here, is `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 174,430 frames at 30 fps, as documented by G242 and G241b.

## Blind labels, scenes, and agreement with G242

The committed [blind table](g244_blind_validity_labels_2026-09-04.csv) records 27 VALID, 28 INVALID, and 34 CANNOT_JUDGE labels. CANNOT_JUDGE was retained rather than merged with either geometry class.

| Scene type | VALID | INVALID | CANNOT_JUDGE | Total |
|---|---:|---:|---:|---:|
| Normal court | 26 | 24 | 2 | 52 |
| Tight player / bench / crowd | 0 | 0 | 29 | 29 |
| Replay / overhead | 1 | 4 | 1 | 6 |
| Graphic / partial | 0 | 0 | 2 | 2 |
| Total | 27 | 28 | 34 | 89 |

This distinguishes scene from validity: frame 8000 is a normal court view and INVALID, not a scene-type failure.

G242's single-labeller inventory persisted only its four aggregate scene counts, not a frame-to-scene table or validity labels. At the comparable aggregate level, my blind scene marginals agree exactly with G242: normal 52, tight 29, replay/overhead 6, and graphic/partial 2. A frame-level agreement rate, kappa, or validity agreement cannot be computed honestly from an aggregate-only predecessor inventory; identical marginals are not claimed as per-frame agreement.

## G242 diagnostics by blind validity class

All 89 rows are retained. The constructed seed row remains in VALID (2,000 matches/inliers and zero RMS); no row was excluded. P90 uses the standard linear quantile calculation.

| Diagnostic | Class | n | Min | Median | P90 | Max |
|---|---|---:|---:|---:|---:|---:|
| Matches | VALID | 27 | 130 | 343 | 546.2 | 2000 |
| Matches | INVALID | 28 | 114 | 282 | 576.5 | 652 |
| Matches | CANNOT_JUDGE | 34 | 87 | 310.5 | 537.2 | 658 |
| Inliers | VALID | 27 | 100 | 282 | 497.2 | 2000 |
| Inliers | INVALID | 28 | 86 | 246 | 538.8 | 620 |
| Inliers | CANNOT_JUDGE | 34 | 50 | 266 | 499.8 | 631 |
| Inlier ratio | VALID | 27 | 0.624309 | 0.817623 | 0.915106 | 1.000000 |
| Inlier ratio | INVALID | 28 | 0.709677 | 0.864698 | 0.939898 | 0.950920 |
| Inlier ratio | CANNOT_JUDGE | 34 | 0.565217 | 0.860923 | 0.940430 | 0.959140 |
| RMS reprojection px | VALID | 27 | 0.000000 | 0.472978 | 0.637438 | 0.696784 |
| RMS reprojection px | INVALID | 28 | 0.318691 | 0.468667 | 0.588394 | 1.247066 |
| RMS reprojection px | CANNOT_JUDGE | 34 | 0.313691 | 0.471034 | 0.599212 | 1.400314 |

The overlap, rather than the medians, answers the question:

| Diagnostic | INVALID range | VALID values inside INVALID range | VALID range | INVALID values inside VALID range |
|---|---|---:|---|---:|
| Matches | 114 to 652 | 25/27 | 130 to 2000 | 24/28 |
| Inliers | 86 to 620 | 25/27 | 100 to 2000 | 24/28 |
| Inlier ratio | 0.709677 to 0.950920 | 25/27 | 0.624309 to 1.000000 | 28/28 |
| RMS reprojection px | 0.318691 to 1.247066 | 25/27 | 0.000000 to 0.696784 | 26/28 |

There is no clean separation. In particular, the superficially higher INVALID ratio median and lower INVALID match/inlier medians do not establish a validity signal because the class ranges interpenetrate at the counts above. This is in-sample evidence only; no threshold is fit, evaluated, or proposed.

## Matrix sanity checks

The required cheap matrix checks are not reproducible from the committed G242 record. Its 89 `records` contain no per-frame `homography` or `image_to_court` value (0/89) and no ordered projected court corners (0/89). Therefore convexity, projected area, corner order, inversion, and fold cannot be computed by class from the retained matrix data. The rendered fitted corner dots are not a substitute for an ordered matrix and were not used for validity labels.

This is reported as **NOT_REPRODUCIBLE_FROM_COMMITTED_G242_DATA**, not as a pass, fail, or separating result. It leaves the persisted match-diagnostic conclusion above unchanged and identifies a retention limit for any later matrix-shape investigation.

## G241b contiguous single-frame drops

For each direct record at distance `d = 2..10000`, drop is `matches(d-1) - matches(d)`, so positive is a decline. This gives 9,999 single-frame changes. The ordinary reference excludes only the two pre-identified cut transitions at distances 3,933 and 9,823, leaving 9,997 changes.

| Series | n | Min | Median | P90 | Max |
|---|---:|---:|---:|---:|---:|
| All single-frame changes | 9999 | -283 | 0 | 13 | 170 |
| Ordinary changes, excluding the two named cuts | 9997 | -283 | 0 | 13 | 170 |

| Named cut transition | Matches before -> after | Drop | Ordinary drops at least this large |
|---|---|---:|---:|
| Distance 3933 | 310 -> 182 | 128 | 1 |
| Distance 9823 | 327 -> 162 | 165 | 1 |

The two named drops span 128 to 165. Zero of the 9,997 ordinary drops falls inside that closed interval, but this is not a clean separator: both named drops lie inside the broader ordinary range (-283 to 170), and the single ordinary 170 drop is larger than both. A magnitude rule that retained the smaller 128 drop would also retain that ordinary 170 drop. Thus the explicit range overlap is 2/2 named cuts inside the ordinary range, with 0/9,997 ordinary values inside the named-cut interval. The abrupt-drop signal is **not separable from ordinary variation on this in-sample two-cut, one-clip denominator**; no threshold or production detector follows.

## Verification and limitations

Focused test run locally:

```text
python -m pytest scripts/platformkit/tracking/test_g244_homography_validity_signal.py -q -p no:cacheprovider
1 passed in 1.55s
```

No full test suite was run. Contract self-check: A7 names only extant committed paths; B1 retains all 89 blind and diagnostic rows and all 9,999 G241b differences; B2-B6 introduce no production schema, lifecycle, deployment, or move; B7 uses the complete even-stride G242 set; B8 never treats fitted corners or self-fit RMS as independent geometry; B9 names frame and one-frame-difference denominators; B10 changes no bar. Q does not apply to this tracking measurement.

**NOT VERIFIED:** ground truth; repeatability of this one labeller's validity calls (G140 p90 label repeatability is 11.39 px); framewise agreement with G242 because it did not retain per-frame scene labels; any other seed, clip, arena, camera, or sport; dense validity between G242's stride samples; any matrix-shape sanity signal because matrices were not retained; and a production validity or cut-detection rule.
