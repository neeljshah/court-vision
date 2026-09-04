# G217: Oracle Error Decomposition

## Verdict

**ACCEPT: the G214 strategic claim does not survive.** G210b's detected-line oracle reproduced at **1/17** all-four frames and **28.841315992648475 px** median maximum corner error. Passing four exact labelled paint lines to the same unchanged solve_line_pairs fitter and unchanged G205 score_frame produced **17/17** all-four frames and **0.0 px** median maximum corner error.

The 1/17 result is therefore a property of the **current detected line geometry**, not an inherent inability of this four-point fitter or court model to work at 12 px on these frames. The selected detected groups are off their two labelled paint corners by median **10.2347919059155 px**, p90 **20.6572887040051 px**, and maximum **59.693249497295 px** across all 68 role-frame selections. The error is DETECTED LINE GEOMETRY and detection accuracy is the live lever on this fixed construct.

This does **not** produce automatic calibration: the true-line control consumes labels. It means the measured 1/17 ceiling is a property of the current line detectors' accuracy, not of the approach, and G214's defunding recommendation rests on a misreading. It does not establish that another detector, or a production route, will attain the label-derived control.

## Machine, fixed inputs, and unchanged route

This measurement ran only on local Windows worktree C:/Users/neelj/nba-track-a5. No SSH, pod, service, daemon, production path, corpus, detector, or threshold change occurred.

- Labels: docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv (15,633 bytes, 68 rows: four roles on each of 17 exhaustive frames).
- Oracle: oracle_fit in scripts/platformkit/tracking/g210b_court_fit_untruncated_search.py, unchanged. It uses labels only to choose detected groups, then passes groups[index].line to the fitter.
- Fitter: solve_line_pairs in scripts/platformkit/tracking/g210_court_model_fit_to_lines.py, unchanged.
- Scorer: G205 score_frame and TOLERANCE_PX = 12.0 in scripts/platformkit/tracking/g205_zero_shot_corner_probe.py, unchanged.
- G196 reference: docs/evidence/tracking/g196_homography_from_labelled_corners_2026-09-03.md. It found externally visible three-point-arc alignment on three evenly spaced frames and two indeterminate tight crops using the same sport-specific court model.

The committed artifact per_frame.csv contains the full path, byte size, SHA-256, and decoded resolution of every opened source. The following table repeats the required full path, byte size, and resolution.

| Audit ID | Full local source path | Bytes | Resolution |
|---|---|---:|---:|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg | 605623 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg | 584472 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg | 106044 | 640x360 |
| ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg | 689352 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg | 297020 | 1280x720 |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg | 308901 | 1280x720 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg | 679804 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg | 531457 | 1920x1080 |
| wnba__wnba_01_1080p__s01__f001600 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s01__f001600.jpg | 621798 | 1920x1080 |
| wnba__wnba_01_1080p__s03__f004062 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s03__f004062.jpg | 629254 | 1920x1080 |
| wnba__wnba_01_1080p__s06__f007539 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s06__f007539.jpg | 535379 | 1920x1080 |
| wnba__wnba_02__s11__f021983 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_02__s11__f021983.jpg | 251244 | 1280x720 |
| wnba__wnba_04__s06__f012223 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_04__s06__f012223.jpg | 238301 | 1280x720 |
| wnba__wnba_06__s03__f007237 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s03__f007237.jpg | 598645 | 1920x1080 |
| wnba__wnba_06__s07__f014099 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s07__f014099.jpg | 530179 | 1920x1080 |
| wnba__wnba_06__s09__f018997 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s09__f018997.jpg | 622191 | 1920x1080 |
| wnba__wnba_07__s08__f016801 | C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_07__s08__f016801.jpg | 504523 | 1920x1080 |

## Method

The control was rerun before attribution. G210b's label-free fit_image branch was rerun unchanged to reproduce the stated 0/17. The detected-line oracle was then rerun unchanged. The G217 Method's 0/17 and approximately 28.841 px wording combines two G210b branches: label-free is 0/17, while the detected-line oracle is 1/17 at 28.841315992648475 px. This memo keeps them separate.

For the true-line control only, the four G140 labelled corners built exactly these image lines: baseline 0-1, free-throw 2-3, lane-left 0-2, and lane-right 1-3. Those lines were passed directly to unchanged solve_line_pairs with the same near_baseline, near_free_throw, lane_left, and lane_right court lines. The resulting court corners were inverse-projected and scored by unchanged G205 score_frame at its unchanged 12 px threshold.

## Reproduced controls and decomposition

| Arm | Frames all four within 12 px | Median per-frame max corner error | What varies |
|---|---:|---:|---|
| G210b label-free fit | 0 / 17 | 729.7681160167696 px | Fixed global random search and current detector groups |
| G210b detected-line oracle | 1 / 17 | 28.841315992648475 px | Selection is label-assisted; geometry remains selected detected group lines |
| G217 true-line control | 17 / 17 | 0.0 px | Detected lines replaced by exact lines built from labels |
| G196 hand-corner result | All 17 matrices solved | 0.0 px fitted-point residual | Direct four-corner transform; non-fitted-marking visual check |

The true-line control holds fitter, court model, sport-specific lane width, inverse projection, scorer, labels, tolerance, and all 17 frames fixed. Only the four detected line geometries change. Its near-zero result isolates the oracle residual to detected-line geometry; it is not a new independent accuracy estimate.

