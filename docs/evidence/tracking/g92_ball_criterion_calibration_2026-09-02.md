# G92 - Tennis Ball Criterion Calibration (2026-09-02)

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7 and
section B. Input: [G85](g85_ball_label_consistency_2026-09-02.md).

## Answer

The calibrated criterion resolves **110 / 150** pooled `ball_visible` calls,
so the precondition of at least 100 resolved positives is **YES**. This is a
criterion-calibration result only; it does not measure detector recall or
precision.

The fixed G85 comparison is **45 / 60 = 75.0%** agreement, Wilson 95% CI
**62.8% to 84.2%**. It did not improve on the pre-card **45 / 60 = 75.0%**
agreement. There is no pass bar on this number: this is a real finding that
the boundary remains intrinsically ambiguous at this zoom and routes the next
row to higher zoom or a different definition, not to more labelling. The G85
blind labels and seed 850917 were not edited; the card examples were chosen
outside that fixed sample.

## Exemplar card

All calls below use G65's tiled 2x renders. `ball_visible` requires a compact,
separately locatable ball-shaped mark with an edge distinct from its
background. A brightness change, court-line fragment, diffuse motion trail,
or an object with no locatable compact head is `uncertain`. Do not use a
neighbouring frame to infer the call.

### Clear `ball_visible` (4)

| Frame | Evidence | Call |
|---|---|---|
| `tennis_09:7028` | [render](g92_criterion/exemplars/tennis__tennis_09_f07028.jpg) | Compact high-contrast mark is separately locatable. |
| `tennis_09:7076` | [render](g92_criterion/exemplars/tennis__tennis_09_f07076.jpg) | Compact high-contrast mark is separately locatable. |
| `tennis_09:7106` | [render](g92_criterion/exemplars/tennis__tennis_09_f07106.jpg) | Compact high-contrast mark is separately locatable. |
| `tennis_09:7118` | [render](g92_criterion/exemplars/tennis__tennis_09_f07118.jpg) | Compact high-contrast mark is separately locatable. |

### Clear `uncertain` (4)

| Frame | Evidence | Call |
|---|---|---|
| `tennis_10:4073` | [render](g92_criterion/exemplars/tennis__tennis_10_f04073.jpg) | No compact head separates from the blur. |
| `tennis_10:4088` | [render](g92_criterion/exemplars/tennis__tennis_10_f04088.jpg) | No compact head separates from the blur. |
| `tennis_10:4103` | [render](g92_criterion/exemplars/tennis__tennis_10_f04103.jpg) | No compact head separates from the blur. |
| `tennis_10:4108` | [render](g92_criterion/exemplars/tennis__tennis_10_f04108.jpg) | No compact head separates from the blur. |

### Boundary calls (6)

| Frame | Evidence | Adjudication | One deciding feature |
|---|---|---|---|
| `tennis_10:4113` | [render](g92_criterion/exemplars/tennis__tennis_10_f04113.jpg) | `ball_visible` | A compact approximately 3-pixel head remains distinct from its short blur. |
| `tennis_10:4128` | [render](g92_criterion/exemplars/tennis__tennis_10_f04128.jpg) | `uncertain` | Motion-blur streak has no separately locatable compact head. |
| `tennis_10:4233` | [render](g92_criterion/exemplars/tennis__tennis_10_f04233.jpg) | `ball_visible` | The partial-frame object still has a compact closed head before the frame edge. |
| `tennis_10:4248` | [render](g92_criterion/exemplars/tennis__tennis_10_f04248.jpg) | `uncertain` | Contrast against the court does not support a distinct compact boundary. |
| `tennis_10:4258` | [render](g92_criterion/exemplars/tennis__tennis_10_f04258.jpg) | `uncertain` | Motion-blur streak length exceeds a separable compact head. |
| `tennis_10:4268` | [render](g92_criterion/exemplars/tennis__tennis_10_f04268.jpg) | `ball_visible` | A compact approximately 4-pixel head is distinct from the court. |

