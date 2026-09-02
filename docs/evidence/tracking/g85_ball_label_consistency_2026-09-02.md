# G85 - Tennis Ball Label Consistency (2026-09-02)

## Answer

`tennis_10`'s 27.7 percent is a clip property at the prevalence level: the independent blind sample was also low at 6/20 (30.0 percent), versus 16/20 (80.0 percent) for `tennis_09` and 19/20 (95.0 percent) for `nyYk_720p`, although its row-level labels are criterion-sensitive and cannot be treated as interchangeable across labellers.

## Method

One labeller made every call in [blind_labels.csv](g85_consistency/blind_labels.csv) before any prior row-level `ball_visible` value was opened. The fixed sample used PowerShell `System.Random(850917)`: 20 distinct rows without replacement from each of the three resolved chunks, with only clip/frame identities exposed to the labeller. The sample is therefore 60 unique `(clip, source_frame)` pairs, not a re-labelling of the existing 109 rows.

Each call was made from its corresponding G65 source-derived tiled 2x composite in [g85_consistency/renders/](g85_consistency/renders/). `tennis_09` and `tennis_10` use 4800x1800 three-tile composites; `nyYk_720p` uses 3200x1800 two-tile composites. `ball_visible` means an individually identifiable ball at that viewing scale; otherwise the call is `uncertain`.

Only after the 60 blind calls were fixed did this audit join by frame to the prior resolved chunks:

| Clip | Blind visible | Prior visible in sample | Agreement | Prior visible / blind uncertain | Prior uncertain / blind visible |
|---|---:|---:|---:|---:|---:|
| `nyYk_720p` | 19/20 (95.0%) | 20/20 (100.0%) | 19/20 (95.0%) | 1 | 0 |
| `tennis_09` | 16/20 (80.0%) | 16/20 (80.0%) | 12/20 (60.0%) | 4 | 4 |
| `tennis_10` | 6/20 (30.0%) | 2/20 (10.0%) | 14/20 (70.0%) | 1 | 5 |

The previously reported full-chunk rates are 29/30 (96.7%) for `nyYk_720p`, 27/32 (84.4%) for `tennis_09`, and 13/47 (27.7%) for `tennis_10`. The blind sample preserves their large ordering despite sampling variation, which supports a clip effect: in `tennis_10`, many frames have a small, fast-moving or frame-leaving ball that is not individually identifiable at the specified 2x view, unlike the high-contrast, readily identifiable balls in the other clips.

## Interpretation and required handling

The measured raw agreement is 45/60 (75.0 percent), and the 14/20 `tennis_10` agreement is still not evidence that individual calls are interchangeable. Its disagreements occur in both directions (1 prior-visible/blind-uncertain and 5 prior-uncertain/blind-visible), so this is an ambiguous operational criterion, not merely a one-sided labeller bias. The fix is criterion calibration with examples at the `ball_visible`/`uncertain` boundary before pooling labellers; this audit does not silently relabel or replace any of the 109 existing calls.

The prevalence result still answers the G85 question: the strong low-versus-high clip separation repeats under a blinded pass, but estimates from individual frames must retain the labeller/criterion caveat until that calibration is complete.

## VERIFIER_CONTRACT and self-check

- A1: No executable test was added; this verifier recomputed the audit directly from the fixed evidence rather than relying on a claimed prior result.
- A2: Counts, agreement, and both disagreement directions above were recomputed from all 60 fixed blind rows and their exact prior-frame matches.
- A3: All 60 decisions use the committed tiled 2x renders, with 20 rows from each clip.
- A4: The verifier asserted 60 total and 60 unique `(clip, source_frame)` pairs.
- A5: No existing label schema or reader was changed.
- A6: Evidence lands in the separate `docs/evidence/tracking/g85_consistency/` directory; no production or gate path changed.
- A7: Every evidence path named here exists: [blind labels](g85_consistency/blind_labels.csv), [render directory](g85_consistency/renders/), and [method note](g85_consistency/README.md).

Self-check B1-B10: no circular row exclusion; no schema, gate, claim-loop, pod, or deployment change; seeded non-head sampling; no self-fit; 60 unique rows; and no threshold change. The sole conclusion is the measured clip/criterion finding above.