### Detected selected-line distance distribution (68 role-frame selections)

Each is the oracle's mean absolute point-line distance from a selected detected group to the two labels that its paint line should pass through. The full data is in g217_oracle_error_decomposition_artifact/selected_line_distances.csv.

| Role | n | Min px | Median px | p90 px | Max px |
|---|---:|---:|---:|---:|---:|
| near_baseline | 17 | 0.943562746587 | 10.178412103207 | 19.318411264026 | 21.264954433606 |
| near_free_throw | 17 | 2.901258925032 | 10.334761554032 | 17.550559166113 | 19.928250513264 |
| lane_left | 17 | 1.229669250022 | 13.907985717438 | 23.170166304047 | 28.397019889751 |
| lane_right | 17 | 1.904616005956 | 10.015046716963 | 19.893118429898 | 59.693249497295 |
| all roles | 68 | 0.943562746587 | 10.234791905916 | 20.657288704005 | 59.693249497295 |

### Per-frame control scores

The committed per_frame.csv carries these values plus input hashes. The true-line maximum is zero at displayed precision on every frame; no row is excluded.

| Audit ID | Oracle max px | Oracle all four | True-line max px | True-line all four |
|---|---:|---|---:|---|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | 22.102247083275 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785 | 26.900086711036 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171 | 26.693424003592 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871 | 28.359302507852 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925 | 6.744692217456 | yes | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920 | 32.637571875747 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760 | 61.102801579856 | no | 0.0 | yes |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340 | 33.307597842910 | no | 0.0 | yes |
| wnba__wnba_01_1080p__s01__f001600 | 92.774241200329 | no | 0.0 | yes |
| wnba__wnba_01_1080p__s03__f004062 | 26.699672335697 | no | 0.0 | yes |
| wnba__wnba_01_1080p__s06__f007539 | 24.462716724897 | no | 0.0 | yes |
| wnba__wnba_02__s11__f021983 | 33.792880619898 | no | 0.0 | yes |
| wnba__wnba_04__s06__f012223 | 32.759892570331 | no | 0.0 | yes |
| wnba__wnba_06__s03__f007237 | 38.506943530561 | no | 0.0 | yes |
| wnba__wnba_06__s07__f014099 | 24.939875638428 | no | 0.0 | yes |
| wnba__wnba_06__s09__f018997 | 36.914618287772 | no | 0.0 | yes |
| wnba__wnba_07__s08__f016801 | 28.841315992648 | no | 0.0 | yes |

## Evenly distributed render check

Indices 0, 8, and 16 span the sorted 17-frame construct. Each image puts G210b's detected-line oracle at left and G217's exact labelled-line control at right with the same projected-court renderer. The panels visibly diverge; they are the required side-by-side route check, not an independent metric. Broadcast graphics and occlusion prevent treating them as a label-free score.

| Index | Audit ID | Render |
|---:|---|---|
| 0 | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | [side-by-side render](g217_oracle_error_decomposition_artifact/renders/00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg) |
| 8 | wnba__wnba_01_1080p__s01__f001600 | [side-by-side render](g217_oracle_error_decomposition_artifact/renders/08_wnba__wnba_01_1080p__s01__f001600.jpg) |
| 16 | wnba__wnba_07__s08__f016801 | [side-by-side render](g217_oracle_error_decomposition_artifact/renders/16_wnba__wnba_07__s08__f016801.jpg) |

## Limitations and NOT VERIFIED

- This is a 17-frame exhaustive construct, not a rate for games, broadcasts, or future footage.
- G140 p90 label repeatability is 11.39 px. The 12 px threshold is at the label-noise floor, and corners are single-source eye labels.
- The true-line score is self-fit at the four corners used to construct its lines. It is an isolation control, not independent residual evidence.
- No new or tuned line detector was tested. This does not rank detector designs, demonstrate automatic calibration, validate production tracking, or promise a recoverable calibration rate.
- G196's out-of-sample arc observations support projective-model adequacy on these frames, but its two tight-crop checks were indeterminate.
- Temporal calibration, new footage, deployment, thresholds, court model, coordinate contract, and all production paths are NOT VERIFIED here.

## Verifier-contract self-check

- A1 is verifier-owned and runs in master. Per the worktree rule, this lane did not run commands outside track-a5.
- A2: recomputed from committed G217 CSVs before this memo: 17 unique source paths, 68 selected role rows, oracle 1/17 and 28.841315992648475 px, true line 17/17 and 0.0 px.
- A3/B7: renders are indices 0, 8, 16 across all 17 sorted rows, not a head slice. A4: 17 distinct source paths and 68 distinct audit-role rows.
- A5/B2: targeted reader search found only the new harness, memo, ledger, and register references; no pre-existing reader consumes a new artifact field. A7: every named artifact file and all three linked renders exists before commit.
- B1: no row was excluded. B3-B6: no gate, schema, deployment, claim loop, or module move exists. B8: true-line score is explicitly self-fit, not independent. B9: denominators are all 17 fixed frames and all 68 named role-frame pairs. B10: G205's 12 px scorer and G210 fitter were imported unchanged.

Focused verification in this worktree:

    python -m pytest tests/platformkit/test_g217_oracle_error_decomposition.py -q
    1 passed in 1.28s

    python -m pytest tests/platformkit/test_loc_rail_scope.py -q
    1 passed in 1.97s
