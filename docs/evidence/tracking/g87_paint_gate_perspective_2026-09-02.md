# G87 Paint-Gate Perspective Audit

## Result: the strong rejection claim is FALSIFIED on this hand-marked sample

This row tested the existing image-space role gate without changing
`domains/basketball/tracking/line_calibration.py`, its `1.8` / `1.6` thresholds,
the coordinate contract, or the producer. Each row below is a G76-audited
`PAINT_SOLVABLE` tile. I hand-marked exactly the baseline, free-throw line, and
two lane sides visible in the original 640x384 tile, then passed exactly those
four segments to `assign_paint_roles`.

The gate rejected **1/12 (8.33%)** true-line inputs, at the `parallel` gate. It
passed **11/12**. Therefore the strong form of the proposed mechanism--that
ordinary broadcast perspective rejects the true paint gate generally--is
falsified by this sample. The one rejection is still useful: it has a 68.47
degree baseline-to-lane image angle and is rejected at the first checked gate
with `parallel=1.543` (and `orthogonal=1.266`). The passing views have measured
angles from 79.66 to 88.59 degrees. This is a measurement, not a threshold
retuning recommendation.

## Construction and hand truth

The frozen G76 audit's label-selection seed is `76092026`. For this G87
construction, I used seed `87092026` to select and screen G76-positive source
identities, then retained only a tile where every one of the four required
physical lines could be traced as an image segment. This is required input
construction, not a scored exclusion: a row with no traceable line cannot be
fed as a true-four-line input. The preliminary screened identities that could
not be used as such are named here rather than silently dropped:

- `WFl3V7ZY4ss:f2865`, `sRtHQbywiTE:f1728`, `tiUvyvWOCxo:f27264`, and
  `wnba_01:f16128` were close/cutaway views without all four traceable lines.
- `wnba_02:f6336`, `wnba_04:f1920`, and `wnba_05:f17280` likewise did not show
  four fittable paint lines in the native tile.

The 12 entered rows are distinct frame identities. Per-clip counts are one
each for the six NCAA clips, three for `wnba__wnba_01`, and three for
`wnba__wnba_01_1080p`; NCAA/WNBA counts are 6/6. They span both leagues and
multiple points in their source clips, rather than the head of a frame list.

The exact manual endpoint declarations are in
[hand_marks.json](g87_paint_gate/hand_marks.json). The twelve marked native
renders are under [renders](g87_paint_gate/renders), with red baseline, green
free-throw, blue `lane_low`, and yellow `lane_high`. They are the eye-checkable
input to the gate; no LSD candidate, detector output, or arithmetic-only
surrogate was used.

## Measured replay

`PASS` means `assign_paint_roles` returned roles for the four manual segments.
For `REJECT`, `gate` is the first existing guard that failed. Scores are sums
of the two existing image-direction terms, so the reported values are directly
comparable to the unchanged 1.8 and 1.6 guards.

| clip | frame | baseline-to-lane angle | parallel | orthogonal | verdict | gate |
|---|---:|---:|---:|---:|---|---|
| IB-_u4gW3ds | 19200 | 87.07 | 1.993 | 1.898 | PASS | PASS |
| IB-_u4gW3ds_1080p | 1560 | 88.59 | 1.997 | 1.951 | PASS | PASS |
| WFl3V7ZY4ss | 2483 | 68.47 | 1.543 | 1.266 | REJECT | parallel |
| sRtHQbywiTE | 5760 | 81.56 | 1.979 | 1.706 | PASS | PASS |
| tiUvyvWOCxo | 192 | 83.06 | 1.985 | 1.758 | PASS | PASS |
| zqBCKovJCQU | 3648 | 79.66 | 1.961 | 1.641 | PASS | PASS |
| wnba_01 | 11904 | 85.72 | 1.999 | 1.851 | PASS | PASS |
| wnba_01 | 8448 | 82.03 | 1.991 | 1.723 | PASS | PASS |
| wnba_01 | 13632 | 81.47 | 1.994 | 1.703 | PASS | PASS |
| wnba_01_1080p | 360 | 79.79 | 1.991 | 1.645 | PASS | PASS |
| wnba_01_1080p | 2640 | 83.20 | 1.993 | 1.763 | PASS | PASS |
| wnba_01_1080p | 4080 | 84.25 | 1.995 | 1.800 | PASS | PASS |

The machine-readable version is [measurements.csv](g87_paint_gate/measurements.csv).
Reproduce the replay and the renders (with the read-only original G68 boards
available) using:

```text
python -m scripts.platformkit.g87_paint_gate_audit --source-root <g68 contact_sheets root>
python -m pytest tests/domains/basketball/test_g87_paint_gate_audit.py -q
```

## Verifier self-check

- A7: this memo's `hand_marks.json`, `measurements.csv`, and `renders/` paths
  exist in the commit; `renders/` contains 12 named JPEGs. The focused test
  asserts the two artifact counts.
- B1: the denominator is all 12 named, distinct, hand-traceable true-four-line
  inputs. The screened-out G76-positive source identities are named above;
  none contributes a hidden result.
- B2: no existing schema, status, reader, or public field changed.
- B3-B6: this audit changes no gate behavior, deployment state, module location,
  or claim lifecycle.
- B7: the evidence is a seeded construction across both leagues and seven
  source encodes, not a start-of-clip slice.
- B8-B9: no geometry was fitted to score against itself and no identifier is
  recycled; each metric unit is one distinct frame.
- B10: the existing thresholds remain 1.8 and 1.6; this row only calls them.

## Not verified

- This 12-frame construction is not a population estimate of the gate's
  rejection rate across broadcasts, cameras, or leagues.
- It does not contradict G84's separate detector-candidate blocker, and it
  does not determine a replacement perspective-invariant hypothesis test.
- It does not validate the final homography, paint-role correctness beyond the
  manual input, or any downstream tracking behavior.
