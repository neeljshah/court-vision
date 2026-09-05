# G289 - Implausible-step decomposition (2026-09-04)

VERDICT: MEASURED, measurement only, no pass bar. Detector-box observations: 4,090 implausible / 29,973 eligible same-ID consecutive-observation steps, 30,071 retained detector boxes, 1 clip, 1 span (19599-23399 inclusive), 1 non-deterministic draw. No ground truth of any kind; eye check NONE.

630/4,090 = 0.154034 (15.403 percent) of implausible steps moved 20 px or less in the image; the small-image-move amplification candidate covers only this minority, so it does not explain the dominant 3,460/4,090 = 0.845966 with larger image displacements.

Machine: DESKTOP-VUIITL8, Windows, local CPU, Python 3.10.0; reason: all measurements are arithmetic on committed JSON. Worktree: C:/Users/neelj/nba-track-a6, branch track-a6. No pod, GPU, decode or video opened.

## Baseline checked before decomposition

Imported scripts.platformkit.tracking.verifier_footpoint_analyses.steps() without modification. First command, before any displacement analysis:

```text
BASELINE FIRST: 4090 / 29973 = 0.136456
```

The unrounded rate is 0.13645614386280985; EXACT reproduction means the exact integer numerator and denominator and the published six-decimal display. The harness stops before decomposition if any disagree. Consecutive observations include non-unit gaps, using the imported 30 fps and strict >40 ft/s bar.

The verifier returns IDs and speeds only. A float subclass records endpoints when steps() subtracts court x coordinates, returning the identical numeric difference. There is no second pairing algorithm. Every observed ID and speed must exactly equal the uninstrumented output; every captured speed is checked against endpoint court distance and gap. The test independently matches all 4,090 captured endpoints and pixel distances to G267's existing implausible-step records.

## Complete displacement partition

Secant scale = court_feet / image_pixels: the average ft-per-px along the step, NOT the local Jacobian. For a short step the two converge; for a long one they do not. More precisely, that limit is directional and requires a single fixed differentiable mapping. G267 measure() composes a per-frame map, so these empirical cross-frame ratios can also include map changes; they cannot isolate the spatial Jacobian or establish horizon ill-conditioning.

The suggested bins are retained: zero isolates division by zero, 5 and 20 px describe small moves, 50 and 150 px separate progressively larger displacements. These are descriptive categories, not new decision rules. All 29,973 steps have both displacements, both endpoint coordinates and frame gaps in steps.csv. None is filtered.

| Image displacement (px) | Count | Share of 4,090 | Median secant scale (ft/px) | Median court distance (ft) |
|---|---:|---:|---:|---:|
| 0 | 17 | 0.004156 | undefined | 7.063756 |
| (0,5] | 157 | 0.038386 | 2.299537 | 5.618861 |
| (5,20] | 456 | 0.111491 | 0.346517 | 3.485953 |
| (20,50] | 749 | 0.183130 | 0.062393 | 1.893039 |
| (50,150] | 814 | 0.199022 | 0.043432 | 3.777285 |
| >150 | 1897 | 0.463814 | 0.042906 | 14.658075 |
| TOTAL | 4090 | 1.000000 | - | - |

```text
PARTITION SHARE SUM: 1.000
```

The unrounded shares sum to exactly 1.0 (printed 1.000). Independently rounded six-decimal cells sum to 0.999999, which also rounds to 1.000; the total uses unrounded shares. Every implausible step belongs to exactly one bucket.

Zero pixels: 1,228/29,973 eligible steps, of which 1,207 have nonzero court displacement and 21 have zero court displacement; 17/4,090 = 0.004156 of the implausible steps have zero image displacement. The ratio is undefined for all 1,228 (including 0/0), stored as JSON null / empty CSV, never infinity or a silently dropped step. Median secant scale is undefined for the zero bucket; other medians exclude only undefined ratios.

Among 613/4,090 = 0.149878 with nonzero displacement at most 20 px, the large empirical secant ratios are compatible with mapping-related amplification, but its causal share is not established because the two endpoints can use different maps. For 17/4,090 = 0.004156 with zero pixels and implausible court motion, spatial amplification through a single fixed homography alone is impossible; this is a coordinate inconsistency with that fixed-map premise, not proof that either frame's homography is wrong.

Large image displacements are directly observed for 3,460/4,090 = 0.845966 (>20 px), including 1,897/4,090 = 0.463814 (>150 px); their cause remains unexplained by this row. The mapping is exonerated as the dominant tiny-image-move explanation (the candidate is only 630/4,090 = 0.154034), not as a contributor to court distances on the remaining 3,460/4,090 = 0.845966. This is an exhaustive displacement partition, not an exhaustive causal attribution.

The historical bimodal-ID candidate accounted for 185/4,090 = 0.045232, leaving 3,905/4,090 = 0.954768 unexplained; G289 does not establish a new causal allocation that closes that historical residue. Its overlap with the 630 small-image steps is not measured, so those counts must not be subtracted as disjoint causes.

## Geometric signature by midpoint foot_y_px

