# G223: Selected Line Error Structure

## Verdict

**ACCEPT: this exhaustive construct shows scatter, not a clean role-level signed bias, and does not identify a deterministic centreline correction.** G217's absolute selected-line control reproduced exactly: median 10.2347919059155 px and maximum 59.693249497295 px across all 68 selected role-frame lines. With the fixed sign convention below, every role straddles zero. The signed role means are small compared with their spreads and with G140's 11.39 px p90 label-repeatability floor.

Angle and offset are both present, but neither materially dominates over the construct: median absolute midpoint offset is 6.9677852781165 px and median endpoint angle component is 6.856945758277 px; their means are 8.366663440127175 and 9.155991663115234 px. The three largest corner-error frames are not the shallowest selected-line intersections, and 17-frame rank associations are weak (corner error versus maximum role angle: 0.07352941176470588; versus shallowness: -0.12254901960784316). This is descriptive evidence, not an inference beyond the fixed construct.

There is no supported deterministic refinement proposal. A fixed painted-edge-to-centreline shift would require a stable one-signed residual after allowing for label noise; this construct does not show one. No error reduction is predicted for such a correction. A future row would need independent/repeated labels before trying a detector or refinement.

## Machine, route, and fixed inputs

This was run locally only in `C:/Users/neelj/nba-track-a5`; no pod, SSH, service, daemon, corpus mutation, detector change, threshold change, or `src/` write occurred. It calls G217's unchanged `oracle_fit` selection rule, G217's ordered label-line construction, the unchanged group extractor, and G205's unchanged corner scorer. The 12 px protocol, court model, coordinate contract, and `solve_line_pairs` are untouched.

- Labels opened: `C:/Users/neelj/nba-track-a5/docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`, 15,633 bytes, 68 rows (no image resolution).
- Source frames opened: each full path, byte size, SHA-256, and decoded resolution is in the committed `g223_line_error_structure_artifact/per_frame.csv`; the full paths, sizes, and resolutions are repeated below.
- G217's committed artifact remains available at `docs/evidence/tracking/g217_oracle_error_decomposition_artifact/`. G223 remeasures rather than reads its selected-line CSV, so the reproduction is not a copied artifact metric.

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

## Method and sign convention

For each of G217's four fixed roles, G223 calls the same label-assisted `oracle_fit` to select the detected group. It does not tune, replace, or reorder a selected group. The exact comparison line comes from the same ordered pairs used in G217: left-to-right for `near_baseline` and `near_free_throw`, baseline-to-free-throw for `lane_left` and `lane_right`.

**Sign convention:** normalize the exact label-derived line and the selected detected line to unit normals. If the selected normal has a negative dot product with that role's exact-line normal, multiply the selected line by -1. A positive point-line distance is then a selected-line displacement toward the positive half-plane of that fixed, ordered exact-line normal. The convention is fixed once per role and does not depend on source filename, selected-group endpoint order, or distance sign; it therefore cannot manufacture a role bias by arbitrary line orientation.

For each selection, the artifact records both signed corner distances. Their mean is the signed perpendicular offset at the labelled-corner midpoint. Half their absolute difference is the endpoint angle component: the exact amount of label-endpoint disagreement attributable to changing orientation along that labelled segment. The reported angle is the acute unoriented angle between the selected and exact lines.

For each frame, G205 scores the unchanged oracle homography and records its maximum labelled-corner error. The conditioning value is the smallest acute angle among its four selected transverse-longitudinal corner pairs. Lower values are more geometrically shallow and less well conditioned.

## Reproduction control and signed per-role structure

The 68 remeasured mean absolute distances have median 10.2347919059155 px and maximum 59.693249497295 px, exactly reproducing the G217 control. No role-frame row was removed, deduplicated, or selected after inspecting its sign.

| Role | n | Mean signed px | Sample SD px | Min to max px | Positive / negative |
|---|---:|---:|---:|---:|---:|
| near_baseline | 17 | 1.818589260619 | 11.372950124199 | -16.287568808540 to 20.880914316348 | 7 / 10 |
| near_free_throw | 17 | -1.543534481982 | 10.222741378026 | -18.678209304740 to 19.928250513264 | 9 / 8 |
| lane_left | 17 | 0.446456924225 | 11.483474363915 | -18.529477609186 to 26.179441572953 | 5 / 12 |
| lane_right | 17 | -4.595488757972 | 10.132987195837 | -30.781031838369 to 12.772889747363 | 5 / 12 |

All four roles straddle zero. `lane_right` has the largest signed mean in magnitude, -4.595488757972 px, but its sample SD is 10.132987195837 px and it has five positive frames. This is scatter, not the consistent one-sided evidence required for a stable role-level painted-edge bias.

