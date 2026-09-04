# G284 - detector recall bound from sealed visible-person census

## Verdict

**ACCEPT (measurement only; this bounds recall, it does not measure it).** The sealed Pass 1 census counted 524 visibly on-court players and 47 other visibly on-court people in 54 judgeable frames. G267 has 365 finite detector-box observations whose footpoints are on court in those same 54 frames. That is 365 / 524 = **0.697 detector boxes per visible player**, or 365 / 571 = **0.639 detector boxes per visible person**. The raw box ratios are not recall.

If G273's sampled detector-box precision of 43 / 72 = 0.597 is assumed to apply to this on-court subset, 365 * 43 / 72 = 217.986 expected player-box observations. That is **0.416 expected player-box observations per visible player** (217.986 / 524), and 0.382 per visible person (217.986 / 571). Under the further assumption that duplicate boxes are negligible, 0.416 is an upper bound on the fraction of visible players that could have been found. It is not a measured fraction found.

## What was counted, and the sealed blind sequence

Pass 1 used only the 61 committed raw JPEGs in `docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/frames/`, in G278's already committed randomized `blind_order`. No G267 record, detector crop, overlay, marker, or prior detection count was opened while making these counts. `pass_1_protocol.md` and `pass_1_blind_counts.csv` were committed alone as `c5c526691` before any detection join.

The visual rule was fixed once: count a person only if visibly inside the painted boundary lines of the court of play. Bench, sideline, and crowd people are excluded. `CANNOT_COUNT` means the image does not show enough court to judge, and its numeric fields are blank. The denominator is therefore **people visibly on court**, not all people who were actually on court. A fully occluded player cannot be counted by the labeller or detector; this inflates any apparent recall bound.

Of 61 frames, 54 were `COUNTED` and 7 were `CANNOT_COUNT`. The committed per-frame table is `g284_detector_recall_bound_artifact/per_frame_join.csv`; it names every source frame, finite-box count, G270-on-court-box count, geometry category, visible-person counts, and both ratios. No source frames were dropped after seeing detections.

## Detector-box join and denominators

G267's frozen `g267_measurement.json` was opened only after the Pass 1 commit. For every sampled `source_frame`, the join counts:

- **finite detection count:** every G267 detection whose `finite` field is true;
- **on-court detection count:** the finite subset satisfying G270's unchanged inclusive footpoint rectangle, `0 <= court_x_ft <= 50` and `0 <= court_y_ft <= 94`.

The population is detector-box observations, not authenticated players. Across all 61 sampled frames there are 508 finite boxes and 402 on-court boxes. The 54 frames with a visual denominator contain 461 finite boxes and 365 on-court boxes. The 7 `CANNOT_COUNT` frames still retain their box counts in the machine-readable table but do not enter a people-denominated ratio.

| Named quantity | Numerator | Denominator | Value |
| --- | ---: | ---: | ---: |
| Raw on-court boxes per visible player | 365 G270-on-court detector boxes | 524 visible players | 0.697 |
| Raw on-court boxes per visible person | 365 G270-on-court detector boxes | 571 visible players plus other people | 0.639 |
| G273-adjusted expected player boxes per visible player | 365 * (43 / 72) = 217.986 expected player-box observations | 524 visible players | 0.416 |
| G273-adjusted expected player boxes per visible person | 217.986 expected player-box observations | 571 visible people | 0.382 |

Per-frame raw on-court boxes per visible player have n=54, min=0.200, q25=0.425, median=0.683, mean=0.701, q75=0.975, and max=1.300. Per-frame raw on-court boxes per visible person have n=54, min=0.182, q25=0.404, median=0.618, mean=0.647, q75=0.907, and max=1.300. Values above one are another reason a box count cannot identify unique people.

## THIS BOUNDS RECALL, IT DOES NOT MEASURE IT

No per-person matching is performed. Ten visible people and five detector boxes is consistent with five people found once each, or with three people found twice and two people missed. A count ratio is an upper bound on the fraction of people found only if duplicates are negligible. G273/G267's same-frame duplicate diagnostics make duplicates rare but not zero: 0.33 percent of 121,926 pairs are within 1 ft, 0.74 percent within 2 ft, and 0.21 percent within 20 px. Those checks rule out duplicates as a complete explanation; they do not turn the count ratio into recall.

The precision-adjusted 0.416 figure additionally assumes all of the following:

1. G273's 43 / 72 = 0.597 sampled precision applies to the **on-court** G267 subset here. G273 sampled the finite detector-box population, not this subset, so this is unverified and potentially shaky.
2. The rare-but-nonzero duplicate rate is negligible enough that expected correct boxes can stand in for distinct people. This is only an approximation.
3. These 61 fixed frames represent the committed G278 span. They do not represent the clip: G278 measured the span as friendlier than the clip, 0.836 versus 0.656, nominal p=0.0078.