## One-pass calibrated relabel

[calibrated_labels.csv](g92_criterion/calibrated_labels.csv) contains one
calibrated tiled-2x call for every one of G65's **109** initially uncertain,
unique `(clip, source_frame)` rows. It is add-only: neither the G65 chunk
labels nor G85's blind labels were overwritten. The prior 41 clear G65
`ball_visible` calls are retained only when combining the 150-row pooled
count; they are not relabelled here because this assignment is specifically
the 109 initially uncertain rows.

For the G85 comparison, the 60-row calibrated decision set is therefore the
new call when the seeded frame was one of the 109 and the untouched G65 clear
call otherwise. This is the exact add-only rule used for both agreement and
the pooled count.

## Re-measurement

| Clip | Calibrated agreement with fixed G85 blind rows | Calibrated visible / 50 |
|---|---:|---:|
| `tennis_09` | 12 / 20 | 45 / 50 |
| `tennis_10` | 14 / 20 | 16 / 50 |
| `nyYk_720p` | 19 / 20 | 49 / 50 |
| **Pooled** | **45 / 60 = 75.0% (Wilson 95% CI 62.8%--84.2%)** | **110 / 150** |

The 110 pooled positives clear the G44B precondition of 100. This does not
move the criterion to hit that number: the card states the compact-mark rule,
the new one-pass labels expose every retained uncertain call, and the count is
reported as produced. If the result had not cleared 100, this row would have
stopped there without widening the criterion.

G76's 68.6% basketball paint agreement and G85's pre-card 75.0% tennis-ball
agreement show the same method lesson: an unexemplified natural-language
criterion lands around 70% agreement. This card is therefore a reusable
method correction, not a claim about one labeller.

## VERIFIER_CONTRACT and self-check

- A1: No executable code or test was added; there is no new per-file test to
  run. This evidence-only row is rechecked directly from its CSV and renders.
- A2: Recomputed from `calibrated_labels.csv`, the untouched 41 G65 clear
  rows, and all 60 G85 blind rows: 45/60 agreement and 110/150 pooled visible.
- A3: This is an eye check at tiled 2x or better. The complete decision set is
  the 109 seeded, evenly spaced G65 uncertain rows across all three clips,
  not a head slice.
- A4: The calibrated CSV has 109 rows and 109 unique `(clip, source_frame)`
  pairs; combined with the retained 41, the pool has 150 unique decisions.
- A5: No field reader is affected: the new CSV is add-only evidence and no
  production schema, reader, or import changed.
- A6: No pod deployment, archive landing, register, or ledger action was
  performed by this lane. The requested worktree commit uses explicit paths.
- A7: Every evidence path named in this memo exists at write time:
  `g92_criterion/`, `g92_criterion/README.md`,
  `g92_criterion/calibrated_labels.csv`, and all fourteen linked renders in
  `g92_criterion/exemplars/`; the unchanged G65/G85 source paths cited above
  also exist.

Self-check B1: no row is excluded from either named denominator; all 109
relabels and all 150 pooled decisions are named. B2: no existing column,
status, field, or reader changed. B3: no gate was changed or made to
quarantine absent evidence. B4: no claim path exists or was changed. B5: no
file was copied to a pod before acceptance. B6: no module, import, or test was
moved or retired. B7: G65's seeded, evenly spaced rally windows provide the
complete non-head decision set. B8: the agreement comparator is G85's fixed
blind label set and its examples are excluded from the card; this is not a
residual fit on the scoring rows. B9: the metric uses unique frame decisions,
not recycled identifiers. B10: no harness threshold, gate value, seed, or
coordinate contract moved.

## NOT VERIFIED

- This does not establish ball-detector recall, precision, a spatial gate, or
  any production tracking performance.
- The Wilson interval quantifies agreement with this fixed 60-row blind pass,
  not agreement with a physical-ball ground truth or another corpus.
- The criterion may remain intrinsically ambiguous at a different zoom,
  compression level, camera angle, or sport.
