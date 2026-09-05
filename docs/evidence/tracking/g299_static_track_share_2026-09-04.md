# G299: static-track share of retained detector-box observations

**MEASURED; no pass bar; verifier pending. At the declared arbitrary primary cut of at least 20 observations and footpoint bounding-box diagonal below 25 px, 0/84 eligible IDs (from 98 total IDs) carry 0/30,071 = 0.000000 (0%) of all retained detector-box observations, across 29,973 consecutive-observation steps in ONE clip, ONE span (19599-23399), ONE non-deterministic draw.**

The answer is SMALL: zero at every declared cut. The hypothesis that this retained population is dominated by IDs that barely move over their entire retained history is unsupported. The "identity is healthy" framing survives this particular static-ID challenge. This is not new proof of healthy identity, real players, or absence of furniture: motion cannot authenticate a player. No share of G281's 0.935 purity has been attributed to furniture.

This follows [G299_spec.md](specs/G299_spec.md) and [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). Machine: DESKTOP-VUIITL8, Windows, local CPU, Python 3.10.0. Worktree: `C:/Users/neelj/nba-track-a3`, branch `track-a3`. Reason: entirely local arithmetic on committed coordinates. No pod, GPU, decode, disk guard, hold rule, image access, eye check, or ground truth.

## Population and method

The imported `verifier_footpoint_analyses.load_detections()` supplies G267's 3,801 frame records. All 30,071 finite retained detector-box observations remain, including off-court coordinates. They are 30,071 unique `(source_frame, track_id)` observations across 98 distinct emitted IDs. No player, identity, on-court, motion, or image-band condition was used to remove observations from the census or the all-detection denominator.

The imported `verifier_footpoint_analyses.steps()` supplies the unchanged same-ID consecutive-OBSERVATION definition, including non-unit frame gaps. G289's existing `measure_steps()` traces the endpoints selected by that function without creating another pairing rule. Every field of every one of the 29,973 committed G289 CSV steps is checked against that existing trace, including endpoints, ID, frame gap, image displacement, and speed. All match. No G289 artifact or partition is changed.

For every ID, [per_track.csv](g299_static_track_share_artifact/per_track.csv) reports observation count, step count, first/last frame, minimum/maximum footpoint x and y, total image path length, footpoint bounding-box diagonal, median step displacement, eligibility, and counts in each image band. Path length is the sum of its already defined G289 image displacements. Diagonal is `hypot(max(foot_x_px)-min(foot_x_px), max(foot_y_px)-min(foot_y_px))` over ALL its retained observations; this is the bounding box of footpoints, not a detector-box dimension. Median is over that ID's consecutive-observation step displacements, not net displacement or speed. Each ID has observation count minus one steps in this corpus.

The minimum of 20 observations and cuts of 10, 25, and 50 px are **ARBITRARY descriptive choices**, declared before measurement. The primary cut stays 25 px regardless of the result. Static means `observation_count >= 20 AND footpoint_bbox_diagonal_px < cut`; equality to the pixel cut is not static. These are measurement categories, not a proposed operational threshold or filter.

There are 84 eligible IDs carrying 29,990 retained observations. The 14 IDs below 20 observations carry 81/30,071 = 0.002694 of all retained detections. They are EXCLUDED from the eligible-ID denominator, not counted as non-static. Their 81 observations remain in the all-retained-detection denominator and in the full distribution. Their IDs are 9, 12, 21, 27, 28, 43, 50, 51, 58, 59, 79, 92, 96, and 98. Three singleton IDs have zero path and zero diagonal, and undefined median step displacement; the latter is null, not silently replaced with zero.

## Distribution across IDs

Quantiles use linear interpolation at rank `(n-1)*p`, giving equal weight to each ID, not each detection. Units are pixels except observation count. The complete unrounded distributions are in [summary.json](g299_static_track_share_artifact/summary.json).