Deciles use inclusive linear empirical quantiles of all eligible step midpoints. Equal midpoint values stay in the same cell (upper boundary inclusive), so eligible denominators vary slightly. Decile 1 has the smallest y, the expected far end. Median secant scale is for all steps in each decile with a defined ratio.

| Decile | Midpoint y interval (px) | Implausible numerator | Eligible steps whose midpoint falls in decile (denominator) | Implausible rate | Median secant scale (ft/px) |
|---:|---|---:|---:|---:|---:|
| 1 | (-inf, 412.875] | 525 | 2999 | 0.175058 | 0.065313 |
| 2 | (412.875, 490.500] | 442 | 3003 | 0.147186 | 0.054413 |
| 3 | (490.500, 556.125] | 435 | 2996 | 0.145194 | 0.050321 |
| 4 | (556.125, 623.625] | 384 | 3001 | 0.127957 | 0.046421 |
| 5 | (623.625, 694.125] | 472 | 2992 | 0.157754 | 0.044118 |
| 6 | (694.125, 783.000] | 614 | 3000 | 0.204667 | 0.039873 |
| 7 | (783.000, 858.750] | 452 | 3015 | 0.149917 | 0.038310 |
| 8 | (858.750, 928.125] | 423 | 2975 | 0.142185 | 0.026864 |
| 9 | (928.125, 970.875] | 242 | 3028 | 0.079921 | 0.027270 |
| 10 | (970.875, +inf] | 101 | 2964 | 0.034076 | 0.024116 |
| TOTAL | All midpoints | 4090 | 29973 | 0.136456 | - |

The profile is NOT FLAT: the farthest decile rate is 0.175058 versus 0.034076 at the nearest, and empirical secant medians are 0.065313 versus 0.024116 ft/px. It is also NOT MONOTONE: decile 6 peaks at 0.204667, above decile 1, and deciles 5 and 6 reverse the progression. Thus the stipulated monotone horizon signature is absent; the flat-profile refutation condition is not met either. No significance test or causal allocation is inferred from these dependent steps.

The small-image amplification candidate remains 630/4,090 = 0.154034; the y profile provides only partial descriptive support, not evidence that projective ill-conditioning causes that share or the unexplained 3,460/4,090 = 0.845966 remainder.

## Frame-gap confound

Each column has its own explicitly named eligible denominator. Zero counts are printed for absent gaps. This table enumerates every observed integer gap; gap 1 is not an eligibility condition.

| Frame gap | Implausible count / 4,090 eligible implausible steps | Share | Plausible count / 25,883 eligible plausible steps | Share |
|---:|---:|---:|---:|---:|
| 1 | 2961/4090 | 0.723961 | 23562/25883 | 0.910327 |
| 2 | 448/4090 | 0.109535 | 965/25883 | 0.037283 |
| 3 | 228/4090 | 0.055746 | 388/25883 | 0.014991 |
| 4 | 157/4090 | 0.038386 | 226/25883 | 0.008732 |
| 5 | 67/4090 | 0.016381 | 152/25883 | 0.005873 |
| 6 | 58/4090 | 0.014181 | 96/25883 | 0.003709 |
| 7 | 45/4090 | 0.011002 | 71/25883 | 0.002743 |
| 8 | 27/4090 | 0.006601 | 70/25883 | 0.002704 |
| 9 | 29/4090 | 0.007090 | 52/25883 | 0.002009 |
| 10 | 18/4090 | 0.004401 | 38/25883 | 0.001468 |
| 11 | 8/4090 | 0.001956 | 25/25883 | 0.000966 |
| 12 | 10/4090 | 0.002445 | 25/25883 | 0.000966 |
| 13 | 4/4090 | 0.000978 | 28/25883 | 0.001082 |
| 14 | 6/4090 | 0.001467 | 25/25883 | 0.000966 |
| 15 | 5/4090 | 0.001222 | 20/25883 | 0.000773 |
| 16 | 6/4090 | 0.001467 | 24/25883 | 0.000927 |
| 17 | 1/4090 | 0.000244 | 15/25883 | 0.000580 |
| 18 | 3/4090 | 0.000733 | 14/25883 | 0.000541 |
| 19 | 2/4090 | 0.000489 | 13/25883 | 0.000502 |
| 20 | 3/4090 | 0.000733 | 8/25883 | 0.000309 |
| 21 | 0/4090 | 0.000000 | 9/25883 | 0.000348 |
| 22 | 2/4090 | 0.000489 | 8/25883 | 0.000309 |
| 23 | 0/4090 | 0.000000 | 6/25883 | 0.000232 |
| 24 | 0/4090 | 0.000000 | 8/25883 | 0.000309 |
| 25 | 1/4090 | 0.000244 | 5/25883 | 0.000193 |
| 26 | 0/4090 | 0.000000 | 8/25883 | 0.000309 |
| 27 | 0/4090 | 0.000000 | 7/25883 | 0.000270 |
| 28 | 1/4090 | 0.000244 | 4/25883 | 0.000155 |
| 29 | 0/4090 | 0.000000 | 7/25883 | 0.000270 |
| 30 | 0/4090 | 0.000000 | 4/25883 | 0.000155 |
| TOTAL | 4090/4090 | 1.000000 | 25883/25883 | 1.000000 |

