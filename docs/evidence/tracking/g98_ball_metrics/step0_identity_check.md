# G98 Step 0 identity comparison

This durable note records the entry-condition calculation required by
`G98_spec.md`. It is a comparison of every label decision; it is not a
tracker measurement.

## Inputs and join key

- Prior resolved-chunk decisions: `../g65_ball_labels/resolved/*.csv` (109
  rows total).
- Calibrated decisions: `../g92_criterion/calibrated_labels.csv` (109 rows).
- Fixed blind comparison: `../g85_consistency/blind_labels.csv` (60 rows).
- Key: canonical clip identity plus `source_frame`. The canonical names are
  `tennis_09`, `tennis_10`, and `nyYk_720p`; this only reconciles filename
  forms, not decisions.

## Complete decision comparison

| Clip | Prior rows | Calibrated rows | Joined rows | Changed label | Unchanged label |
|---|---:|---:|---:|---:|---:|
| `tennis_09` | 32 | 32 | 32 | 0 | 32 |
| `tennis_10` | 47 | 47 | 47 | 0 | 47 |
| `nyYk_720p` | 30 | 30 | 30 | 0 | 30 |
| **Pooled** | **109** | **109** | **109** | **0** | **109** |

The calibrated labels are therefore identical in decision value to the prior
chunks: the exemplar card changed **0 / 109** labels.

## Fixed G85 blind-comparison identity check

| Clip | Old agreement | Calibrated agreement | Same agreeing frame identities |
|---|---:|---:|---:|
| `tennis_09` | 12 / 20 | 12 / 20 | 12 |
| `tennis_10` | 14 / 20 | 14 / 20 | 14 |
| `nyYk_720p` | 19 / 20 | 19 / 20 | 19 |
| **Pooled** | **45 / 60** | **45 / 60** | **45** |

Among the 60 joined blind rows, agreement-identity overlap is 45; there are
0 old-only agreements and 0 new-only agreements. Thus the matching aggregate
is not a coincidental total: it is the exact same 45 frames.

## Consequence

G98's Step 0 stop condition applies. The card did not demonstrate any changed
decision, so this assignment must not pre-register a tolerance, read tracker
rows, calculate recall or precision, or render metric disagreements.