| Population / quantity | Defined IDs / population IDs | Min | p10 | p25 | Median | p75 | p90 | p95 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All IDs: observation count | 98/98 | 1 | 9.70 | 52.00 | 120.00 | 452.00 | 841.70 | 1148.15 | 1639 |
| All IDs: path length px | 98/98 | 0.00 | 227.27 | 1392.98 | 5001.95 | 18304.31 | 32195.66 | 41002.37 | 58983.43 |
| All IDs: footpoint diagonal px | 98/98 | 0.00 | 147.67 | 628.27 | 1408.61 | 1858.51 | 2019.73 | 2050.93 | 2085.20 |
| All IDs: median step px | 95/98; 3 undefined | 0.38 | 1.65 | 4.80 | 7.50 | 11.04 | 17.24 | 31.68 | 405.10 |
| Eligible IDs: observation count | 84/84 | 20 | 47.60 | 85.75 | 200.50 | 506.25 | 930.60 | 1190.85 | 1639 |
| Eligible IDs: path length px | 84/84 | 167.74 | 888.00 | 2413.35 | 8061.79 | 22866.52 | 33157.11 | 43121.35 | 58983.43 |
| Eligible IDs: footpoint diagonal px | 84/84 | 99.88 | 444.06 | 848.98 | 1638.27 | 1929.08 | 2030.05 | 2056.00 | 2085.20 |
| Eligible IDs: median step px | 84/84 | 0.38 | 2.10 | 4.86 | 7.57 | 10.63 | 15.00 | 21.02 | 41.49 |

The smallest eligible-ID diagonal is 99.876139 px. None is near any declared static cut. A small median step is compatible with a large lifetime extent; neither the median nor occasional zero steps establishes a static ID.

## Three-cut sensitivity, with all-detection shares

| Arbitrary strict diagonal cut; minimum 20 observations | Static IDs / eligible IDs | Static-ID share of eligible IDs | Detections carried by static IDs / ALL retained detections | Detection share |
| --- | ---: | ---: | ---: | ---: |
| <10 px | 0/84 | 0.000000 | 0/30,071 | 0.000000 (0%) |
| <25 px, primary | 0/84 | 0.000000 | 0/30,071 | 0.000000 (0%) |
| <50 px | 0/84 | 0.000000 | 0/30,071 | 0.000000 (0%) |

The denominator of each ID share is the 84 IDs with at least 20 observations. The denominator of each detection share is all 30,071 retained detector-box observations, including those belonging to ineligible IDs. The sets of static IDs are empty at all three cuts.

The supporting zero-step premise reproduces: 1,228/29,973 = 0.040970 steps have exactly zero image displacement. Their median court displacement is 0.001490 ft over all 1,228 zero-image steps. Restricting that median to the 1,207 with nonzero court displacement gives 0.001557 ft, consistent with the cited approximately 0.0016 ft; these denominators differ. These zero steps do not imply zero motion across the IDs' full histories. No landed number is revised.

## Image-band cross-tab

Bands reproduce the verifier's inclusive endpoints exactly: y 0-89, 90-300, 850-980, and 990-1079 px. `other` includes all remaining y values, including gaps between those bands. These are location names, not content labels. Every retained observation belongs to exactly one row.

| Image band | All band detections / all retained detections | Baseline detection share |
| --- | ---: | ---: |
| Top strip, 0-89 | 24/30,071 | 0.000798 |
| Score-bug band, 90-300 | 1,084/30,071 | 0.036048 |
| Lower-third band, 850-980 | 9,561/30,071 | 0.317948 |
| Bottom strip, 990-1079 | 19/30,071 | 0.000632 |
| Other y | 19,383/30,071 | 0.644575 |
| Total | 30,071/30,071 | 1.000000 |

The cross-tab below names the eligible-ID denominator at every cut. "Touching" means at least one retained footpoint in the band; IDs could touch multiple bands, so ID counts are not generally additive. Detection counts are additive. Here every static-ID set is empty.

