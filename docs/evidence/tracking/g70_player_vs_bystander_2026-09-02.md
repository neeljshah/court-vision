# G70 tennis player versus bystander classifier: CLOSED AT LIMIT

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and
section B. This is a new G70 measurement built on the G66 labels; it neither
changes nor invokes the tennis adapter.

## Premise reproduced before fitting

Direct CSV recount of `g66_player_candidate_labels/labels.csv` found 210 unique
candidate rows: 51 `player` (24.3 percent), 155 `non_player_person` (73.8
percent), and 4 `uncertain` (1.9 percent). The 4 uncertain rows were excluded
from both training and scoring, leaving exactly 206 rows. No other label or
row was excluded. There are zero `duplicate_of_player` and zero
`not_a_person` labels.

## Fixed classifier and split

The model is a fixed `StandardScaler` plus class-balanced logistic regression
(`liblinear`, C=1.0, seed 20260902). Candidate-local features are court-foot
x/y, log bounding-box area, box aspect ratio, and detector confidence. They
are defensible visual/court-geometry inputs; there is no selector decision,
selected identity, track identity, future observation, or adapter output in
the feature set.

Evaluation is leave-one-clip-out. Each row receives one OOF prediction from a
model trained on the other two clips only. This is deliberately not a row-wise
split: candidates from the same source frame are near duplicates. The durable
definition is `g70_classifier/split_definition.json`, and every prediction,
including its held-out fold, is in `g70_classifier/clip_oof_predictions.csv`.

| held-out clip | train n (player/non-player) | held-out n (player/non-player) |
|---|---:|---:|
| tennis_09 | 136 (35/101) | 70 (16/54) |
| tennis_10 | 136 (37/99) | 70 (14/56) |
| tennis_nyYk2nPZAwY_720p | 140 (30/110) | 66 (21/45) |

## Held-out results

Every accuracy below is shown beside the required G66 label-pool majority
baseline of 0.738. For additional denominator clarity, always predicting
non-player on the 206 scored rows is 155/206 = 0.752; it does not rescue this
result.

| held-out data | accuracy, Wilson 95 percent, vs 0.738 | player recall, Wilson 95 percent | non-player recall, Wilson 95 percent |
|---|---|---|---|
| tennis_09 (n=70) | 0.529 [0.413, 0.641] vs 0.738 | 9/16 = 0.563 [0.332, 0.769] | 28/54 = 0.519 [0.389, 0.646] |
| tennis_10 (n=70) | 0.714 [0.599, 0.807] vs 0.738 | 5/14 = 0.357 [0.163, 0.612] | 45/56 = 0.804 [0.682, 0.887] |
| tennis_nyYk2nPZAwY_720p (n=66) | 0.652 [0.531, 0.755] vs 0.738 | 7/21 = 0.333 [0.172, 0.546] | 36/45 = 0.800 [0.662, 0.891] |
| pooled OOF (n=206) | 130/206 = 0.631 [0.563, 0.694] vs 0.738 | 21/51 = 0.412 [0.288, 0.548] | 109/155 = 0.703 [0.627, 0.770] |

The pooled held-out accuracy is below 0.738, and its 95 percent upper bound is
also below 0.738. The acceptance bar therefore fails. Player recall is only
21/51 and is not enough to offset the failed accuracy bar. Verdict: **CLOSED
AT LIMIT**. The classifier remains offline and unwired.

The 51 positives also leave a wide player-recall interval. As a planning
calculation only, estimating a recall near 0.412 to roughly plus/minus 0.10 at
95 percent confidence needs about 93 positives (normal approximation), or
about 383 candidates at G66's 24.3 percent player prevalence: approximately
42 more player labels and 173 more candidate labels, spread over additional
clips. This is not a claim that more labels alone will fix the cross-clip
feature failure.

## Mandatory held-out error eye check

All 76 OOF mistakes were rendered in `g70_classifier/mistake_renders/` (46
false positives and 30 false negatives). I looked at the 20 files named in
`g70_classifier/eye_check_selection.csv`: 10 per direction, selected evenly
over each direction after ordering by clip, source frame, and candidate index,
not from the head of the set.

- False positives: G66_003, G66_018, G66_029, G66_049, G66_055, and G66_069
  are court-side/back-wall staff or ball-person-like figures with box and
  court-foot geometry that transferred poorly. G66_150 and G66_210 are
  ball-persons near or running through the court. G66_105 and G66_135 look
  player-like in the render despite their fixed `non_player_person` labels;
  this is a visible label/context ambiguity, not a post-score relabel.
- False negatives: G66_002, G66_021, and G66_057 visibly box the active
  on-court player but were rejected under the held-out tennis_09 camera setup.
  G66_090 and G66_117 are small far-side candidates. G66_141, G66_155,
  G66_172, G66_178, and G66_181 are extreme edge, occluded, or very small
  candidate boxes in the held-out grass-court render. Several look ambiguous
  relative to the primary on-court player, so the fixed G66 truth is retained
  but the failure is not claimed to be fully understood from static geometry.

This visual result explains the low transfer: the same static geometry can
describe ball staff and a player in a different broadcast camera, and some
edge candidates lack enough visual context for this feature set. It does not
justify wiring the classifier into production.

## Durability and verifier self-check

A7 was checked before this memo: these paths exist now:

- `g70_classifier/split_definition.json`
- `g70_classifier/clip_oof_predictions.csv`
- `g70_classifier/summary.json`
- `g70_classifier/mistake_manifest.csv`
- `g70_classifier/eye_check_selection.csv`
- `g70_classifier/mistake_renders/` (76 rendered JPEGs)

Section B self-check:

- B1: only the four explicitly named uncertain rows were removed before both
  fitting and scoring; no prediction-dependent exclusion occurred.
- B2-B6: this is additive evidence and an offline platformkit module. No
  runtime schema, reader, gate, deployment, or production claim changed.
- B7: the visual audit samples errors evenly across the full error set, not a
  head slice.
- B8: every score is from a model whose held-out clip is absent from training.
- B9: the denominator is 206 unique `candidate_csv_row_number` values; each
  CSV output row is one labelled candidate.
- B10: no selector, harness threshold, solver, camera lock, coordinate
  contract, or adapter value changed.

## NOT VERIFIED

- This failed offline static-feature model is not a production classifier and
  has no adapter caller.
- No causal claim is made about whether more labels, motion, or image features
  would satisfy the acceptance bar.
- The visually ambiguous fixed G66 labels were not independently re-adjudicated
  after scoring.
- No pod action, deployment, daemon action, or new tracking run occurred.
