# G294 - Gap-conditioned implausibility (2026-09-04)

VERDICT: MEASURED, measurement only, no pass bar; 4,090 implausible / 29,973 eligible same-ID consecutive-observation steps from detector-box observations, 1 clip, 1 span (19599-23399 inclusive), 1 non-deterministic draw; not authenticated players, no ground truth, eye check NONE, not clip-wide; verifier adjudication pending.

**One-sentence answer:** Steps spanning retained-record dropouts carry 1,129/4,090 = 0.276039 of implausible steps (1,129/29,973 = 0.037667 of all eligible detector-box steps), with gap composition accounting for 0.181869 of the observed rate under gap-1 standardisation and descriptively super-linear median displacement exponents of 1.221585 (court, SE 0.185403) and 1.239337 (image, SE 0.182517), making re-acquisition after a dropout a candidate worth the next measurement, not an established or dominant mechanism.

Machine: DESKTOP-VUIITL8, Windows, local CPU, Python 3.10.0; reason: arithmetic on the sole committed CSV. Worktree: C:/Users/neelj/nba-track-a3, branch track-a3. No pod, GPU, decode, video, disk guard or hold rule used.

## Reproduction first

Read [G294_spec.md](specs/G294_spec.md) and [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) in full, the G289 memo and its historical ledger row at `3f2000f20`, and G290's VERIFIER NOTE at `121382d11`. The latter cautions against treating a conditioned statistic as an unconditioned result. This row conditions explicitly on gap, includes all eligible steps within each bucket, and labels the fits descriptive.

The first CSV calculation reproduced every required integer count and rounded figure before any decomposition. The harness stops on a mismatch; none occurred. Pasted check:

```text
REPRODUCTION FIRST (all required figures MATCH):
baseline: 4090/29973 = 0.136456144
gap1_share_implausible: 2961/4090 = 0.723960880
gap1_share_plausible: 23562/25883 = 0.910327242
gap1_rate: 2961/26523 = 0.111638955
gap_above1_rate: 1129/3450 = 0.327246377
gap_above1_share_all: 3450/29973 = 0.115103593
gap_above1_share_implausible: 1129/4090 = 0.276039120
rate ratio gap>1/gap1: 2.931292014
```

Baseline six-decimal display: 4,090/29,973 = 0.136456. Gap 1 four-decimal display: 2,961/26,523 = 0.1116. The above-1 rate is nearly three times the gap-1 rate. The stored `implausible` flag is read directly; no steps are re-derived, no pairing is repeated, and the original strict >40 ft/s definition is unchanged.

## Complete gap census

Each metric cell names its eligible denominator: **all steps at that gap**, plausible and implausible together. Medians are order statistics of exactly that many measurements, not ratios of their values to those counts. The seven counts sum to 29,973 eligible steps; implausible numerators sum to 4,090. Any bucket below 30 eligible steps is marked TOO SMALL TO READ; none of these seven buckets is below 30. Pooling 6-10 and above 10 is prescribed, not a claim that every individual gap in those pools has 30 steps.

| Gap | Median gap (frames) | Implausible rate | Median court ft | Median image px | Median speed ft/s | Cell mark |
|---|---|---|---|---|---|---|
| 1 | 1 (26523 eligible steps at this gap) | 2961/26523 = 0.111639 (26523 eligible steps at this gap) | 0.237733 (26523 eligible steps at this gap) | 5.625781 (26523 eligible steps at this gap) | 7.131982 (26523 eligible steps at this gap) | OK (>=30 steps) |
| 2 | 2 (1413 eligible steps at this gap) | 448/1413 = 0.317056 (1413 eligible steps at this gap) | 0.968981 (1413 eligible steps at this gap) | 27.093588 (1413 eligible steps at this gap) | 14.534716 (1413 eligible steps at this gap) | OK (>=30 steps) |
| 3 | 3 (616 eligible steps at this gap) | 228/616 = 0.370130 (616 eligible steps at this gap) | 1.688489 (616 eligible steps at this gap) | 43.947796 (616 eligible steps at this gap) | 16.884888 (616 eligible steps at this gap) | OK (>=30 steps) |
| 4 | 4 (383 eligible steps at this gap) | 157/383 = 0.409922 (383 eligible steps at this gap) | 2.939385 (383 eligible steps at this gap) | 73.151918 (383 eligible steps at this gap) | 22.045390 (383 eligible steps at this gap) | OK (>=30 steps) |
| 5 | 5 (219 eligible steps at this gap) | 67/219 = 0.305936 (219 eligible steps at this gap) | 2.163102 (219 eligible steps at this gap) | 64.504360 (219 eligible steps at this gap) | 12.978610 (219 eligible steps at this gap) | OK (>=30 steps) |
| 6-10 | 7 (504 eligible steps at this gap) | 177/504 = 0.351190 (504 eligible steps at this gap) | 5.989298 (504 eligible steps at this gap) | 143.799824 (504 eligible steps at this gap) | 23.642147 (504 eligible steps at this gap) | OK (>=30 steps) |
| above 10 | 16 (315 eligible steps at this gap) | 52/315 = 0.165079 (315 eligible steps at this gap) | 6.777805 (315 eligible steps at this gap) | 178.600812 (315 eligible steps at this gap) | 12.420706 (315 eligible steps at this gap) | OK (>=30 steps) |