The detector's `player` label is a detection class, not an identity. G267 is one non-deterministic detector draw; G241 documented that 808 / 1,201 exact rerun records differed. Thus neither the raw ratios nor the 0.416 upper bound may be quoted clip-wide, population-wide, or as a stable per-person recall result.

## Count agreement after the seal

After Pass 1 was committed, a separate fresh random order of 24 of its 54 countable frames was drawn with the documented seed and viewed from raw JPEGs only. Its order and values were sealed in `69ded29cd` before this join. The recount did not display Pass 1 counts or detection information.

Of 24 frames, countability status agreed exactly on 23. The 23 frames that were numeric in both passes give the following agreement:

| Count | Exact | Within one | Numeric recount denominator |
| --- | ---: | ---: | ---: |
| Players | 22 | 22 | 23 |
| Other people | 21 | 23 | 23 |
| Players plus other people | 21 | 22 | 23 |

One close-camera frame changed from 10 players plus 1 other person to 5 players and 0 other people; another changed from `COUNTED` to `CANNOT_COUNT`; a third retained ten players but changed other people from zero to one. The visual count is therefore reasonably repeatable on the jointly numeric subset but not invariant. This one-labeller check is not an inter-rater reliability study, and the nontrivial close-camera disagreement is a reason not to promote the bound to recall.

## G278 committed geometry category, descriptive only

These categories were committed by G278 before this work. They were not used to select, exclude, or weight frames here.

| G278 category | All frames | Counted / cannot count | Visible players / other people | On-court detector boxes | Boxes per visible player | Boxes per visible person |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| a | 51 | 45 / 6 | 434 / 40 | 326 | 0.751 | 0.688 |
| b | 2 | 2 / 0 | 20 / 1 | 7 | 0.350 | 0.333 |
| c | 8 | 7 / 1 | 70 / 6 | 32 | 0.457 | 0.421 |

The apparent category differences are descriptive only. Category sizes, particularly b, are too small for a category conclusion; differing `CANNOT_COUNT` rates also make them unsuitable for conditioning this census.

## Reproduction and verifier contract

Run the following local, read-only measurement command to regenerate both result files:

```text
python scripts/platformkit/tracking/g284_detector_recall_bound.py --pass-counts docs/evidence/tracking/g284_detector_recall_bound_artifact/pass_1_blind_counts.csv --categories docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/blind_labels.csv --g267 docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json --recount docs/evidence/tracking/g284_detector_recall_bound_artifact/recount_blind_counts.csv --per-frame-output docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv --summary-output docs/evidence/tracking/g284_detector_recall_bound_artifact/summary.json
```

- A1/A2: the primary receipt is the per-frame CSV (61 source-keyed rows); `summary.json` recomputes every aggregate and agreement value from the sealed inputs.
- A3: not applicable. G278 had already committed this exact 61-frame sample; every frame is joined, rather than a new decision-set slice.
- A4: the harness asserts blind IDs 0 through 60 exactly once, unique source frames, a single G267 record per source frame, and each G278 category exactly once.
- A5: the join adds evidence-only fields and has no production reader. The only reader is the new local harness; no existing schema is changed.
- A6/A11: no verifier landing or pod route is required for this entirely local evidence row.
- A7: all cited inputs and both output artifacts exist in this worktree; the two blind commits precede the join commit.
- A8: the append-only `RESULTS_LEDGER.md` row is added in this same final commit.
- A9: opened inputs were G278's raw-frame directory (61 JPEGs, 12,012,411 bytes, each 1920x1080), G278's 313-byte category file (SHA-256 `2c06f2311a7ac4a1330ce9caf1313b2195faa4e291c7160337891acf5dd0619c`), G267's 12,446,681-byte measurement JSON (SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`), and G273's 8,257-byte precision memo (SHA-256 `41f0378e15f4bce082bee83b6a1fc30b9ab851dd4da4e1c80f607561ea3333de`). The source video was not opened, decoded, rendered, or re-detected.
- A10/A12: no dependency, feature flag, or allowlisted file changed; the new 233-line harness remains under the 300-LOC rail.
- B1/B9: all 61 source frames remain in the table; seven explicitly named `CANNOT_COUNT` frames are separate from the 54 people-denominated rows, and every numerator and denominator is named above.
- B2/B7/B8/B10: additive evidence files only; no selection of a flattering head slice, no schema or threshold change, and no evidence is stored solely in the memo.

## Scope and limits

This is one clip, one shot, 61 frames, and one labeller. The raw JPEGs represent a span already measured as friendlier than its parent clip, so nothing here is clip-wide. The human denominator excludes fully occluded people and can therefore make apparent recall too high. G267 is one non-deterministic detector draw. This row does not tune, filter, set a threshold, retrain, or make an edge claim.
