# G246: Why the Amateur Seed Gates Failed

**VERDICT: CLOSED AT LIMIT - the G243b failure is not repaired by a role mapping or axis convention.** The recorded label coordinates do not identify the court features their role names claim, and exhaustive enumeration of every four-point correspondence finds no overlay that follows the independent arc, sidelines, and centre circle. The immediate cause is mislabelled-feature bookkeeping in the seed inputs, not label spread. No production change, new court-model key, propagation, in-court fraction, or labels-per-hour calculation is proposed or performed.

Denominator: 1 clip, 1 enumerated seed frame, 0 confirmation frames because no variant passed, and 1 labeller. This row is a diagnosis, not a calibration.

## Preconditions, source, and disk guard

I began at 2026-09-04 05:18:31 -05:00 in `C:\Users\neelj\nba-track-a6`, branch `track-a6`. Before beginning, I used an exact executable-and-argument process inspection and found G244 active in `C:\Users\neelj\nba-track-a5`; it was not interrupted. That left the permitted second measurement lane available. No resident process was touched.

The input opened for this diagnosis was the committed exact seed decode, `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g243b_seeded_calibration_amateur_2026-09-04_artifact\seed_frame_2760.jpg`, 1280x720, derived frame-exactly from `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4`. I independently rechecked the pod source: 24,523,745 bytes; SHA-256 `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`; 1280x720; 30/1 fps; 3,601 decoded video frames; 120.100000 seconds.

`df` was not used. The required pod probe, `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g246_disk_probe.bin bs=1M count=1 conv=fsync status=none`, wrote and removed 1,048,576 bytes before any G246 artifact was generated. `du -sm /workspace/nba-ai-system/data` measured 33,038 MB. The two abandoned partials in `footage_bridge` were not touched. No corpus source was copied or deleted; no temporary artifact was made or deleted, so bytes freed are 0.

## Point identity comes before correspondence

The table records the visible feature at every one of the eight retained label rows. The red cross is a locator, not evidence that the claimed role is correct. The eight crops are committed in [identity_crops](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/).

| Set / label | Pixel | Claimed role | What is actually at the pixel in frame 2760 | Crop |
|---|---:|---|---|---|
| Clustered 1 | `(45, 385)` | near-baseline left paint corner | Bare hardwood immediately courtward of the blue outer boundary; no paint corner or painted lane line is at the cross. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/clustered_01.jpg) |
| Clustered 2 | `(283, 276)` | near-baseline right paint corner | Bare hardwood beside the diagonal blue outer boundary, not a paint corner. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/clustered_02.jpg) |
| Clustered 3 | `(363, 424)` | near-free-throw left paint corner | A non-corner floor region adjacent to a diagonal marking and partly obscured by the coach; no identifiable paint/free-throw corner is present at the cross. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/clustered_03.jpg) |
| Clustered 4 | `(624, 306)` | near-free-throw right paint corner | A player-occluded floor location near curved court marking, not a visible paint corner. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/clustered_04.jpg) |
| Spread 1 | `(363, 424)` | near-free-throw left paint corner | The same coach-occluded, non-corner location as clustered 3; the repeated coordinate does not become a corner under a new role name. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/spread_01.jpg) |
| Spread 2 | `(624, 306)` | near-free-throw right paint corner | The same player-occluded, non-corner location as clustered 4. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/spread_02.jpg) |
| Spread 3 | `(1140, 359)` | centre-circle top | Bare floor immediately above/outside the visible centre-circle and logo boundary, not a circle extremum. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/spread_03.jpg) |
| Spread 4 | `(1160, 468)` | centre-circle bottom | The centre-line/logo area, rather than the lower circumference of the painted centre circle. | [crop](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/identity_crops/spread_04.jpg) |

This is independent of the G243b repeatability result. Repeating an incorrect point within 11.39 px can be repeatable without identifying the intended feature. The clustered input has no four visible paint corners; the spread input has no two visible centre-circle extrema. Thus a role permutation can only exchange wrong correspondences.

## Court-model check

`court_points_for_sport` in `scripts/platformkit/tracking/g196_homography_from_labelled_corners.py` has exactly two accepted keys:

| Key | Returned near-paint points in ft | Model assumption |
|---|---|---|
| `ncaa_basketball` | `(19,0) (31,0) (19,19) (31,19)` | 94x50 ft, 12-ft lane, 19-ft paint depth |
| `wnba` | `(17,0) (33,0) (17,19) (33,19)` | 94x50 ft, 16-ft lane, 19-ft paint depth |

There is no high-school key. I held both existing models fixed and, exactly as G243b did, used only its row-local 84x50-ft, 12-ft lane, 19-ft paint-depth, 6-ft centre-circle-radius, 19-ft-9-in arc model for the enumeration.

The footage visibly establishes painted sidelines/baseline material, a relatively narrow lane, a three-point arc at the visible end, and a centre-circle marking. Those observations are qualitatively consistent with a high-school-style court. A single uncalibrated oblique camera view cannot independently measure 12 versus 16 ft, 84 versus 94 ft, or a 19-ft-9-in radius: each requires a correct correspondence or physical reference. Therefore the footage does not verify those dimensions as ground truth, and this row does not treat the model as proven. It does establish that the label points above are not the requested features, regardless of which of those court models might later be appropriate.

## Exhaustive correspondence test

