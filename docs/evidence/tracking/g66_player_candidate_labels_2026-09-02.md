# G66 tennis player-candidate labels

Date: 2026-09-02. Gap: G66. This row produces a render-attributed candidate
label set only. It does not compute a jump split, change a selector, or touch
the adapter.

## Schema correction and corpus overlap

`docs/evidence/tracking/tennis_player_select_limit_2026-09-04/candidates.csv`
has 33,632 candidate rows and these columns only:
`match, range_start, range_stop, source_frame, local_frame, candidate_index,
x1, y1, x2, y2, foot_x, foot_y, confidence, detector_track_id`. It has no
label field. The prior 21 committed renders were a viewing sample, not a label
set.

The candidate artifact covers `tennis_09`, `tennis_10`, and
`tennis_nyYk2nPZAwY_720p`. G38 used `tennis_02` through `tennis_05`; there is
no clip overlap. A later join to G38's own tables therefore needs new tables or
new candidates. This label set deliberately labels the clips the candidates
actually cover and does not paper over that mismatch.

## Durable label set

- Labels: `docs/evidence/tracking/g66_player_candidate_labels/labels.csv`
- Sampling manifest: `docs/evidence/tracking/g66_player_candidate_labels/sample_manifest.csv`
- Sampling parameters: `docs/evidence/tracking/g66_player_candidate_labels/sampling.json`
- Label summary: `docs/evidence/tracking/g66_player_candidate_labels/label_summary.json`
- Rendered source-frame-plus-crop images: `docs/evidence/tracking/g66_player_candidate_labels/renders/`

Each of the 210 rows has exactly one label from the required vocabulary and a
render path. Every image displays the source frame with the candidate box in
red, plus an enlarged crop of that boxed candidate. Labels were assigned by
looking at those images, not from a selector decision.

## Sampling

Seed: `20260902`. The seed is applied with Python's `random.Random` after
sorting candidate rows by
`match:range_start:range_stop:source_frame:candidate_index`.

The 15 `(match, range_start, range_stop)` groups are the strata. Each supplies
14 rows: eight `stride_proxy_gt8` and six `baseline`, for 210 labels total and
70 labels per clip. `stride_proxy_gt8` is a reproducible enrichment proxy:
within a range, the same `candidate_index` appears at source frame `f` and
`f-3` or `f+3`, and the two candidate foot points are more than 8 ft apart.
The candidate CSV has neither a selected-candidate field nor a detector track
ID (all are blank), so this is not an assertion that the selector chose either
row. It is explicitly retained as a stratum for later reweighting and joining.

| clip | ranges | baseline | stride_proxy_gt8 | total |
|---|---:|---:|---:|---:|
| tennis_09 | 5 | 30 | 40 | 70 |
| tennis_10 | 5 | 30 | 40 | 70 |
| tennis_nyYk2nPZAwY_720p | 5 | 30 | 40 | 70 |
| total | 15 | 90 | 120 | 210 |

Every individual range stratum has six baseline and eight proxy-positive rows;
the manifest records its range, source frame, original candidate CSV row, and
candidate box.

## Labels observed

Wilson intervals below are two-sided 95 percent intervals (z = 1.96), over all
210 rendered candidates.

| label | count | share | 95 percent Wilson interval |
|---|---:|---:|---:|
| player | 51 | 24.3% | [19.0%, 30.5%] |
| non_player_person | 155 | 73.8% | [67.5%, 79.3%] |
| duplicate_of_player | 0 | 0.0% | [0.0%, 1.8%] |
| not_a_person | 0 | 0.0% | [0.0%, 1.8%] |
| uncertain | 4 | 1.9% | [0.7%, 4.8%] |

- `player` share: 51/210 = 24.3% (95% Wilson [19.0%, 30.5%]).
- In the deliberately enriched `stride_proxy_gt8` stratum, 95/120 = 79.2%
  are not labelled `player` (95% Wilson [71.1%, 85.5%]). This is a descriptive
  share of the labelled candidate-index stride proxy, not a G38 endpoint split:
  actual selector-endpoint membership is absent from the input artifact.

Per-clip player/non-player/uncertain counts are `16/54/0` for `tennis_09`,
`14/56/0` for `tennis_10`, and `21/45/4` for `tennis_nyYk2nPZAwY_720p`.

## Eye check notes

The common confusable cases were real: baseline ball kids and line personnel
were small at broadcast resolution and can look player-like when near the
painted court boundary. Chair-side staff, chair umpires, photographers, and
front-row spectators also generated person boxes. In contrast, a match player
was identified from their on-court position and play context visible in the
source frame, never because any selector chose that candidate. Four boxes at a
top-edge broadcast-graphic boundary remain `uncertain`; their one-clause
reason is stored row by row in `labels.csv`.

## NOT VERIFIED

- This is not the three-way >8 ft jump-endpoint split; G38B must make that
  later join once it supplies selected endpoint identities.
- The candidate artifact cannot establish a detector-track relationship because
  `detector_track_id` is blank on all 33,632 rows.
- The label set is a stratified, enriched sample, not a prevalence estimate for
  all 33,632 candidates without reweighting.
- No selector, solver, camera lock, coordinate contract, adapter, or harness
  threshold was changed.

## Self-check against verifier contract B

- B1: no rows were excluded from the declared 210-row sample.
- B2-B6: no runtime schema, reader, gate, deployment, or module was changed.
- B7: sampling is seeded and stratified over all 15 ranges, not a head slice.
- B8: labels are independent visual annotations, not a fit or selector output.
- B9: denominators are distinct candidate CSV rows and the proxy denominator is
  named explicitly.
- B10: no threshold or harness value was changed.
