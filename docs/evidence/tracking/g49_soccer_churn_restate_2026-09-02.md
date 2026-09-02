# G49 Soccer Churn Restatement - 2026-09-02

## Scope and result

This is a read-only restatement of the committed G08 packet. No tracker,
harness threshold, G08 table, code, pod, or daemon was changed.

The identity issue visibly present in the assessable windows is in-window ID
replacement (ID fragmentation): five visually assessable endpoint pairs show a
green tracker label changing for an identifiable subject during a ten-second
uncut sequence. Per scope, this memo names that defect and stops; it proposes
no fix and creates no new gap ID.

## Reproduction and restated unit

I read all three committed `soccer_s1_stream_windows.csv` files under
`soccer_stream_packet_2026-09-02`. They contain 15 windows, 4,500 decoded
frames, 417 summed window-distinct IDs, and 53,620 person detections. The
detection-weighted mean concurrent boxes is 11.915555555556, which rounds to
11.916.

Reconciliation line: the legacy 0.00778 statistic reproduces as
417 / 53,620 = 0.007776948900, and is **ids-per-detection**, not a defect-size
unit. It decreases when the same ID minting is divided across more detected
boxes, so it is not interpretable as tracker defect magnitude.

The restated statistic is computed independently for each ten-second window as
`distinct_track_ids / mean_raw_person_boxes_per_frame`, then averaged over the
15 windows. It is **2.47 track IDs per concurrent person per 10 s window**
(unrounded mean 2.473753101872; range **1.42-4.95**).

The 95% interval is a nonparametric percentile bootstrap of the mean over the
15 window-level ratios: 100,000 resamples with seed 20260902 gives
**2.08-2.96** track IDs per concurrent person per 10 s. Bootstrap is appropriate
for this continuous mean-of-ratios statistic; a Wilson interval is for a
binomial proportion and is not applicable. This interval describes variation
among these 15 seeded windows, not an independent-corpus generalization.

## Eye check: all stored endpoint renders

G49 states a 28-render decision set, but the committed packet actually contains
**30 endpoint image files**, organized as **15 first/last comparison pairs**
(ten endpoints for each of three clips). This count discrepancy is a falsified
artifact-count premise. I viewed every one of the 30 images below; none was
skipped or inferred from CSV ID counts. A verdict necessarily applies to a
first/last comparison pair, so the table has 15 comparison rows rather than
inventing 28 rows for an artifact set that is not present.

| comparison pair | visual observation | verdict |
|---|---|---|
| AgspyOj5BPk w01 | Coach close-up at 09:57 to wide pitch at 10:07. | NOT-ASSESSABLE - a cut |
| AgspyOj5BPk w02 | Close stoppage shot to wide set-piece view at 15:48. | NOT-ASSESSABLE - a cut |
| AgspyOj5BPk w03 | Wide live play to referee close-up at 17:22. | NOT-ASSESSABLE - a cut |
| AgspyOj5BPk w04 | Wide penalty-area view to tight moving player view at 21:11. | NOT-ASSESSABLE - a cut |
| AgspyOj5BPk w05 | Same sideline angle at 23:38; Belgium #17 changes visible green label 5 to 16. | ASSESSABLE-AND-CHANGED |
| DdnvC6-PGYY w01 | Uncut wide midfield pan from 07:14 to 07:24; later frame includes labels 22, 25, and 26 after an all-20-or-lower first frame. | ASSESSABLE-AND-CHANGED |
| DdnvC6-PGYY w02 | Continuous wide play from 12:57 to 13:07; teal #9 changes visible green label 1 to 12. | ASSESSABLE-AND-CHANGED |
| DdnvC6-PGYY w03 | Uncut wide goal-end view from 14:32 to 14:42; yellow goalkeeper changes visible green label 12 to 5. | ASSESSABLE-AND-CHANGED |
| DdnvC6-PGYY w04 | Goal-mouth view to behind-goal replay angle. | NOT-ASSESSABLE - a replay |
| DdnvC6-PGYY w05 | Continuous goal-end wide view from 20:50 to 21:00; teal #8 changes visible green label 8 to 12. | ASSESSABLE-AND-CHANGED |
| kSgNjoaqCpI_1080p w01 | High wide midfield view to tight two-player follow shot. | NOT-ASSESSABLE - a cut |
| kSgNjoaqCpI_1080p w02 | Wide midfield view to close-up of blue #10 and yellow opponent. | NOT-ASSESSABLE - a cut |
| kSgNjoaqCpI_1080p w03 | Extreme obstruction/close-up to orange-goalkeeper goalmouth view. | NOT-ASSESSABLE - a cut |
| kSgNjoaqCpI_1080p w04 | Goal-area broadcast angle to distant reverse-field view with opposite goalkeeper. | NOT-ASSESSABLE - a cut |
| kSgNjoaqCpI_1080p w05 | Broad-side field views, but subjects are too small and dispersed for a reliable endpoint identity match. | NOT-ASSESSABLE - too few matchable subjects |

The changed fraction is **5 / 5 assessable comparison pairs = 1.00**. The
denominators are explicitly: 5 assessable pairs and 15 total pairs (30 viewed
endpoint images). It is not 5/28 and it is not 5/30. The prior memo's result,
"1 changed" out of 4 viewed endpoint images, was a floor rather than a
measurement; its limited review could not supply a comparison-pair denominator.

The eye check contradicts any reassuring reading of the restated mean: all five
assessable pairs changed, while the other ten pairs were made non-assessable by
broadcast production rather than by stable identity continuity.

## Legacy-statistic locations for orchestrator correction

The following current documents quote the legacy detection-normalized headline.
They are listed for correction; this lane did not edit other lanes' memos or
register rows.

- `docs/evidence/tracking/soccer_stream_packet_2026-09-02.md` (G08 memo)
- `docs/evidence/tracking/g35_gapfinder_2026-09-02.md` (G35 memo)
- `docs/evidence/tracking/RESULTS_LEDGER.md` (G08 ledger row)
- `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` (G08 and G49 register rows)

`docs/evidence/cross-corpus-replication.md` contains a similarly shaped decimal
as part of an unrelated signal coefficient, not this tracking statistic, and is
not a correction target.

## NOT VERIFIED

- No G08 packet re-run was performed, so this is not a fresh tracker measurement.
- The rendered endpoints cannot identify the underlying association failure mode
  or establish a particular code fix.
- The interval is not a multi-corpus or live-production estimate.
- Homography, coordinate quality, and the S1 verdict were not re-adjudicated.
- The packet manifest's detector-branch wording was not independently resolved.

## Verifier-contract B self-check

| check | result |
|---|---|
| B1 Circular metric | Clear: every stored comparison pair is named; no failing pair was excluded from the reported assessable denominator. |
| B2 Non-additive schema | Clear: no schema or reader changed. |
| B3 Fall-through loss | Clear: no gate changed; non-assessable pairs remain named evidence, not discarded data. |
| B4 Re-claim loop | Clear: no claim or workflow changed. |
| B5 Pre-verification deploy | Clear: read-only local artifact review; no pod action occurred. |
| B6 Orphans | Clear: no module moved or retired. |
| B7 Head-slice evidence | Clear: all 15 comparison pairs / 30 endpoints were viewed, across all clips and window positions. |
| B8 Self-fit as independent | Clear: no fitted model or independent-performance claim. |
| B9 Degenerate denominator | Clear: restated numerator and concurrent-subject denominator are window-specific; the legacy detection denominator is explicitly rejected as defect size. |
| B10 Moved bar | Clear: no harness threshold or gate changed. |