| Cut px | Band | Static IDs touching band / eligible IDs | Static band detections / ALL retained detections | Static band detections / all detections in band |
| ---: | --- | ---: | ---: | ---: |
| <10 | Top | 0/84 | 0/30,071 = 0 | 0/24 = 0 |
| <10 | Score-bug | 0/84 | 0/30,071 = 0 | 0/1,084 = 0 |
| <10 | Lower-third | 0/84 | 0/30,071 = 0 | 0/9,561 = 0 |
| <10 | Bottom | 0/84 | 0/30,071 = 0 | 0/19 = 0 |
| <10 | Other | 0/84 | 0/30,071 = 0 | 0/19,383 = 0 |
| <25 | Top | 0/84 | 0/30,071 = 0 | 0/24 = 0 |
| <25 | Score-bug | 0/84 | 0/30,071 = 0 | 0/1,084 = 0 |
| <25 | Lower-third | 0/84 | 0/30,071 = 0 | 0/9,561 = 0 |
| <25 | Bottom | 0/84 | 0/30,071 = 0 | 0/19 = 0 |
| <25 | Other | 0/84 | 0/30,071 = 0 | 0/19,383 = 0 |
| <50 | Top | 0/84 | 0/30,071 = 0 | 0/24 = 0 |
| <50 | Score-bug | 0/84 | 0/30,071 = 0 | 0/1,084 = 0 |
| <50 | Lower-third | 0/84 | 0/30,071 = 0 | 0/9,561 = 0 |
| <50 | Bottom | 0/84 | 0/30,071 = 0 | 0/19 = 0 |
| <50 | Other | 0/84 | 0/30,071 = 0 | 0/19,383 = 0 |

At each of <10, <25, and <50 px, static IDs are 0/84 eligible IDs and carry zero detections; a band's share *within static detections* is therefore 0/0, undefined, stored as null. It is not a zero-valued distribution over static locations.

**THE LOWER-THIRD BAND IS ALSO WHERE THE NEAR COURT IS.** Its 9,561/30,071 = 0.317948 baseline occupancy is not by itself evidence of furniture. This row makes no content inference from that band and does not repeat the withdrawn spatial-histogram claim.

## Relationship to G281 and required limits

G287's landed memo reports 32/72 footpoints on a player's feet or body and 13/72 = 0.181 on graphics. G288 describes 13/13 of that graphic subset as overlays. Those historical sample results motivated the question; this row reads the requested memos, not blind verdict files, crops, labels, or unblind maps.

G281's memo and ledger report the historical 0.935 among 46 judgeable person-person pairs, following 80 sampled pairs and 62 both-endpoints-person pairs from 15,207 eligible one-second pairs. That is a different, conditioned denominator from this 30,071-observation motion census. G281's coarse crop-neighbourhood judgments also do not certify the precise footpoint. This row does not recompute or rerun purity, has no per-track identity labels, and cannot identify overlap between its static category and G281's judged pairs. **It CANNOT attribute a share of the 0.935 to furniture.** A furniture-heavy whole-ID static population was one possible challenge to the broad framing; it is not present under these declared cuts. That finding leaves G281's bounded historical evidence intact without establishing that the moving detector boxes are real players.

STATIC IS NOT THE SAME AS FURNITURE. A player standing still, a track living entirely during a held camera, or a short id in a static shot all look static, and this row has NO image evidence and NO eye check to tell them apart -- naming furniture would need crops this row does not render. The camera moves, so screen-fixed overlay graphics are static in image space while the court is not; that is the signal being used and it is INDIRECT. ONE clip, ONE span (19599-23399), ONE draw of a non-deterministic route (G241: 808 of 1,201 records differed). Per G278 the span is measurably friendlier than the clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. The population is detector-box observations, not authenticated players -- every denominator is named.

## NOT VERIFIED

- Furniture identity, player identity, true player motion, or any visual correctness; there is no image evidence, eye check, or ground truth.
- Static stretches within moving IDs. A rare excursion can make a mostly stationary ID exceed every lifetime-diagonal cut; this row measures whole retained IDs, not stationary-duration share.
- Whether an ID moves between people, overlays, floor, or other content, or why its footpoint moves.
- Any decomposition, new estimate, causal attribution, or per-track explanation of G281's 0.935 purity.
- Identity fragmentation, identity correctness between endpoints, or usefulness of per-player quantities.
- Another clip, span, shot, arena, sport, detector draw, or repeatability of these per-ID findings; nothing is clip-wide.

