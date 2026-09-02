# G102 temporal ball-label evidence

## Result

The strip pass agreed with the independent G85 blind labels on 24 of 29 overlapping rows: **82.8%**, Wilson 95% CI **[65.5%, 92.4%]**. The observed point estimate is **+7.8 percentage points** versus the still-frame baseline of 75.0% (Wilson 95% CI [62.8%, 84.2%]). The intervals overlap and the G102 overlap is only 29 rows, so this is an observed movement in the point estimate, not evidence of a statistically established or durable improvement.

G102 is complete under its stated no-pass-bar rule: the strips were built, the blind labels were committed before comparison, and agreement was measured. This evidence does not change a production gate, model, coordinate contract, or any previous label set.

## Blind-pass order and render evidence

1. The candidate identities were derived from the 109 G65 uncertain rows by explicitly reading only `clip` and `source_frame`; no prior row-level `ball_visible` or blind-label value was opened before the blind-label commit. The protocol record is [blind_pass_protocol.md](g102_temporal_labels/blind_pass_protocol.md).
2. Seed `10220260902` generated the 40-row rendered set in [sample_manifest.csv](g102_temporal_labels/sample_manifest.csv). All 40 are unique members of the 109 candidate identities.
3. The local `tennis__tennis_10.mp4` source was unavailable when rendering. Before rendering, this excluded its 47 candidates on source availability alone, leaving 62 locally renderable candidates; the seeded 40 were sampled without replacement from that availability-defined subset. This is a named coverage restriction, not an outcome-based exclusion.
4. The 96 tiled, spatially aligned 2x predecessor/current/successor strips are committed in [strips_blind_retry](g102_temporal_labels/strips_blind_retry), with tile/frame provenance in [render_manifest_blind_retry.csv](g102_temporal_labels/render_manifest_blind_retry.csv). The 40 review cards used to examine their tile strips are committed in [review_cards_blind_retry](g102_temporal_labels/review_cards_blind_retry).
5. One labeller made all 40 calls from those strips only. The labels were written and committed in `ae789355f39f7d70cd22e8680ea45f2221b480d6` before any prior label file was opened: [strip_labels_blind_retry.csv](g102_temporal_labels/strip_labels_blind_retry.csv).
6. Only after that commit, G85 was opened and joined. The per-row comparison is [agreement_against_g85_blind_labels.csv](g102_temporal_labels/agreement_against_g85_blind_labels.csv), and the independently reproducible Wilson calculation is [agreement_computation.md](g102_temporal_labels/agreement_computation.md). The comparison source is [G85 blind labels](g85_consistency/blind_labels.csv).

`ball_visible=true` in the G102 blind file normalizes to G85 `ball_visible`; `false` normalizes to G85 `uncertain`. The identity normalization used solely for the join is recorded in the computation note. Of the 40 labelled rows, 29 overlap G85; that overlap is the agreement denominator. The other 11 are retained in the blind-label artifact and were not discarded on label outcome.

## Secondary resolved-rate observation

Thirty-seven of 40 strip labels were `ball_visible` (92.5%); three remained `uncertain` after normalization. This is intentionally secondary. The decision metric is the 24/29 agreement result above, not the higher rate of ball-visible calls.

## Verifier-contract self-check

| Contract item | Self-check |
| --- | --- |
| A1 | N/A: this lane adds evidence only and changes no executable code, so no master per-file test exists to rerun. |
| A2 | Recomputed directly from the committed 29-row agreement artifact: 24/29 and Wilson [0.654516, 0.924021]. |
| A3 | All 40 review cards and all 96 underlying clean strips were inspected or supplied as the labelled visual record. |
| A4 | 40 unique sampled `(clip, source_frame)` identities; 29 unique joined identities. |
| A5 | A source-tree reader search found no readers of the new evidence-only artifact names or fields. |
| A6 | Lane commit only; no merge, deploy, ledger append, or feature-flag action. Landing and any ledger action remain verifier-owned. |
| A7 | Every relative evidence path named in this memo was checked to exist before the final evidence commit. |

| Section B item | Self-check |
| --- | --- |
| B1 | The 47 unavailable-source candidates are explicitly named as a pre-render, non-outcome restriction; the agreement denominator is 29. |
| B2 | No existing schema or reader changed; new CSVs are evidence artifacts only. |
| B3 | No gate, threshold, or harness changed. |
| B4 | No production or performance claim path was added. |
| B5 | No pod command was run; the pod remained read-only. |
| B6 | No modules moved. |
| B7 | The seeded set was sampled without replacement from the named source-available subset, not taken as a head slice. |
| B8 | No model or threshold was fit to these labels. |
| B9 | The 40 labelled source-frame identities are unique; predecessor/current/successor panel reuse across tiles is intentional spatial tiling, not repeated sampled rows. |
| B10 | The y-gate and coordinate contract were not touched. |

## Not verified

- Statistical significance or generalization of the +7.8-point observed movement; the 29-row interval overlaps the still-frame interval.
- Coverage of the 47 `tennis__tennis_10.mp4` candidates, because their local source video is absent.
- Any production impact. This is a labelling-method evidence lane only.

## Evidence paths

- [G102 specification](specs/G102_spec.md)
- [Verifier contract](VERIFIER_CONTRACT.md)
- [G98 baseline memo](g98_ball_recall_precision_2026-09-02.md)
- [G85 protocol](g85_consistency/README.md)
- [G85 blind labels](g85_consistency/blind_labels.csv)
- [G102 blind protocol](g102_temporal_labels/blind_pass_protocol.md)
- [Sample manifest](g102_temporal_labels/sample_manifest.csv)
- [Render manifest](g102_temporal_labels/render_manifest_blind_retry.csv)
- [Clean strips](g102_temporal_labels/strips_blind_retry)
- [Review cards](g102_temporal_labels/review_cards_blind_retry)
- [Committed blind labels](g102_temporal_labels/strip_labels_blind_retry.csv)
- [Agreement audit](g102_temporal_labels/agreement_against_g85_blind_labels.csv)
- [Wilson computation](g102_temporal_labels/agreement_computation.md)