Gap median / p90 / maximum: implausible 1 / 4 / 28 frames; plausible 1 / 1 / 30. Gaps >1 occur in 1,129/4,090 = 0.276039 of implausible steps versus 2,321/25,883 = 0.089673 of plausible steps (about 3.08 times as frequent). Longer gaps are over-represented despite speed = court_feet * 30 / gap; speed normalisation may not fully absorb the gap confound. This is an association, not an assigned cause for the 1,129/4,090 = 0.276039.

## Scope and NOT VERIFIED

The population is DETECTOR-BOX OBSERVATIONS, not authenticated players. G286/G287 report about 0.208 of footpoints on a player's feet and 0.181 on overlay graphics. Those are footpoint-content proportions, not causal shares of the 4,090 steps. A same-ID step may connect two things that are not players at all.

ONE clip, ONE span (19599-23399), ONE draw of a NON-DETERMINISTIC research route. G241 found 808/1,201 records differed. The 4,090 is one realisation. G282 reproduced the rate at 0.136978 on an independent draw versus 0.136456 here: the rate is stable across those draws even where individual steps are not, without a variance claim from two draws. Per G278 the span is measurably friendlier than the clip (0.836 versus 0.656 court-bearing, p=0.0078); nothing here may be quoted clip-wide.

This row observes the geometry of a committed mapping and cannot say the homography is wrong; it can only assess evidence for ill-conditioning where these steps occur. There is NO ground truth of any kind, no verified player position anywhere, and no eye check.

NOT VERIFIED: a per-frame local Jacobian; a horizon location; separation of spatial scale from changes between frame mappings; correctness of any homography; identities or actual player speeds; a causal explanation for the 3,460/4,090 = 0.845966 larger-image residue; a causal allocation even for the 630/4,090 = 0.154034 small-image candidate; second-draw reproduction of this decomposition; anything clip-wide. No production change is proposed.

## Exact inputs, artifacts and reproduction

Opened measurement input (JSON has no raster resolution; coordinates refer to 1920x1080 pixels):

- `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g267_court_space_physical_plausibility_artifact\g267_measurement.json`: 12052299 bytes; SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`.

Inherited video provenance ONLY, not opened: `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps. No claims of local video access or visual validation.

Code identity (Python source resolution: not applicable):

- `C:\Users\neelj\nba-track-a6\scripts\platformkit\tracking\g289_implausible_step_decomposition.py`: 9477 bytes; SHA-256 `98328998b2e42a7435e42513089247bf371ff0994ec17930c9b75fb0d153c48b`.
- `C:\Users\neelj\nba-track-a6\scripts\platformkit\tracking\verifier_footpoint_analyses.py`: 8342 bytes; SHA-256 `558b8fd7ecce0b0123107c5962fd1061f7c2c2ff08ffd2a1b13f857baa0b4672`.
- Read-only provenance inspection: `C:\Users\neelj\nba-track-a6\scripts\platformkit\tracking\g267_court_space_physical_plausibility.py`, 12214 bytes, Python source (no raster resolution); measure() composes the map per frame. It was not imported or executed.

Artifacts (all beside this memo, all committed):

- [summary.json](g289_implausible_step_decomposition_artifact/summary.json): complete summaries, exact source identity, machine and limits.
- [steps.csv](g289_implausible_step_decomposition_artifact/steps.csv): all 29,973 steps with endpoints and measured quantities.
- [run_stdout.txt](g289_implausible_step_decomposition_artifact/run_stdout.txt): baseline first, full summary, printed partition sum.

Reproduce from this worktree:

```text
python -m scripts.platformkit.tracking.g289_implausible_step_decomposition
python -m pytest tests/platformkit/test_g289_implausible_step_decomposition.py -q
...                                                                      [100%]
3 passed in 1.75s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
.                                                                        [100%]
1 passed in 1.84s
```

The focused test pins 4,090/29,973 = 0.136456 and partition shares summing to exactly 1.0, all bucket counts, zero-pixel outcomes, every eligible decile/gap denominator, all archived per-step values, original G267 implausible endpoints, non-unit gaps, duplicate-frame handling and baseline failure. No full pytest run.

Self-check against [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) section B: B1 all verifier-eligible steps retained; B2 additive files only; B3-B6 no gates, claims, deployment or module retirement; B7 complete census, no head slice or renders; B8 no fit/ground-truth claim; B9 named observation-step denominators; B10 40 ft/s and imported steps unchanged; B11 single-draw limits explicit. A7 all evidence paths exist. A9 source identity above. A12 no existing allowlisted code file grew; new harness is below 300 lines and rail test passes. Q is not applicable to this descriptive tracking G-row. Memo and RESULTS_LEDGER.md row are in the same explicit-pathspec commit; verifier adjudication is pending.