For each unchanged G243b label set, I rendered all 24 one-to-one assignments of the four fixed model points to the four fixed image labels: `4! = 24`, 48 overlays total. This exhaustive enumeration includes both choices of which baseline is `y=0`, both left-to-right `x` orientations, and every other point ordering. No label coordinate, court dimension, matcher setting, or production coordinate contract moved.

Every verdict below is an eye judgement against only independent geometry: the painted three-point arc, sidelines, and centre circle. It never uses the four red fitted point markers. `FAIL` means that at least those independent markings do not jointly land; it is not a residual criterion. The two contact sheets make the full enumeration reviewable at once, while every full-resolution overlay is individually committed: [clustered sheet](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/clustered_contact_sheet.jpg) and [spread sheet](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/spread_contact_sheet.jpg).

| Variant | Court index for image-label order | Clustered render / verdict | Spread render / verdict |
|---:|---|---|---|
| 0 | `0123` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_00_court_indices_0123.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_00_court_indices_0123.jpg) FAIL |
| 1 | `0132` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_01_court_indices_0132.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_01_court_indices_0132.jpg) FAIL |
| 2 | `0213` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_02_court_indices_0213.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_02_court_indices_0213.jpg) FAIL |
| 3 | `0231` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_03_court_indices_0231.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_03_court_indices_0231.jpg) FAIL |
| 4 | `0312` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_04_court_indices_0312.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_04_court_indices_0312.jpg) FAIL |
| 5 | `0321` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_05_court_indices_0321.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_05_court_indices_0321.jpg) FAIL |
| 6 | `1023` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_06_court_indices_1023.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_06_court_indices_1023.jpg) FAIL |
| 7 | `1032` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_07_court_indices_1032.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_07_court_indices_1032.jpg) FAIL |
| 8 | `1203` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_08_court_indices_1203.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_08_court_indices_1203.jpg) FAIL |
| 9 | `1230` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_09_court_indices_1230.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_09_court_indices_1230.jpg) FAIL |
| 10 | `1302` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_10_court_indices_1302.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_10_court_indices_1302.jpg) FAIL |
| 11 | `1320` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_11_court_indices_1320.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_11_court_indices_1320.jpg) FAIL |
| 12 | `2013` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_12_court_indices_2013.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_12_court_indices_2013.jpg) FAIL |
| 13 | `2031` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_13_court_indices_2031.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_13_court_indices_2031.jpg) FAIL |
| 14 | `2103` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_14_court_indices_2103.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_14_court_indices_2103.jpg) FAIL |
| 15 | `2130` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_15_court_indices_2130.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_15_court_indices_2130.jpg) FAIL |
| 16 | `2301` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_16_court_indices_2301.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_16_court_indices_2301.jpg) FAIL |
| 17 | `2310` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_17_court_indices_2310.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_17_court_indices_2310.jpg) FAIL |
| 18 | `3012` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_18_court_indices_3012.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_18_court_indices_3012.jpg) FAIL |
| 19 | `3021` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_19_court_indices_3021.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_19_court_indices_3021.jpg) FAIL |
| 20 | `3102` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_20_court_indices_3102.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_20_court_indices_3102.jpg) FAIL |
| 21 | `3120` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_21_court_indices_3120.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_21_court_indices_3120.jpg) FAIL |
| 22 | `3201` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_22_court_indices_3201.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_22_court_indices_3201.jpg) FAIL |
| 23 | `3210` | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/clustered_23_court_indices_3210.jpg) FAIL | [render](g246_amateur_gate_failure_diagnosis_2026-09-04_artifact/enumerated_renders/spread_23_court_indices_3210.jpg) FAIL |

The passing candidates column is empty. Therefore no mapping was found by enumeration, and no out-of-sample fresh label/render was performed. Treating an arbitrary variant as a candidate for confirmation would be tuning after a fail, not the mandated test.

## Conclusion and limits

The particular G243b coordinates are not valid feature observations. Enumeration proves that reordering those same coordinates, reversing the baseline, or flipping `x` cannot make their inverse projection coincide with the independent court geometry. This is a complete negative result for role mapping and axis convention. It does not prove that the 84x50-ft model is correct, does not rule out camera geometry as an additional problem, and does not establish a corrected label set. The cause established here is narrower: the recorded seed rows were bookkeeping labels rather than the painted features named by their roles.

RMS is deliberately omitted from all verdicts. With four fitted inputs, its zero self-fit value is structurally guaranteed and provides no independent evidence. G242 remains controlling: match counts, inliers, inlier ratios, and RMS do not establish a correct court.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. Contract self-check: A7 evidence paths named above exist; B1 has no conditional denominator; B2-B6 make no schema, lifecycle, deployment, production, or module move; B7 reviews all 48 renders rather than a head slice; B8 excludes fitted points and self-fit residuals; B9 recycles no unit; and B10 moves no bar or threshold. This local renderer did not exercise a pod route, so A11 has no route-file hash to record. The focused test is `python -m pytest scripts/platformkit/tracking/test_g246_homography_mapping_diagnosis.py -q -p no:cacheprovider` and passed: `3 passed`.

NOT VERIFIED: physical court dimensions; a corrected hand label; a passing mapping on this or any other frame; automatic calibration (still 0/17); camera-model adequacy; detector coordinates; propagation; in-court fraction; labels-per-hour; or eye-label repeatability beyond the stated single labeller. This diagnosis is not a production fix.
