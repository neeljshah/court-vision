# G118 temporal agreement power extension

## Achievable overlap before labelling

The G65/G85 identity intersection contains 60 unique source frames (20 per
clip). Forty are achievable: the local source MP4s exist for `tennis_09` and
`nyyk_720p`. The remaining 20 are `tennis_10` frames, whose local source MP4
is absent; this is a named source-availability exclusion, fixed before any
new labels were made. G102 had already blind-labelled 29 of the 40 achievable
identities. G118 therefore blind-labelled every remaining achievable identity:
11 rows (eight `tennis_09`, three `nyyk_720p`). The complete census and
pre-label precision statement are in
[`pre_label_protocol.md`](g118_temporal_power/pre_label_protocol.md).

At an assumed 75.0% agreement rate, the planned 40-row pool could have a
Wilson 95% interval of [59.8%, 85.8%] (half-width 13.0 percentage points).
That is an improvement on the 29-row precision, but it is still a bounded
test rather than a high-power separator.

## Pre-registered decision rule

The strip method is BETTER only if the lower endpoint of its two-sided 95%
Wilson agreement interval exceeds the still-frame point estimate of 75.0%.
Failing that rule is a complete result: the labelling branch closes and no
additional label pass is warranted.

## Blind-pass order and evidence

1. The independent G118 labeller derived the candidate census by accessing
   only `clip` and `source_frame` fields from G65, G85, and the G102 sample
   manifest. The protocol records the canonical identity aliases and the
   source-availability restriction before labelling.
2. G102's 29 existing blind calls were retained and not relabelled. The
   11 new rows were enumerated in
   [`candidate_manifest.csv`](g118_temporal_power/candidate_manifest.csv).
3. The labeller rendered clean predecessor/current/successor 2x strips and
   review cards for all 11 new rows, made the blind calls, and committed them
   in `acefa309e37c4dc6f17f392ab3e442b3ed5ecf41` before opening any prior
   row-level G65, G85, or G102 label value or comparison.
4. Only after that commit, the G85 labels were joined. The complete 40-row,
   unique-identity audit is
   [`pooled_agreement_against_g85.csv`](g118_temporal_power/pooled_agreement_against_g85.csv).

## Pooled result and separation verdict

G102 contributes 24 agreements in 29 rows; the 11 new G118 blind labels
contribute 9 agreements. The pooled metric is therefore **33/40 = 82.5%**,
with a two-sided 95% Wilson interval of **[68.1%, 91.3%]**. The independent
formula and unrounded calculation are in
[`agreement_computation.md`](g118_temporal_power/agreement_computation.md).

The observed point estimate is 7.5 percentage points above the 75.0%
still-frame baseline (45/60, Wilson 95% [62.8%, 84.2%]). It does **not** clear
the pre-registered rule: 68.1% is below 75.0%. Temporal context is therefore
not established as better. **Verdict: CLOSED AT LIMIT.** Neither refining the
written criterion (G98) nor adding temporal context (G118) has demonstrated
reliable agreement improvement from this footage; further effort belongs in
acquisition rather than another labelling pass.

## Verifier-contract self-check

| Contract item | Self-check |
| --- | --- |
| A1 | N/A: this evidence-only lane changed no executable code and added no test. |
| A2 | Recomputed from the 40 committed/reused blind-label rows: 33/40 and Wilson [0.680500, 0.912546]. |
| A3 | The decision set is all 40 source-available G65/G85 identities. The blind labeller reviewed every new card; as a verifier eye check, seven review cards were inspected at evenly spaced sorted decision-set positions 0, 7, 14, 21, 28, 35, and 39. |
| A4 | `pooled_agreement_against_g85.csv` has 40 rows and 40 unique `(clip, source_frame)` identities; it partitions into 29 reused G102 and 11 new G118 rows. |
| A5 | A reader search found no source-code reader of the new evidence artifacts; the only external text reference is the G118 specification's required evidence-directory path. |
| A6 | Lane work is committed in this worktree only. No landing, ledger append, deployment, or flag action was taken; those are verifier-owned actions. |
| A7 | Every evidence path named below was checked to exist after the final artifact write and before the final commit. |

| Section B item | Self-check |
| --- | --- |
| B1 | The denominator is every achievable source-available overlap (40); all 20 unavailable `tennis_10` identities are named before labels, not excluded on outcome. |
| B2 | No existing schema or reader changed; all additions are new evidence artifacts. |
| B3 | No gate or threshold changed. |
| B4 | No production claim path was added. |
| B5 | No pod command was run; the pod remained read-only. |
| B6 | No module, import, test, or command entry point moved. |
| B7 | The metric uses the full achievable overlap, not a head slice; the supplemental eye check was evenly spaced over that complete decision set. |
| B8 | No model or threshold was fit to these blind labels. |
| B9 | The 40 source-frame decisions are unique and no row is recycled. |
| B10 | The G85 seed, the 110/150 pool count, all harness thresholds, the y-gate, and the coordinate contract were not touched. |

## Not verified

- A true improvement in ball recoverability from temporal context; the
  pre-registered lower-bound bar was not met.
- Coverage of the 20 `tennis_10` overlap identities because the local source
  video is absent.
- Any detector, production, coordinate, y-gate, or model impact.
- Generalization beyond this fixed G65/G85 overlap.

## Evidence paths

- [G118 specification](specs/G118_spec.md)
- [Verifier contract](VERIFIER_CONTRACT.md)
- [G102 memo](g102_ball_label_temporal_2026-09-02.md)
- [G85 blind labels](g85_consistency/blind_labels.csv)
- [Pre-label protocol](g118_temporal_power/pre_label_protocol.md)
- [Candidate manifest](g118_temporal_power/candidate_manifest.csv)
- [New committed blind labels](g118_temporal_power/blind_labels.csv)
- [New render manifest](g118_temporal_power/render_manifest.csv)
- [New clean strips](g118_temporal_power/strips_blind)
- [New review cards](g118_temporal_power/review_cards_blind)
- [Pooled agreement audit](g118_temporal_power/pooled_agreement_against_g85.csv)
- [Wilson calculation](g118_temporal_power/agreement_computation.md)
