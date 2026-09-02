# G84 candidate line quality measurement

Date: 2026-09-02. Gap G84. This is an input measurement only. It builds no
solver and no role rule, changes no threshold, coordinate contract,
`line_calibration.py`, producer, pod file, or deployment.

## Input and selection

The source of truth is the separate G76 audit label file, not the original G68
census labels. The frame set is a seeded, clip-stratified sample of three
`PAINT_SOLVABLE` rows from each of the 11 G76 clips: 33 unique frames total.
The seed is `84092026` (`random.Random`); the selection and all per-clip counts
are committed in [selection.json](g84_candidate_quality/selection.json), and
the frame identities and candidate counts are in
[sample_manifest.csv](g84_candidate_quality/sample_manifest.csv).

Each frame was passed through the existing candidate-group detector used by the
G75 evidence pass (`detect_lsd_segments(image, 28.0)` followed by
`candidate_line_group_details(..., 5.0, 10.0)`). Every returned candidate is
drawn with its index in [renders/](g84_candidate_quality/renders/), and every
one of the 1,764 unique `(clip, frame_index, group_index)` candidates has an
image-only audit label in
[per_group_labels.csv](g84_candidate_quality/per_group_labels.csv). The audit
does not read or call G75 role assignment; a group is not a court line because
any rule accepted it.

| clip family | G76 audited-positive frames |
|---|---:|
| NCAA IB-_u4gW3ds | 3 |
| NCAA IB-_u4gW3ds 1080p | 3 |
| NCAA WFl3V7ZY4ss | 3 |
| NCAA sRtHQbywiTE | 3 |
| NCAA tiUvyvWOCxo | 3 |
| NCAA zqBCKovJCQU | 3 |
| WNBA 01 | 3 |
| WNBA 01 1080p | 3 |
| WNBA 02 | 3 |
| WNBA 04 | 3 |
| WNBA 05 | 3 |

## Result

Wilson 95% intervals are reported. Candidate groups are unique detector groups
within unique source frames, not reused identifiers.

| metric | result |
|---|---:|
| court-line candidates / all candidate groups | 198/1,764 = 11.22% [9.83%, 12.78%] |
| frames where all four physical paint lines are present among candidates | 0/33 = 0.00% [0.00%, 10.43%] |

The second row is the ceiling for a paint naming rule on this sampled audited
input. The observed ceiling is zero: although G76 says the physical lines are
discernible, the existing candidate detector did not return all four paint
lines in any sampled frame. The basketball paint route is therefore limited by
detection before naming on this evidence. **G75 attempt 2 must not be written.**

This is consistent with, but does not overclaim from, G60: tennis clay had a
structurally similar clutter problem, and removing its identified spurious
segments alone still produced zero full solver accepts. A cleaner candidate
input is necessary here; this measurement does not establish that it would be
sufficient for a basketball solve.

## Venue observations

The renders contain both hazards named by the calibration strategy. The WNBA
boards show glossy floor reflections, including reflected bright court and
player structures around the near paint. Paint fills also vary materially by
venue: the sampled images include dark/black, bright blue, and wood-coloured
paint areas. Both hazards create candidate structures that are not the four
physical paint lines.

## Reproduction and verifier self-check

```text
conda run --no-capture-output -n basketball_ai python scripts/platformkit/g84_candidate_line_quality.py
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g84_candidate_line_quality.py -q
```

The focused test passed: `1 passed`.

- A7: the memo's selection file, manifest, per-group label file, and render
  directory exist at report time.
- B1: the sampled population and seed are named; all 33 selected frames remain
  in both denominators.
- B2-B6: this is additive evidence and a focused evidence script/test; no
  schema, reader, gate, deployment, or module was changed or moved.
- B7: selection is seeded and stratified across all 11 clips, not a head slice.
- B8: no fitted residual or role-rule outcome is used as truth.
- B9: denominators are unique candidate groups and unique frames.
- B10: no harness threshold, coordinate contract, or calibration constant moved.

## Not verified

- A replacement detector, ROI, contrast setting, or candidate-cleaning method.
- Whether a clean four-line input is sufficient for role naming, corner solving,
  or coordinate accuracy.
- Generalization beyond these 11 existing basketball clips and their venues.
- Pixel-level provenance for every non-court candidate beyond the recorded
  image-only label taxonomy.