Gap >1 pooled: 1,129/3,450 = 0.327246. The rate is **not monotone**: it peaks at 157/383 = 0.409922 for gap 4, declines at gap 5, and falls to 52/315 = 0.165079 above 10. It remains above gap 1 in every reported bucket. No rows, zero displacements or plausible steps were discarded.

## Scaling measured directly

Fit `ln(median displacement) = intercept + exponent * ln(median observed gap)` by unweighted OLS through the seven bucket medians. The horizontal coordinates are 1, 2, 3, 4, 5, 7 and 16 frames; 7 and 16 are empirical median gaps among the 504 and 315 eligible steps in the pooled buckets, respectively. This choice was stated before fitting; it avoids inventing a midpoint for an open-ended bucket. Each bucket gets one equal fit weight, irrespective of its eligible denominator; within-bucket gap distributions are compressed.

- Court displacement exponent: **1.221585**, standard error **0.185403**.
- Image displacement exponent: **1.239337**, standard error **0.182517**.

For both, `SE = sqrt((sum squared log residuals / (7 - 2)) / sum squared centred log gaps)`, using residual degrees of freedom 5. This is the nominal OLS residual-based standard error, not a dependence-adjusted uncertainty estimate. **A log-log fit through 7 medians is a DESCRIPTIVE summary on dependent data, not an inferential test. No p-value is supplied.** Adjacent steps share observations and tracks; seven bins are not seven independent experiments. The modest excess over 1 relative to those nominal SEs does not establish population super-linearity.

An exponent near 1 describes distance linear in gap, consistent with the stipulated genuine-motion model and gap-invariant speed. Near 0 describes gap-independent distance, consistent with the stipulated unrelated-object jump model, whose speed falls as 1/gap. Both point estimates exceed 1, so this summary is super-linear, in both image and court coordinates; neither idealized model predicts that summary. This does not identify which observations are people or why a transition happened.

The enrichment alone does **not mathematically require** super-linear median displacement: the implausible rate concerns the tail above a gap-dependent distance boundary, and a tail probability does not determine a median. This row measured the medians directly. Neither the rate nor displacement follows one clean monotone power law across these buckets, so the descriptive exponent must not become a universal dynamics claim.

## Standardisation and magnitude

If every one of the 29,973 eligible steps had gap 1's rate, the corpus rate would be **2,961/26,523 = 0.111638955**, versus the observed **4,090/29,973 = 0.136456144**. Using exact count-derived rates, not the rounded six-decimal baseline:

`gap-composition share = ((4090/29973) - (2961/26523)) / (4090/29973)`

**Gap-composition share: 0.181869.**

This is a **decomposition of the rate, not a causal attribution**. A step spans a gap because the tracker lost the object in the retained record sequence, and losing it may be a consequence of the same thing that makes the step wrong. A gap is a property of retained records: intervening detections were absent or dropped, and this row cannot tell those apart. Here "dropout" names that observable gap, not a proven internal tracker event.

The carried share 1,129/4,090 = 0.276039 counts *all* implausible above-1 steps; the composition share counts only the arithmetic excess over assigning them the gap-1 rate. They are different quantities and must not be interchanged.

## Overlap with existing candidates

G289's existing small-image-move definition is <=20 px, including zero. Its count reproduces as 630/4,090 = 0.154034. The following cells partition all 4,090 eligible implausible steps:

| Retained-record gap | Small image move <=20 px | Larger image move >20 px | Row total |
|---|---|---|---|
| 1 | 623/4090 eligible implausible steps | 2338/4090 eligible implausible steps | 2961/4090 eligible implausible steps |
| Above 1 | 7/4090 eligible implausible steps | 1122/4090 eligible implausible steps | 1129/4090 eligible implausible steps |
| Total | 630/4090 eligible implausible steps | 3460/4090 eligible implausible steps | 4090/4090 eligible implausible steps |

**Overlap: 7** of the 1,129 eligible implausible gap-above-1 steps also have a small image move (7/1,129 = 0.006200); equivalently, 7 of the 630 eligible small-image implausible steps span a gap above 1 (7/630 = 0.011111). The union is 1,752/4,090 = 0.428362; 2,338/4,090 = 0.571638 fall in neither category. These are overlapping descriptive categories, not causal allocations.