## Angle versus offset

| Component | Mean px | Median px | Sample SD px | Maximum px |
|---|---:|---:|---:|---:|
| Absolute midpoint offset | 8.366663440127 | 6.967785278117 | 6.903810545913 | 30.781031838369 |
| Endpoint angle component | 9.155991663115 | 6.856945758277 | 9.225411458190 | 59.693249497295 |

The corresponding acute angle errors have mean 3.836002244742 degrees, median 1.893457503375 degrees, and maximum 31.619943558554 degrees. The median offset exceeds the median angle component by 0.110839519839 px, while the mean angle component exceeds the mean offset by 0.789328222988 px. That reversal is not material on this construct: angle and offset are mixed rather than one clearly dominating. The maximum endpoint-angle component is the same 59.693249497295 px G217 line-distance maximum, but it is a single selected line, not a general correction rule.

## Corner error and conditioning

The three largest oracle maximum corner errors and their line-structure summaries are:

| Rank | Audit ID | Corner error px | Max role angle deg | Max absolute midpoint offset px | Minimum selected intersection angle deg | Render |
|---:|---|---:|---:|---:|---:|---|
| 1 | wnba__wnba_01_1080p__s01__f001600 | 92.774241200329 | 20.148822056148 | 30.781031838369 | 81.405789548226 | [render](g223_line_error_structure_artifact/renders/01_wnba__wnba_01_1080p__s01__f001600.jpg) |
| 2 | ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760 | 61.102801579856 | 5.903038836957 | 26.179441572953 | 71.331306802780 | [render](g223_line_error_structure_artifact/renders/02_ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg) |
| 3 | wnba__wnba_06__s03__f007237 | 38.506943530561 | 4.069909370585 | 18.678209304740 | 80.625799648942 | [render](g223_line_error_structure_artifact/renders/03_wnba__wnba_06__s03__f007237.jpg) |

These are the three actual largest score errors, not head-slice examples. Each render shows green selected detected lines, yellow label-derived exact lines, and magenta labelled corners. The first has a visibly divergent selected line, while the next two have large midpoint displacements at non-shallow intersection angles.

Across all 17 frames, the Spearman rank association is 0.07352941176470588 for corner error against the frame's largest role angle, and -0.12254901960784316 for corner error against shallowness (negative minimum selected intersection angle). The three largest-error frames have minimum selected intersection angles 81.405789548226, 71.331306802780, and 80.625799648942 degrees. Thus the observed large corner errors are neither generally the largest-angle frames nor the shallowest-intersection frames; no conditioning explanation is supported here.

## Label floor, limitations, and NOT VERIFIED

This is a 17-frame, 68-selection exhaustive construct, not a rate for games, broadcasts, resolutions, or a production route. It cannot detect a modest resolution effect with its 12/4/1 resolution split; no effect is visible here, but resolution does not thereby become irrelevant. The 11.39 px G140 p90 label-repeatability floor is larger than the G217 median selected-line absolute distance and comparable with every role's signed SD. Labels are single-source eye labels with no second labeller. A sign pattern at this magnitude is weak evidence, and none is treated as a detector or painted-line property.

NOT VERIFIED: independent labels; repeatable role bias outside this construct; a deterministic centreline correction; a better detector; any correction's error reduction; temporal behavior; resolution effects; production tracking; any pod result; and any deployment. This row makes no production change and proposes no fix.

## Verifier-contract self-check

- A1 is verifier-owned and must run in master; this lane honored the worktree rule and did not run outside `track-a5`.
- A2/A4: the harness remeasured all 17 named source frames and all 68 unique audit-role pairs; its control equals G217's median and maximum to the shown precision.
- A3/B7: the three render selections are the three largest decision errors, not a first-row/head slice. A7: this memo, `summary.json`, `per_frame.csv`, `per_selection.csv`, and all three linked renders exist before commit.
- A5/B2: new fields are confined to the new opt-in artifact and its harness; no existing reader or schema changed. B1: all 68 selections are retained. B3-B6: no gate, schema change, deployment, claim loop, move, or retirement exists. B8: no self-fit residual is called independent evidence. B9: denominators are the named 17 frames and 68 unique roles. B10: no threshold or gate moved.
- B11: the local route was executed repeatedly while correcting only a post-measurement CSV serialization defect; final output preserves the same fixed 17-frame construct and unchanged selection route. The focused deterministic helper test below covers the sign normalization used by every selection.

Focused verification in this worktree:

    python -m pytest tests/platformkit/test_g223_line_error_structure.py -q
    1 passed in 0.79s
