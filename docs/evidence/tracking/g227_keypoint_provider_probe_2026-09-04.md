# G227 Keypoint Provider Probe

## Status

CLOSED AT LIMIT. The one declared local arm completed with 0/17 all-four frames, 0/68 corner availability, and 17/17 abstentions. No filters, tolerance, scorer, corpus, or protected module was changed after seeing this result.

## Contract and machine

- Spec: `docs/evidence/tracking/specs/G227_spec.md`.
- Verifier contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`; this is a tracking G-row, with section B self-checked before reporting.
- Machine: local `C:/Users/neelj/nba-track-a3` only. The specification reserves pod work for G211; this probe does not use SSH, a pod, a daemon, or a deployment.

## Fixed configuration, declared before results

- Candidate: `BasketballKeypointProvider(min_edge_support=0.16)`, the provider default. There are no alternate support values, no secondary arms, and no per-frame tuning.
- Input: native BGR pixels with no resize, crop, or pre-processing beyond the provider's own fixed code.
- Scorer: imported unchanged from `scripts/platformkit/tracking/g205_zero_shot_corner_probe.py`: `score_frame` and `TOLERANCE_PX = 12.0`.
- Corpus: all 17 rows groups (68 target corners) in `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`; resolved source files are under `docs/evidence/tracking/g130_recensus/source_decodes/`.
- Render selection: sorted construct indices 0, 4, 8, 12, and 16; also render the lowest maximum direct mapped-corner distance, even if no frame passes.

## Landmark-to-role mapping

The provider defines the selected baseline as the shorter opposite-side pair, orders that pair by image y, then emits `left_paint_bl`, `left_paint_tl`, `left_paint_tr`, and `left_paint_br` in that sequence at `domains/basketball/tracking/keypoints.py:96-115`. The fixed mapping is:

| G140 role | Provider landmark |
|---|---|
| `paint_near_baseline_left_corner` | `left_paint_bl` |
| `paint_near_baseline_right_corner` | `left_paint_tl` |
| `paint_near_free_throw_left_corner` | `left_paint_br` |
| `paint_near_free_throw_right_corner` | `left_paint_tr` |

The harness will preserve this mapping in each target row and calculate a direct mapped-role distance solely as a mapping audit. The headline continues to use G205's unchanged generic `score_frame` availability rule.

## Planned output paths

- `docs/evidence/tracking/g227_keypoint_provider_probe/summary.json`
- `docs/evidence/tracking/g227_keypoint_provider_probe/per_frame.csv`
- `docs/evidence/tracking/g227_keypoint_provider_probe/target_scores.csv`
- `docs/evidence/tracking/g227_keypoint_provider_probe/proposal_scores.csv`
- `docs/evidence/tracking/g227_keypoint_provider_probe/renders/`

All planned paths exist after the run.

## Input inventory

The label input was `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` (15,633 bytes, 68 rows). Each source opened is named below with its full local path, byte size, and native resolution. This is the exhaustive 17-frame construct, not a sample.

| Audit id | Source path | Bytes | Resolution | League | Abstained | All four G205 | Contours | Contours at fixed 120 px |
|---|---|---:|---|---|---|---|---:|---:|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg` | 605623 | 1920x1080 | ncaa_basketball | True | False | 1970 | 594 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg` | 584472 | 1920x1080 | ncaa_basketball | True | False | 1955 | 570 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg` | 106044 | 640x360 | ncaa_basketball | True | False | 817 | 115 |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg` | 689352 | 1920x1080 | ncaa_basketball | True | False | 2779 | 549 |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg` | 297020 | 1280x720 | ncaa_basketball | True | False | 1291 | 277 |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg` | 308901 | 1280x720 | ncaa_basketball | True | False | 1504 | 305 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg` | 679804 | 1920x1080 | ncaa_basketball | True | False | 3090 | 495 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg` | 531457 | 1920x1080 | ncaa_basketball | True | False | 1848 | 345 |
| `wnba__wnba_01_1080p__s01__f001600` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s01__f001600.jpg` | 621798 | 1920x1080 | wnba | True | False | 3254 | 651 |
| `wnba__wnba_01_1080p__s03__f004062` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s03__f004062.jpg` | 629254 | 1920x1080 | wnba | True | False | 3096 | 662 |
| `wnba__wnba_01_1080p__s06__f007539` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s06__f007539.jpg` | 535379 | 1920x1080 | wnba | True | False | 2132 | 517 |
| `wnba__wnba_02__s11__f021983` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_02__s11__f021983.jpg` | 251244 | 1280x720 | wnba | True | False | 1060 | 277 |
| `wnba__wnba_04__s06__f012223` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_04__s06__f012223.jpg` | 238301 | 1280x720 | wnba | True | False | 680 | 229 |
| `wnba__wnba_06__s03__f007237` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s03__f007237.jpg` | 598645 | 1920x1080 | wnba | True | False | 3041 | 520 |
| `wnba__wnba_06__s07__f014099` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s07__f014099.jpg` | 530179 | 1920x1080 | wnba | True | False | 2163 | 448 |
| `wnba__wnba_06__s09__f018997` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s09__f018997.jpg` | 622191 | 1920x1080 | wnba | True | False | 3220 | 538 |
| `wnba__wnba_07__s08__f016801` | `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_07__s08__f016801.jpg` | 504523 | 1920x1080 | wnba | True | False | 1788 | 431 |

## Measurement result

| Metric | Overall | NCAA | WNBA |
|---|---:|---:|---:|
| Frames with all four within 12 px, unchanged G205 scorer | 0/17 | 0/8 | 0/9 |
| Per-corner recall, unchanged G205 scorer | 0/68 | 0/32 | 0/36 |
| Selected paint quads | 0/17 | 0/8 | 0/9 |
| Abstentions: no paint quad survived the provider | 17/17 | 8/8 | 9/9 |
| Proposed-but-missed frames | 0/17 | 0/8 | 0/9 |
| Named corner proposals | 0 total; 0.0/frame | 0 | 0 |
| Selected quads per frame | 0.0 | 0.0 | 0.0 |

This is a low-proposal-count zero-recall outcome: the provider did not produce a wrong lane quad; it produced no lane quad at all. `per_frame.csv` records every abstention, and `target_scores.csv` preserves all 68 unavailable target rows rather than excluding them.

## Mapping sanity check

Before the full run, sorted frame 0 (`ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973`) was run once with the declared mapping. The harness printed all four role-to-provider names in the table above and then recorded no selected quad and four infinite direct mapped-role distances. The result was retained; mapping, support, threshold, and filters were not changed.

## Renders and eye check

The five evenly spaced overlays are `renders/00_...jpg`, `renders/04_...jpg`, `renders/08_...jpg`, `renders/12_...jpg`, and `renders/16_...jpg` under `docs/evidence/tracking/g227_keypoint_provider_probe/`. The explicit closest-frame render is `renders/closest_00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg`; all direct mapped distances are infinite, so the stable sorted-index tie break selected frame 0.

Visual review of all five evenly spaced renders found the four red G140 target markers and no green provider marker or cyan selected quad on each. The closest render is identical to index 0 and likewise shows an abstention. These are no-proposal overlays, not a head-slice result.

## Lane-width and mixed-resolution treatment

`scripts/platformkit/calibration/keypoint_calib.py:19-29` retains the existing 16 ft paint width (y=17 to y=33) for all basketball calls, although 8 construct frames are NCAA. It was not edited. The provider's paint candidate and its baseline-adjacency naming do not reference `CANONICAL_LANDMARKS`; the 16 ft model is first used only in the optional circle-homography path after a paint quad has already been selected. Since all NCAA and WNBA frames abstained before that point, this mismatch does not plausibly explain a paint-quad detection failure here. It could matter for later circle naming or calibration, which was not measured.

The corpus has 12 1920x1080 frames, 4 1280x720 frames, and 1 640x360 frame. The provider's area and shortest-side gates remain its untouched frame-fraction filters. Its Canny thresholds (50/150) and contour-perimeter cutoff (120 px) remain absolute as required. Rather than rescale the 640x360 frame silently, the harness records the provider-equivalent fixed-gate diagnostic: it had 817 raw contours and 115 contours at or above 120 px. The primary run still passed native pixels to the unmodified provider; this diagnostic is not a new scorer or a relaxed arm.

## Reproducibility

The measured route files had these local SHA-256 values at run time:

| File | SHA-256 |
|---|---|
| `domains/basketball/tracking/keypoints.py` | `38209F49E470688B37182FF38CE0D96CE89EB42DD802E32D9A8954245870D943` |
| `scripts/platformkit/tracking/g205_zero_shot_corner_probe.py` | `63C32795C57482E2B2CA2BA5E055C3DD3CA32CB5735F9B96378617B96320CF60` |
| `scripts/platformkit/tracking/g227_keypoint_provider_probe.py` | `F300898C79DA85EAC55A265DA07CB6FA3AECA4738DBE92E6780845E6C53EBC11` |

Run locally from this worktree with `python -m scripts.platformkit.tracking.g227_keypoint_provider_probe`.

## Limitations and NOT VERIFIED

- This is the fixed, exhaustive 17-frame construct, not an estimate of a population rate.
- G140's reported p90 label repeatability is 11.39 px; the unchanged 12 px protocol is at that label-noise floor. A pass would only establish a roughly correct proposal, not production accuracy.
- NOT VERIFIED: whether a separately trained model can detect these paint corners; that next route must cite G31.
- NOT VERIFIED: whether changing any provider threshold, lane model, Canny threshold, or 120 px perimeter would help. Those changes were outside this fixed no-tuning probe.
- NOT VERIFIED: any downstream circle, homography, or player-coordinate result; no paint quad was available to start those paths.

## Verifier self-check

- B1: all 17 frames and all 68 target rows remain in the denominator; abstentions are explicit rows, not excluded data.
- B2-B4 and B6: no existing schema, reader, gate, or claim lifecycle was changed; the harness and artifacts are additive.
- B5: no pod copy or deployment occurred.
- B7: renders use the five fixed evenly spaced indices plus the explicit closest frame, not a leading slice.
- B8-B9: no fit, residual-derived claim, or recycled denominator is used.
- B10: `score_frame` and its 12 px tolerance are imported unchanged and asserted in the harness.