Within G289's larger-image residue, 1,122/3,460 = 0.324277 eligible larger-image implausible steps span a gap above 1, leaving 2,338/3,460 = 0.675723 at gap 1. Thus the lead covers a material minority and does not close G289's 3,460/4,090 = 0.845966 causally unexplained residue. Re-acquisition after a dropout merits a next measurement as a candidate for that minority; this row does not establish it as the leading explanation for the whole defect.

The historical bimodal-ID set remains a previously reported **185/4,090 = 0.045232** of implausible steps. Its overlap is **NOT COMPUTABLE from the specified sole input**: steps.csv has track IDs but no historical bimodal membership flag or sealed list defining that set. This row does not reconstruct or redefine that set, assume it disjoint, add its share, or revive the withdrawn mechanism claim. Both the gap/bimodal and small-image/bimodal intersections remain unmeasured.

## Limits and NOT VERIFIED

- ONE clip, ONE span (19599-23399), ONE draw of a non-deterministic route. G241 found 808 of 1,201 compared records differed. G282 reproduced the aggregate rate at 0.136978 on an independent draw (denominator: eligible consecutive-observation steps in that draw); this is inherited evidence for the rate, not a repeat of G294's buckets, fits or overlap.
- G278 found the span measurably friendlier: painted-court category (a) in 51/61 within-span reviewed frames = 0.836 versus 118/180 clip-wide reviewed frames = 0.656, nominal p=0.0078. Nothing in this row may be quoted clip-wide. That inherited p-value is not a significance test of these fits.
- The population is detector-box observations, not authenticated players. G287's direct centre-cross finding puts only 15/72 reviewed detector footpoints = 0.208 on a player's feet. That is a footpoint-content proportion, not a share of these steps; a step may connect two things that are not players at all.
- NO ground truth and NO eye check in G294; no visual or physical validation is implied. Identity, genuine speed, correct court mapping, whether a missing detection was absent or dropped, and a causal dropout/re-acquisition mechanism are NOT VERIFIED.
- Independence, inferential super-linearity, a power law at every exact gap, second-draw reproduction of this decomposition, bimodal overlaps, causal allocation of either candidate bucket, and any clip-wide or system-wide claim are NOT VERIFIED.

No filter, threshold, gate, retrain or production change is proposed. The 40 ft/s bar, steps() definition, G289 CSV/counts/partition/gap table, G267 records/span and every prior verdict remain unchanged. No src/ or domains/ edits or imports occurred.

## Source and committed reproduction evidence

Sole measurement input opened:

`C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv`

- Byte size: **6336759**.
- SHA-256: `180e5b2bc8d7adbcebfd19dcb8128a8e9a872aa839c32d96e9f68e6a62bb24a0`.
- Resolution: CSV has no raster resolution; inherited image coordinates refer to 1920x1080 pixels. No video opened.

Evidence files, all local and committed with this memo:

- [summary.json](g294_gap_conditioned_implausibility_artifact/summary.json): full-precision results, input identity, machine and limitations.
- [per_gap.csv](g294_gap_conditioned_implausibility_artifact/per_gap.csv): all seven medians, eligible denominators, counts and small-cell flags.
- [run_stdout.txt](g294_gap_conditioned_implausibility_artifact/run_stdout.txt): reproduction check and denominator-bearing table, ASCII.
- Harness: `scripts/platformkit/tracking/g294_gap_conditioned_implausibility.py`.
- Test: `tests/platformkit/test_g294_gap_conditioned_implausibility.py`.

Commands and pasted per-file test output:

```text
python -m scripts.platformkit.tracking.g294_gap_conditioned_implausibility
python -m pytest tests/platformkit/test_g294_gap_conditioned_implausibility.py -q
.....                                                                    [100%]
5 passed in 1.57s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
.                                                                        [100%]
1 passed in 2.06s
```

The focused test pins the baseline 0.136456, gap-1 rate 0.1116, every bucket numerator/eligible denominator, an independently defined exhaustive and disjoint interval partition, all four overlap cells, the standardisation, failure before decomposition on altered counts, small-cell retention/marking, known scaling exponents and a hand-computable residual standard error. No full pytest.

Contract self-check: B1 complete census, no excluded failing rows; B2 additive harness/artifacts, no schema changes; B3-B6 no gates, claim lifecycle, deployment or module retirement; B7 all steps, no head slice; B8 descriptive same-data fit, no independent validation claim; B9 named step denominators; B10 original bar and definitions unchanged; B11 one-draw limits explicit. A7 evidence paths exist; A9 sole measurement input identity above; A12 no existing allowlisted file grew, new harness below 300 lines, LOC rail passed. Q does not apply to this descriptive tracking G-row. RESULTS_LEDGER.md row and memo share one explicit-pathspec commit; TRACKING_GAPS_2026-09-01.md is untouched. No push.