No filter, threshold, gate, retrain, or production change is proposed. No bar, source record, landed count, landed artifact, or verdict was changed. `src/`, `domains/`, and the orchestrator-owned `TRACKING_GAPS_2026-09-01.md` were not edited.

## Exact inputs, code identity, and reproduction

Opened measurement inputs (text files have no raster resolution; coordinates refer to 1920x1080):

- `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`: 12,446,681 bytes; SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`.
- `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv`: 6,336,759 bytes; SHA-256 `180e5b2bc8d7adbcebfd19dcb8128a8e9a872aa839c32d96e9f68e6a62bb24a0`.

G267's local Windows checkout uses CRLF. Normalizing CRLF to LF **in memory only** gives 12,052,299 bytes and SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`, exactly the G281/G289 memo source identity. The on-disk input was not rewritten. Numeric step reconciliation independently confirms all archived G289 measurements.

Inherited video provenance ONLY, never opened: `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps, frames 19599-23399 inclusive. This is not a claim of local video access.

Opened analysis code (Python source, raster resolution not applicable):

- `C:/Users/neelj/nba-track-a3/scripts/platformkit/tracking/g299_static_track_share.py`: 11,123 bytes; SHA-256 `c281b41e7d2d909097ba9e53481d42fa0b314fb9b792dbbfd19291c96fcde27a`.
- `C:/Users/neelj/nba-track-a3/scripts/platformkit/tracking/verifier_footpoint_analyses.py`: 10,462 bytes; SHA-256 `a0da6bd99dc5c6b257340be8d125ea48d5420bec29c54f473e1150d03974151c`.
- `C:/Users/neelj/nba-track-a3/scripts/platformkit/tracking/g289_implausible_step_decomposition.py`: 9,655 bytes; SHA-256 `6663b97b45fcffa8c13731afa3affe90f426a5badd54435655da6c47883df9b9`.

Artifacts committed with this memo: [per_track.csv](g299_static_track_share_artifact/per_track.csv), [summary.json](g299_static_track_share_artifact/summary.json), and [run_stdout.txt](g299_static_track_share_artifact/run_stdout.txt). The summary includes exact source and code identities, machine, denominators, distributions, all three cut/band results, and limits.

Pasted local measurement and per-file test output:

```text
python -m scripts.platformkit.tracking.g299_static_track_share
CENSUS: 30071 retained detector-box observations, 98 IDs, 29973 steps
ARBITRARY diagonal <10 px, n>=20: 0/84 eligible IDs; 0/30071 retained detections = 0.000000000
ARBITRARY diagonal <25 px, n>=20: 0/84 eligible IDs; 0/30071 retained detections = 0.000000000
ARBITRARY diagonal <50 px, n>=20: 0/84 eligible IDs; 0/30071 retained detections = 0.000000000

python -m pytest tests/platformkit/test_g299_static_track_share.py -q
.....                                                                    [100%]
5 passed in 2.61s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
.                                                                        [100%]
1 passed in 1.97s
```

The focused test pins footpoint **diagonal**, distinguishes it from path length, per-axis extent, median and net motion, pins strict equality at the cut, and proves that a 19-observation ID is excluded from the eligible denominator while its detections remain in the all-observation denominator. It also tests inclusive bands and gaps, undefined medians and empty-static fractions, and the full committed coordinate/step census against the archived summary. No full pytest was run.

Contract self-check: B1 all retained observations preserved, 14 short IDs explicitly excluded only from eligibility; B2 additive code/artifacts and appended ledger only; B3-B6 no gate, claim lifecycle, deployment, or retirement; B7 complete census, no sampled head or render; B8 no fit or ground-truth claim; B9 unique frame-ID units checked and detector-box denominators named; B10 existing steps and all landed bars unchanged, arbitrary descriptive cuts predeclared; B11 strictly one-span, one-draw claims. A7 all linked evidence paths exist; A9 exact source identity above; A12 no existing allowlisted source grew, the new source is below 300 lines and the per-file rail passed. Q is not applicable to this descriptive G-row. Memo and RESULTS_LEDGER row are in the same explicit-pathspec commit; no push. External verifier adjudication is pending.
